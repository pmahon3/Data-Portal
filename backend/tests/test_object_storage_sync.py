import asyncio
from types import SimpleNamespace

from core.services.filetree import object_storage_sync as sync


# Minimal S3 fakes: enough to exercise pagination without boto3 or network calls.
class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, Bucket):
        return self.pages


class FakeS3Client:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.pages)


class FakeAgent:
    def __init__(self, pages=None, buckets=None):
        self.s3_client = FakeS3Client(pages or [])
        self._buckets = buckets or []

    def fetch_all_buckets(self):
        return self._buckets


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeFolderSession:
    def __init__(self):
        self.added = []
        self._next_id = 2
        self.restored_folder = SimpleNamespace(status="orphaned")

    def add(self, folder):
        self.added.append(folder)

    async def flush(self):
        if self.added[-1].id is None:
            self.added[-1].id = self._next_id
            self._next_id += 1

    async def get(self, model, folder_id):
        return self.restored_folder

    async def execute(self, stmt):
        values = stmt.compile().params
        folder = SimpleNamespace(
            id=self._next_id,
            full_path=values["full_path"],
            marker_key=values["marker_key"],
            path=values["path"],
            status=values["status"],
        )
        self._next_id += 1
        self.added.append(folder)
        return SimpleNamespace(one=lambda: (folder.id, folder.path, folder.status))


# Verifies S3 pagination is flattened into fixed-size async batches.
def test_batches_s3_objects_by_size():
    async def run():
        agent = FakeAgent(
            pages=[
                {"Contents": [{"Key": "a"}, {"Key": "b"}]},
                {"Contents": [{"Key": "c"}, {"Key": "d"}, {"Key": "e"}]},
            ]
        )

        batches = []
        async for batch in sync.iter_s3_object_batches(agent, "bucket", batch_size=2):
            batches.append([obj["Key"] for obj in batch])

        return batches

    assert asyncio.run(run()) == [["a", "b"], ["c", "d"], ["e"]]


# Verifies missing folder ancestors are created and cached with ltree paths.
def test_folder_cache_creates_nested_folders():
    async def run():
        session = FakeFolderSession()
        cache = sync.FolderCache("bucket", session)
        cache.id_cache["/"] = 1
        cache.ltree_cache["/"] = sync.Ltree("root")
        cache.status_cache["/"] = "complete"

        folder_id = await cache.ensure_exists("/Photos/Raw Files/")
        return cache, session, folder_id

    cache, session, folder_id = asyncio.run(run())

    assert folder_id == 3
    assert cache.synced_count == 2
    assert cache.id_cache == {"/": 1, "/Photos/": 2, "/Photos/Raw Files/": 3}
    assert [folder.full_path for folder in session.added] == ["/Photos/", "/Photos/Raw Files/"]
    assert [folder.marker_key for folder in session.added] == ["Photos/", "Photos/Raw Files/"]
    assert [folder.path.path for folder in session.added] == ["root.photos", "root.photos.raw_files"]


# Verifies cached orphaned folders are marked complete before reuse.
def test_folder_cache_restores_orphaned_folder():
    async def run():
        session = FakeFolderSession()
        cache = sync.FolderCache("bucket", session)
        cache.id_cache["/old/"] = 7
        cache.status_cache["/old/"] = "orphaned"

        folder_id = await cache.ensure_exists("/old/")
        return cache, session, folder_id

    cache, session, folder_id = asyncio.run(run())

    assert folder_id == 7
    assert cache.synced_count == 1
    assert cache.status_cache["/old/"] == "complete"
    assert session.restored_folder.status == "complete"


