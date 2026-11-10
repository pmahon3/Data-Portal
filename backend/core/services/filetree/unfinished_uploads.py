"""
Clear uploads left unfinished after a set time (PX-6).

An upload starts by adding a pending file row, and pending folder rows for any new folders of a
folder upload, then the browser sends the bytes straight to storage. When it never finishes, the rows
stay pending and hidden. After a set time, each pending file is checked in storage:

- the object is there: the file arrived whole, so it's kept and marked complete with its folders;
- the object isn't there: the row is removed, then any pending folder left empty.

Storage is asked per bucket through the storage instance that holds it. A file whose bucket no
instance holds, or whose check fails, is left for the next run.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.services.filetree.file_service import FileService
from core.services.filetree.models.file import File
from core.services.filetree.models.folder import Folder
from core.services.filetree.tree_service import TreeService
from core.services.instances import AbstractInstanceManager
from core.storage_agents.abstract_storage_agent import AbstractStorageAgent

logger = logging.getLogger("unfinished_uploads")

# An upload unfinished this long after it began is cleared. The value is open (PX-6 says "a set time");
# it must outlast the longest upload link, or a slow upload could be cleared while it runs.
UNFINISHED_UPLOAD_HOURS = float(os.getenv("UNFINISHED_UPLOAD_HOURS", "24"))
UNFINISHED_UPLOAD_CHECK_MINUTES = float(os.getenv("UNFINISHED_UPLOAD_CHECK_MINUTES", "60"))
LONGEST_UPLOAD_LINK_SECONDS = max(int(os.getenv("FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS", "7200")), 900)

# Files checked per run, so one run stays short; the rest wait for the next
BATCH_SIZE = 500

# HeadObject answers these codes when the object isn't there
NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def is_not_found(exc: ClientError) -> bool:
    """Return whether a storage error means the object isn't there."""
    return str(exc.response.get("Error", {}).get("Code")) in NOT_FOUND_CODES


async def agents_by_bucket(instance_manager: AbstractInstanceManager) -> dict[str, AbstractStorageAgent]:
    """
    Return the storage agent that holds each bucket, for the S3-like instances. An instance that
    can't be reached is skipped, so its files wait for the next run and the others go ahead.

    Example: {"bundle": <S3StorageAgent for qa-instance>}
    """
    agents = {}
    for instance in instance_manager.instances:
        agent = instance.agent
        if not hasattr(agent, "fetch_all_buckets"):
            continue
        try:
            # Listing buckets calls storage, so it runs in a thread, as the checks below do
            buckets = await asyncio.to_thread(agent.fetch_all_buckets)
        except Exception as exc:
            logger.warning("Could not list the buckets of a storage instance; skipped this run: %s", exc)
            continue
        for bucket in buckets:
            agents[bucket] = agent
    return agents


def set_time() -> timedelta:
    """Return the set time from the settings, never shorter than the longest upload link."""
    configured = timedelta(hours=UNFINISHED_UPLOAD_HOURS)
    floor = timedelta(seconds=LONGEST_UPLOAD_LINK_SECONDS)
    if configured < floor:
        logger.warning(
            "UNFINISHED_UPLOAD_HOURS=%s is shorter than the longest upload link; using %s",
            UNFINISHED_UPLOAD_HOURS,
            floor,
        )
        return floor
    return configured


async def clear_unfinished_uploads(
    session: AsyncSession,
    instance_manager: AbstractInstanceManager,
    older_than: timedelta,
) -> dict[str, int]:
    """
    Clear uploads unfinished for longer than ``older_than``, and return how many files were kept
    and removed and how many folders were removed. Safe to run in several processes at once.
    """
    cutoff = datetime.now(timezone.utc) - older_than
    # Older rows have no pending_since; their upload began when they were created
    started = func.coalesce(File.pending_since, File.created_at)
    unfinished = (await session.execute(
        select(File)
        .where(File.status == "pending", started < cutoff)
        .order_by(File.id)
        .limit(BATCH_SIZE)
    )).scalars().all()

    agents = await agents_by_bucket(instance_manager)
    arrived: list[dict] = []
    arrived_folders: set[tuple[str, int]] = set()
    missing_ids: list[int] = []

    for file in unfinished:
        agent = agents.get(file.bucket)
        if agent is None:
            continue
        try:
            # The agent takes a "bucket/key" resource, as the upload endpoints build it. The check
            # blocks, so it runs in a thread and requests aren't held up meanwhile.
            head = await asyncio.to_thread(agent.get_object_metadata, f"{file.bucket}/{file.key}")
        except ClientError as exc:
            if is_not_found(exc):
                missing_ids.append(file.id)
            else:
                logger.warning(
                    "Could not check %s/%s in storage; left for the next run: %s",
                    file.bucket,
                    file.key,
                    exc,
                )
            continue
        arrived.append({
            "id": file.id,
            "size": head.get("ContentLength"),
            "etag": head.get("ETag"),
            "last_modified": head.get("LastModified"),
            "content_type": head.get("ContentType", file.content_type),
            "status": "complete",
        })
        arrived_folders.add((file.bucket, file.folder_id))

    # Kept: the file arrived whole, so it and its folders are shown
    await FileService(session).update_many_from_head(arrived)
    tree_svc = TreeService(session)
    for bucket, folder_id in arrived_folders:
        await tree_svc.mark_folder_ancestors_complete(bucket, folder_id)

    # Removed: checked again here, so an upload started again since the check is left alone
    removed = 0
    if missing_ids:
        result = await session.execute(
            delete(File).where(File.id.in_(missing_ids), File.status == "pending", started < cutoff)
        )
        removed = result.rowcount or 0
        await session.commit()

    folders_removed = await remove_empty_pending_folders(session, cutoff)

    counts = {"kept": len(arrived), "removed": removed, "folders_removed": folders_removed}
    if any(counts.values()):
        logger.info(
            "Unfinished uploads: kept %s file(s) that arrived, removed %s file(s) and %s folder(s)",
            counts["kept"],
            counts["removed"],
            counts["folders_removed"],
        )
    return counts


async def remove_empty_pending_folders(session: AsyncSession, cutoff: datetime) -> int:
    """
    Remove pending folders made before ``cutoff`` that hold no files or folders, deepest first, and
    return how many. Deleting a folder deletes what's in it, so only empty ones go.
    """
    child = Folder.__table__.alias("child")
    total = 0
    while True:
        result = await session.execute(
            delete(Folder).where(
                Folder.status == "pending",
                Folder.created_at < cutoff,
                ~exists().where(File.folder_id == Folder.id),
                ~exists().where(child.c.parent_id == Folder.id),
            )
        )
        await session.commit()
        if not result.rowcount:
            return total
        total += result.rowcount


async def clear_unfinished_uploads_periodically(
    sessions: async_sessionmaker,
    instance_manager: AbstractInstanceManager,
) -> None:
    """Clear unfinished uploads every UNFINISHED_UPLOAD_CHECK_MINUTES, until cancelled."""
    older_than = set_time()
    while True:
        try:
            async with sessions() as session:
                await clear_unfinished_uploads(session, instance_manager, older_than)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One failed run mustn't stop the next
            logger.exception("Clearing unfinished uploads failed")
        await asyncio.sleep(UNFINISHED_UPLOAD_CHECK_MINUTES * 60)
