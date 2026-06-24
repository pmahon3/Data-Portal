"""
Apply object-storage notification rows to the folders/files tables.

Usage inside the backend container:
    python storage_events_worker/process_storage_events.py

Optional watch mode:
    python storage_events_worker/process_storage_events.py --watch --interval 10
"""

from __future__ import annotations

import argparse
import asyncio
import posixpath
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from core.utils.paths import build_ltree_path, normalize_folder_full_path, split_segments
from storage_events_worker.db import AsyncSessionMaker, files, folders, storage_events


def is_folder_key(key: str) -> bool:
    return key.endswith("/")


def folder_path_from_key(key: str) -> str:
    """Convert a folder marker key to a normalized folder path.

    Example:
        "project/data/" -> "/project/data/"
    """
    return normalize_folder_full_path("/" + key.strip("/"))


def file_parts_from_key(key: str) -> tuple[str, str]:
    """Return normalized parent folder path and filename for an object key.

    Example:
        "project/data/report.csv" -> ("/project/data/", "report.csv")
    """
    folder_part, filename = posixpath.split(key.strip("/"))
    if not filename:
        raise ValueError(f"Object key does not contain a file name: {key!r}")
    return normalize_folder_full_path("/" + folder_part), filename


class StorageEventProcessor:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_pending_events(self, limit: int) -> list[dict[str, Any]]:
        # Oldest first keeps create/delete sequences in receive order.
        result = await self.session.execute(
            select(storage_events)
            .where(storage_events.c.status == "pending")
            .order_by(storage_events.c.created_at, storage_events.c.id)
            .limit(limit)
        )
        return [dict(row) for row in result.mappings().all()]

    async def process_batch(self, limit: int) -> int:
        events = await self.fetch_pending_events(limit)
        for event in events:
            await self.process_event(event)
        return len(events)

    async def process_event(self, event: dict[str, Any]) -> None:
        if event["status"] != "pending":
            return

        event_id = event["id"]
        try:
            if event["action"] == "created":
                await self.apply_created(event)
            elif event["action"] == "removed":
                await self.apply_removed(event)
            else:
                raise ValueError(f"Unsupported storage event action: {event['action']!r}")

            # Commit the file/folder change and event status together.
            await self.session.execute(
                update(storage_events)
                .where(storage_events.c.id == event_id)
                .values(status="processed", processed_at=datetime.now(timezone.utc), error_message=None)
            )
            await self.session.commit()
            logger.info("Processed event id={} action={} key={}", event_id, event["action"], event["object_key"])
        except Exception as exc:
            await self.session.rollback()
            await self.mark_failed(event_id, exc)

    async def mark_failed(self, event_id: int, exc: Exception) -> None:
        await self.session.execute(
            update(storage_events)
            .where(storage_events.c.id == event_id)
            .values(
                status="failed",
                retry_count=storage_events.c.retry_count + 1,
                error_message=str(exc),
                processed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()
        logger.error("Failed event id={}: {}", event_id, exc)

    async def apply_created(self, event: dict[str, Any]) -> None:
        if is_folder_key(event["object_key"]):
            folder = await self.ensure_folder(event["bucket"], folder_path_from_key(event["object_key"]))
            await self.session.execute(
                update(folders).where(folders.c.id == folder["id"]).values(marker_key=event["object_key"])
            )
            return

        folder_full_path, filename = file_parts_from_key(event["object_key"])
        folder = await self.ensure_folder(event["bucket"], folder_full_path)
        values = {
            "bucket": event["bucket"],
            "folder_id": folder["id"],
            "name": filename,
            "key": event["object_key"],
            "size": event["size"],
            "etag": event["etag"],
            "last_modified": event["event_time"],
        }
        stmt = insert(files).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["bucket", "key"],
            set_={
                "folder_id": stmt.excluded.folder_id,
                "name": stmt.excluded.name,
                "size": stmt.excluded.size,
                "etag": stmt.excluded.etag,
                "last_modified": stmt.excluded.last_modified,
            },
        )
        await self.session.execute(stmt)

    async def apply_removed(self, event: dict[str, Any]) -> None:
        if is_folder_key(event["object_key"]):
            full_path = folder_path_from_key(event["object_key"])
            if full_path == "/":
                raise ValueError("Refusing to delete bucket root folder")
            # Postgres cascades this delete to child folders/files through FKs.
            await self.session.execute(
                delete(folders).where(folders.c.bucket == event["bucket"], folders.c.full_path == full_path)
            )
            return

        await self.session.execute(
            delete(files).where(files.c.bucket == event["bucket"], files.c.key == event["object_key"])
        )

    async def ensure_folder(self, bucket: str, full_path: str) -> dict[str, Any]:
        full_path = normalize_folder_full_path(full_path)
        existing = await self.get_folder(bucket, full_path)
        if existing is not None:
            return existing

        if full_path == "/":
            result = await self.session.execute(
                folders.insert()
                .values(bucket=bucket, parent_id=None, name="/", path=Ltree("root"), full_path="/")
                .returning(folders)
            )
            return dict(result.mappings().one())

        # Break "/project/data/" into ["project", "data"] so we can attach
        # the new folder to the correct parent and build its ltree path.
        segments = split_segments(full_path)
        parent_path = "/" if len(segments) == 1 else normalize_folder_full_path("/" + "/".join(segments[:-1]))
        parent = await self.ensure_folder(bucket, parent_path)
        result = await self.session.execute(
            folders.insert()
            .values(
                bucket=bucket,
                parent_id=parent["id"],
                name=segments[-1],
                path=Ltree(build_ltree_path(segments)),
                full_path=full_path,
            )
            .returning(folders)
        )
        return dict(result.mappings().one())

    async def get_folder(self, bucket: str, full_path: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(folders).where(folders.c.bucket == bucket, folders.c.full_path == full_path)
        )
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None


async def log_status(session: AsyncSession) -> None:
    result = await session.execute(
        select(storage_events.c.status, func.count(storage_events.c.id)).group_by(storage_events.c.status)
    )
    counts = {status: count for status, count in result.all()}
    logger.info("storage_events status: {}", counts)


async def run_once(batch_size: int) -> int:
    # Nomad periodic batch mode: process one bounded batch, log status, exit.
    async with AsyncSessionMaker() as session:
        await log_status(session)
        processor = StorageEventProcessor(session)
        processed = await processor.process_batch(batch_size)
        await log_status(session)
        return processed


async def run(args: argparse.Namespace) -> None:
    while True:
        processed = await run_once(args.batch_size)

        if not args.watch:
            return

        # Watch mode drains backlogs immediately and sleeps only while idle.
        if processed == 0:
            await asyncio.sleep(args.interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply pending object-storage events to Postgres folders/files tables."
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Maximum pending events to process per pass.")
    parser.add_argument("--watch", action="store_true", help="Keep polling for new pending events.")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds to wait between empty watch passes.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