# Verifies sync_bucket turns S3 objects into DB file rows and skips folder markers.
def test_sync_bucket_builds_file_rows(monkeypatch):
    captured_batches = []
    cache_instances = []

    # Replace FolderCache so this stays a unit test and never opens a DB session.
    class FakeFolderCache:
        def __init__(self, bucket_name, session):
            self.bucket_name = bucket_name
            self.session = session
            self.synced_count = 0
            self.ids = {"/": 1}
            cache_instances.append(self)

        async def initialize(self):
            pass

        async def ensure_exists(self, full_path):
            if full_path not in self.ids:
                self.ids[full_path] = len(self.ids) + 1
                self.synced_count += 1
            return self.ids[full_path]

    async def fake_bulk_upsert_files(session, files_batch):
        captured_batches.append(files_batch)

    # Capture rows that would be sent to PostgreSQL instead of executing an upsert.
    monkeypatch.setattr(sync, "FolderCache", FakeFolderCache)
    monkeypatch.setattr(sync, "bulk_upsert_files", fake_bulk_upsert_files)

    async def run():
        agent = FakeAgent(
            pages=[
                {
                    "Contents": [
                        {"Key": "photos/", "Size": 0},
                        {"Key": "photos/cat.jpg", "Size": 12, "ETag": '"abc"'},
                        {"Key": "readme.txt", "Size": 5, "ETag": '"def"'},
                    ]
                }
            ]
        )
        session = FakeSession()
        summary = await sync.sync_bucket(agent, "bucket", session)
        return summary, session

    summary, session = asyncio.run(run())

    assert summary == sync.BucketSyncSummary(bucket="bucket", files_synced=2, folders_synced=1)
    assert session.commits == 2
    assert cache_instances[0].ids == {"/": 1, "/photos/": 2}
    assert captured_batches == [
        [
            {
                "bucket": "bucket",
                "folder_id": 2,
                "name": "cat.jpg",
                "key": "photos/cat.jpg",
                "size": 12,
                "etag": "abc",
                "last_modified": None,
                "status": "complete",
            },
            {
                "bucket": "bucket",
                "folder_id": 1,
                "name": "readme.txt",
                "key": "readme.txt",
                "size": 5,
                "etag": "def",
                "last_modified": None,
                "status": "complete",
            },
        ]
    ]


# Verifies sync_bucket writes and commits each object batch separately.
def test_sync_bucket_handles_multiple_batches(monkeypatch):
    captured_batches = []

    class FakeFolderCache:
        def __init__(self, bucket_name, session):
            self.synced_count = 0

        async def initialize(self):
            pass

        async def ensure_exists(self, full_path):
            return 1

    async def fake_bulk_upsert_files(session, files_batch):
        captured_batches.append([row["key"] for row in files_batch])

    monkeypatch.setattr(sync, "FolderCache", FakeFolderCache)
    monkeypatch.setattr(sync, "bulk_upsert_files", fake_bulk_upsert_files)

    async def run():
        agent = FakeAgent(
            pages=[
                {
                    "Contents": [
                        {"Key": "a.txt", "Size": 1},
                        {"Key": "b.txt", "Size": 2},
                    ]
                }
            ]
        )
        session = FakeSession()
        summary = await sync.sync_bucket(agent, "bucket", session, batch_size=1)
        return summary, session

    summary, session = asyncio.run(run())

    assert captured_batches == [["a.txt"], ["b.txt"]]
    assert session.commits == 3
    assert summary.files_synced == 2


# Verifies the top-level sync discovers buckets from the agent and totals summaries.
def test_sync_all_uses_agent_buckets(monkeypatch):
    seen_buckets = []

    async def fake_sync_bucket(agent, bucket_name, session):
        seen_buckets.append(bucket_name)
        return sync.BucketSyncSummary(bucket=bucket_name, files_synced=2, folders_synced=1)

    monkeypatch.setattr(sync, "sync_bucket", fake_sync_bucket)

    async def run():
        return await sync.sync_s3_agent_to_postgres(FakeAgent(buckets=["a", "b"]), object())

    summary = asyncio.run(run())

    assert seen_buckets == ["a", "b"]
    assert summary.bucket_count == 2
    assert summary.file_count == 4
    assert summary.folder_count == 2
