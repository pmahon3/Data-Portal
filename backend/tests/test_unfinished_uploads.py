"""
Unfinished uploads are cleared after a set time (PX-6).

An upload that never finished leaves a pending file row, and pending folder rows for a folder upload.
After a set time, a pending file whose object is in storage is kept and marked complete (it arrived
whole); one whose object isn't there is removed, with any pending folder left empty.

Needs a PostgreSQL server: set TEST_DATABASE_URL to postgresql://user:password@host:5432/postgres
for a user that may create databases. Skipped when it isn't set.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
SCHEMA_SQL = Path(__file__).resolve().parents[1] / "core/db/postgres/scripts/schema.sql"
BUCKET = "bundle"
SET_TIME = timedelta(hours=24)

pytestmark = [
    pytest.mark.skipif(not ADMIN_URL, reason="needs a PostgreSQL server: set TEST_DATABASE_URL"),
    pytest.mark.xfail(strict=True, raises=ImportError, reason="unfinished uploads are never cleared"),
]

# The database session module builds its engine on import, from DATABASE_URL
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost:5432/unused")


class FakeAgent:
    """An S3-like storage agent holding the given objects; any other key is not found."""

    def __init__(self, objects: dict[str, int], error: Exception | None = None):
        self.objects = objects
        self.error = error

    def fetch_all_buckets(self) -> list[str]:
        return [BUCKET]

    def get_object_metadata(self, resource: str) -> dict:
        if self.error:
            raise self.error
        bucket, key = resource.split("/", 1)
        if bucket != BUCKET or key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {
            "ContentLength": self.objects[key],
            "ETag": '"abc"',
            "LastModified": datetime.now(timezone.utc),
            "ContentType": "text/plain",
        }


class FakeInstanceManager:
    def __init__(self, agent: FakeAgent):
        self.instances = [type("Instance", (), {"agent": agent})()]


def run_clear(agent: FakeAgent, rows_sql: str) -> dict[str, list]:
    """
    Create a blank database with the schema, add the rows, clear unfinished uploads, and return
    what's left.
    """
    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.services.filetree.unfinished_uploads import clear_unfinished_uploads

    async def run():
        name = f"uploads_{uuid.uuid4().hex[:12]}"
        base = ADMIN_URL.rsplit("/", 1)[0]
        admin = await asyncpg.connect(ADMIN_URL)
        await admin.execute(f'CREATE DATABASE "{name}"')
        db = await asyncpg.connect(f"{base}/{name}")
        engine = create_async_engine(f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{name}")
        try:
            await db.execute(SCHEMA_SQL.read_text())
            await db.execute(rows_sql)
            sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with sessions() as session:
                await clear_unfinished_uploads(session, FakeInstanceManager(agent), SET_TIME)
            files = await db.fetch("SELECT key, status, size FROM files ORDER BY key")
            folders = await db.fetch("SELECT full_path, status FROM folders ORDER BY full_path")
            return {
                "files": [(r["key"], r["status"], r["size"]) for r in files],
                "folders": [(r["full_path"], r["status"]) for r in folders],
            }
        finally:
            await db.close()
            await engine.dispose()
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.close()

    return asyncio.run(run())


# A bucket root, a folder that already existed, and a folder a folder upload created (still pending).
# Each test adds its files to the new folder.
FOLDERS = f"""
INSERT INTO folders (id, bucket, parent_id, name, path, full_path, status, created_at) VALUES
  (1, '{BUCKET}', NULL, '/', 'root', '/', 'complete', now() - interval '30 days'),
  (2, '{BUCKET}', 1, 'study', 'root.study', '/study/', 'complete', now() - interval '30 days'),
  (3, '{BUCKET}', 2, 'new', 'root.study.new', '/study/new/', 'pending', now() - interval '2 days');
"""


def a_file(key: str, status: str, started_ago: str, created_ago: str | None = None) -> str:
    """
    Return SQL adding a file in the new folder. ``started_ago`` is when its upload began; a file
    whose upload began again after it was created has ``created_ago`` too.

    Example: a_file("study/new/a.txt", "pending", "2 days")
    """
    created = created_ago or started_ago
    return (
        "INSERT INTO files (bucket, folder_id, name, key, status, created_at, pending_since) VALUES "
        f"('{BUCKET}', 3, '{key.rsplit('/', 1)[-1]}', '{key}', '{status}', "
        f"now() - interval '{created}', now() - interval '{started_ago}');"
    )


def test_an_unfinished_upload_is_cleared_after_the_set_time():
    """A file that never arrived is removed, and so is the folder the upload created."""
    left = run_clear(FakeAgent({}), FOLDERS + a_file("study/new/a.txt", "pending", "2 days"))
    assert left["files"] == []
    assert left["folders"] == [("/", "complete"), ("/study/", "complete")]


def test_a_file_that_arrived_whole_is_kept():
    """A pending file whose object is in storage is marked complete, and so is its folder."""
    left = run_clear(FakeAgent({"study/new/a.txt": 12}), FOLDERS + a_file("study/new/a.txt", "pending", "2 days"))
    assert left["files"] == [("study/new/a.txt", "complete", 12)]
    assert ("/study/new/", "complete") in left["folders"]


def test_a_partial_folder_upload_keeps_the_files_that_arrived():
    """Of a folder upload, the files that arrived are kept and the rest are removed."""
    rows = FOLDERS + a_file("study/new/a.txt", "pending", "2 days") + a_file("study/new/b.txt", "pending", "2 days")
    left = run_clear(FakeAgent({"study/new/a.txt": 12}), rows)
    assert left["files"] == [("study/new/a.txt", "complete", 12)]
    assert ("/study/new/", "complete") in left["folders"]


def test_an_upload_within_the_set_time_is_left_alone():
    """An upload is cleared only after the set time, counted from when it last started."""
    rows = FOLDERS + a_file("study/new/a.txt", "pending", "1 hour", created_ago="3 days")
    left = run_clear(FakeAgent({}), rows)
    assert left["files"] == [("study/new/a.txt", "pending", None)]
    assert ("/study/new/", "pending") in left["folders"]


def test_complete_files_are_never_touched():
    """Only pending rows are cleared, even when storage doesn't have the object."""
    left = run_clear(FakeAgent({}), FOLDERS + a_file("study/new/a.txt", "complete", "5 days"))
    assert left["files"] == [("study/new/a.txt", "complete", None)]


def test_a_storage_error_removes_nothing():
    """When storage can't be asked, a pending file is kept for the next run."""
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "HeadObject")
    left = run_clear(FakeAgent({}, error=error), FOLDERS + a_file("study/new/a.txt", "pending", "2 days"))
    assert left["files"] == [("study/new/a.txt", "pending", None)]
    assert ("/study/new/", "pending") in left["folders"]
