"""
Object Storage → PostgreSQL sync service.

Walks every object in an S3-compatible bucket, mirrors the folder hierarchy into
the Folder table (using PostgreSQL ltree paths), and bulk-upserts file metadata
into the File table.

NOTE: This is an add/update-only sync. Deletions are NOT handled.
"""

from __future__ import annotations

import logging
import posixpath
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.storage_agents.s3_agent import S3StorageAgent
from core.utils.paths import (
    join_child_full_path,
    normalize_folder_full_path,
    split_segments,
    to_ltree_label,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BucketSyncSummary:
    bucket: str
    files_synced: int
    folders_synced: int


@dataclass(frozen=True)
class ObjectStorageSyncSummary:
    """Aggregate summary of a full sync across all buckets."""

    buckets: list[BucketSyncSummary]

    @property
    def bucket_count(self) -> int:
        return len(self.buckets)

    @property
    def file_count(self) -> int:
        return sum(bucket.files_synced for bucket in self.buckets)

    @property
    def folder_count(self) -> int:
        return sum(bucket.folders_synced for bucket in self.buckets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_count": self.bucket_count,
            "file_count": self.file_count,
            "folder_count": self.folder_count,
            "buckets": [
                {
                    "bucket": bucket.bucket,
                    "files_synced": bucket.files_synced,
                    "folders_synced": bucket.folders_synced,
                }
                for bucket in self.buckets
            ],
        }


class FolderCache:
    """Cache folder IDs and ltree paths to avoid repeated lookups during sync."""

    def __init__(self, bucket_name: str, session: AsyncSession):
        self.bucket_name = bucket_name
        self.session = session
        # full_path -> folder.id
        self.id_cache: dict[str, Any] = {}
        # full_path -> Ltree instance
        self.ltree_cache: dict[str, Any] = {}
        # full_path -> status string ("complete", etc.)
        self.status_cache: dict[str, str] = {}
        self.synced_count = 0

    async def initialize(self) -> None:
        """
        Ensure the bucket root folder exists and load all existing folders into
        the in-memory caches.
        """
        # Ensure the root folder "/" exists for this bucket.
        q_root = select(Folder).where(Folder.bucket == self.bucket_name, Folder.full_path == "/")
        res_root = await self.session.execute(q_root)
        root = res_root.scalar_one_or_none()

        if not root:
            # Upsert so concurrent sync workers do not race creating the same root.
            stmt = insert(Folder).values(
                bucket=self.bucket_name,
                parent_id=None,
                name="/",
                path=Ltree("root"),
                full_path="/",
                status="complete",
            ).on_conflict_do_update(
                index_elements=["bucket", "full_path"],
                set_={"status": "complete"},
            )
            await self.session.execute(stmt)
            self.synced_count += 1
        elif root.status != "complete":
            # Restore the root folder to "complete" if it was previously orphaned.
            root.status = "complete"
            self.synced_count += 1

        # Pre-load every folder in this bucket into the caches.
        query = select(Folder.id, Folder.full_path, Folder.path, Folder.status).where(Folder.bucket == self.bucket_name)
        res = await self.session.execute(query)
        for folder_id, full_path, path, status in res:
            self.id_cache[full_path] = folder_id
            self.ltree_cache[full_path] = path
            self.status_cache[full_path] = status

    async def ensure_exists(self, full_path: str) -> Any:
        """
        Return the folder ID for *full_path*, creating the folder (and any
        missing ancestor folders) if necessary.
        """
        full_path = normalize_folder_full_path(full_path)

        # Fast path: folder is already cached.
        if full_path in self.id_cache:
            # If the folder was previously marked as orphaned, restore it.
            if self.status_cache.get(full_path) != "complete":
                folder = await self.session.get(Folder, self.id_cache[full_path])
                folder.status = "complete"
                self.status_cache[full_path] = "complete"
                self.synced_count += 1
            return self.id_cache[full_path]

        # Walk down from root, creating any missing segments along the way.
        current_path = "/"
        for segment in split_segments(full_path):
            parent_path = current_path
            current_path = join_child_full_path(parent_path, segment)

            # Segment already exists — skip creation.
            if current_path in self.id_cache:
                continue

            parent_id = self.id_cache[parent_path]
            parent_ltree = self.ltree_cache[parent_path]
            # Upsert the folder and return the winning row for the local cache.
            stmt = insert(Folder).values(
                bucket=self.bucket_name,
                parent_id=parent_id,
                name=segment,
                path=Ltree(f"{parent_ltree.path}.{to_ltree_label(segment)}"),
                full_path=current_path,
                marker_key=current_path.lstrip("/"),
                status="complete",
            ).on_conflict_do_update(
                index_elements=["bucket", "full_path"],
                set_={"status": "complete"},
            ).returning(Folder.id, Folder.path, Folder.status)
            folder_id, folder_path, folder_status = (await self.session.execute(stmt)).one()

            # Cache the newly created folder for subsequent lookups.
            self.id_cache[current_path] = folder_id
            self.ltree_cache[current_path] = folder_path
            self.status_cache[current_path] = folder_status
            self.synced_count += 1

        return self.id_cache[full_path]


async def bulk_upsert_files(session: AsyncSession, files_batch: list[dict[str, Any]]) -> None:
    """
    Insert or update a batch of file records using PostgreSQL

    Conflict is detected on the composite key (bucket, key). When a row already
    exists, the size, etag, last_modified, folder_id, name, and status columns
    are refreshed from the incoming data.
    """
    if not files_batch:
        return

    stmt = insert(File).values(files_batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["bucket", "key"],
        set_={
            col: getattr(stmt.excluded, col)
            for col in ["size", "etag", "last_modified", "folder_id", "name", "status"]
        },
    )
    await session.execute(stmt)


async def iter_s3_object_batches(
    agent: S3StorageAgent,
    bucket_name: str,
    batch_size: int = 1000,
) -> AsyncIterator[list[dict[str, Any]]]:
    """
    Yield batches of raw objects from an S3-compatible bucket.

    This keeps S3 pagination separate from folder path computation and database
    writes so callers can test object fetching in isolation.
    """
    paginator = agent.s3_client.get_paginator("list_objects_v2")
    objects_batch: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            objects_batch.append(obj)

            if len(objects_batch) >= batch_size:
                yield objects_batch
                objects_batch = []

    if objects_batch:
        yield objects_batch


async def sync_bucket(
    agent: S3StorageAgent,
    bucket_name: str,
    session: AsyncSession,
    batch_size: int = 1000,
) -> BucketSyncSummary:
    """Sync all objects from a single S3 bucket into the database.

    NOTE: Add/update only. Deletions are NOT handled.
    """
    logger.info("Starting object storage sync for bucket: %s", bucket_name)

    # Load the existing folder tree into an in-memory cache.
    cache = FolderCache(bucket_name, session)
    await cache.initialize()

    total_files = 0

    async for objects_batch in iter_s3_object_batches(agent, bucket_name, batch_size=batch_size):
        files_batch: list[dict[str, Any]] = []

        for obj in objects_batch:
            key = obj["Key"]
            size = obj.get("Size", 0)

            # Zero-byte keys ending in "/" are S3 folder markers — ensure the
            # corresponding Folder row exists, but don't create a File row.
            if key.endswith("/") and size == 0:
                await cache.ensure_exists(normalize_folder_full_path("/" + key))
                continue

            # Split the key into its parent folder path and filename.
            folder_part, filename = posixpath.split(key)
            folder_id = await cache.ensure_exists(normalize_folder_full_path("/" + folder_part))
            files_batch.append(
                {
                    "bucket": bucket_name,
                    "folder_id": folder_id,
                    "name": filename or folder_part,
                    "key": key,
                    "size": size,
                    "etag": obj.get("ETag", "").strip('"'),
                    "last_modified": obj.get("LastModified"),
                    "status": "complete",
                }
            )

            total_files += 1

        await bulk_upsert_files(session, files_batch)
        await session.commit()
        logger.info("[%s] Synced %s files...", bucket_name, total_files)

    await session.commit()

    logger.info(
        "Finished object storage sync for bucket %s: %s files, %s folders",
        bucket_name,
        total_files,
        cache.synced_count,
    )
    return BucketSyncSummary(
        bucket=bucket_name,
        files_synced=total_files,
        folders_synced=cache.synced_count,
    )


async def sync_s3_agent_to_postgres(
    agent: S3StorageAgent,
    session: AsyncSession,
    bucket_names: Iterable[str] | None = None,
) -> ObjectStorageSyncSummary:
    """Sync objects from all (or specified) S3 buckets into the database.

    NOTE: Add/update only. Deletions are NOT handled.
    """
    buckets = list(bucket_names) if bucket_names is not None else agent.fetch_all_buckets()
    summaries = []

    for bucket_name in buckets:
        summaries.append(await sync_bucket(agent, bucket_name, session))

    return ObjectStorageSyncSummary(buckets=summaries)
