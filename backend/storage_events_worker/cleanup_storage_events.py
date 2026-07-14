"""
Delete old processed object-storage event rows.

Usage inside the backend container:
    python storage_events_worker/cleanup_storage_events.py
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from storage_events_worker.db import AsyncSessionMaker, storage_events


async def cleanup_processed_events(session: AsyncSession, retention_days: int) -> int:
    if retention_days <= 0:
        logger.info("Storage event cleanup disabled because retention_days={}", retention_days)
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await session.execute(
        delete(storage_events).where(
            storage_events.c.status == "processed",
            storage_events.c.processed_at < cutoff,
        )
    )
    deleted = result.rowcount or 0
    await session.commit()
    logger.info("Deleted {} processed storage_events older than {} days", deleted, retention_days)
    return deleted


async def run(args: argparse.Namespace) -> None:
    async with AsyncSessionMaker() as session:
        await cleanup_processed_events(session, args.retention_days)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete old processed storage_events rows.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Delete processed storage_events older than this many days. Use 0 to disable cleanup.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
