"""
S3 to PostgreSQL Asset Sync Utility
-----------------------------------
Synchronizes S3/MinIO bucket contents into the PostgreSQL folders/files tables.

Usage inside the backend container:
    python core/db/postgres/scripts/sync_s3_postgres.py

This script is intentionally a thin wrapper around the reusable sync service so
cron/manual runs and application-triggered syncs share the same behavior.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[4]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.db import AsyncSessionMaker
from core.services.filetree.object_storage_sync import sync_s3_agent_to_postgres

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_sync_all() -> None:
    from core.services.injectors import get_instance_manager

    instances = get_instance_manager().instances
    if not instances:
        logger.warning("No storage instances found.")
        return

    async with AsyncSessionMaker() as session:
        for instance in instances:
            logger.info("Processing instance: %s (UUID: %s)", instance.name, instance.uuid)

            if instance.flavour != "s3":
                logger.debug("Skipping %s - flavour %r is not S3 compatible.", instance.name, instance.flavour)
                continue

            try:
                summary = await sync_s3_agent_to_postgres(instance.agent, session)
                logger.info(
                    "Finished instance %s sync: %s buckets, %s files, %s folders",
                    instance.name,
                    summary.bucket_count,
                    summary.file_count,
                    summary.folder_count,
                )
            except Exception as e:
                await session.rollback()
                logger.error(
                    "Error processing instance %s (UUID: %s): %s",
                    instance.name,
                    instance.uuid,
                    e,
                    exc_info=True,
                )


def main() -> None:
    argparse.ArgumentParser(description="Sync S3 objects to Postgres.").parse_args()
    asyncio.run(run_sync_all())


if __name__ == "__main__":
    main()
