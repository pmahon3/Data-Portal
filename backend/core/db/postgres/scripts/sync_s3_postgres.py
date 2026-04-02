"""
S3 to PostgreSQL Asset Sync Utility
--------------------------------------
This script synchronizes assets (files/folders) from all 
configured S3/MinIO buckets into the PostgreSQL 'files' and 'folders' tables.

Usage (Inside Docker):
    $ docker exec -it ams-backend python core/db/postgres/scripts/sync_s3_postgres.py

Note:
    This script must be run within the backend container to access the 
    InstanceManager, database connections, and environment variables.

    DELETE operations not supported. If something is deleted from object storage 
    that will not be synced.

    Generated with Gemini. Brief testing for MinIO confirms it working
"""

import asyncio
import os
import sys
import argparse
import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

# Ensure the backend directory is in the python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.db import AsyncSessionMaker
from core.services.filetree.models.folder import Folder
from core.services.filetree.models.file import File
from core.storage_agents.s3_agent import S3StorageAgent
from core.util.paths import (
    normalize_folder_full_path,
    split_segments,
    to_ltree_label,
    join_child_full_path,
)

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class FolderCache:
    """Cache to store folder IDs and Ltree paths to minimize database lookups."""
    def __init__(self, bucket_name: str, session: AsyncSession):
        self.bucket_name = bucket_name
        self.session = session
        self.id_cache: Dict[str, Any] = {}
        self.ltree_cache: Dict[str, Any] = {}

    async def initialize(self):
        """Pre-populate cache and ensure root exists."""
        # 1. Ensure Root
        q_root = select(Folder).where(Folder.bucket == self.bucket_name, Folder.full_path == "/")
        res_root = await self.session.execute(q_root)
        root = res_root.scalar_one_or_none()

        if not root:
            root = Folder(
                bucket=self.bucket_name,
                parent_id=None,
                name="/",
                path=Ltree("root"),
                full_path="/",
            )
            self.session.add(root)
            await self.session.flush() # Get the ID without full commit
        
        # 2. Load all existing folders into memory
        q = select(Folder.id, Folder.full_path, Folder.path).where(Folder.bucket == self.bucket_name)
        res = await self.session.execute(q)
        for f_id, f_full_path, f_path in res:
            self.id_cache[f_full_path] = f_id
            self.ltree_cache[f_full_path] = f_path

    async def ensure_exists(self, full_path: str) -> Any:
        """Returns folder ID, creating hierarchy if missing."""
        full_path = normalize_folder_full_path(full_path)
        if full_path in self.id_cache:
            return self.id_cache[full_path]

        segments = split_segments(full_path)
        current_path = "/"
        
        for seg in segments:
            parent_path = current_path
            current_path = join_child_full_path(parent_path, seg)
            
            if current_path not in self.id_cache:
                parent_id = self.id_cache[parent_path]
                parent_ltree = self.ltree_cache[parent_path]
                
                new_folder = Folder(
                    bucket=self.bucket_name,
                    parent_id=parent_id,
                    name=seg,
                    path=Ltree(f"{parent_ltree.path}.{to_ltree_label(seg)}"),
                    full_path=current_path,
                    marker_key=current_path.lstrip("/")
                )
                self.session.add(new_folder)
                await self.session.flush() # Flush once per new segment level
                
                self.id_cache[current_path] = new_folder.id
                self.ltree_cache[current_path] = new_folder.path
        
        return self.id_cache[full_path]


async def bulk_upsert_files(session: AsyncSession, files_batch: List[Dict[str, Any]]):
    """Executes an optimized PostgreSQL upsert."""
    if not files_batch:
        return
        
    stmt = insert(File).values(files_batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=['bucket', 'key'],
        set_={col: getattr(stmt.excluded, col) for col in ['size', 'etag', 'last_modified', 'folder_id', 'name']}
    )
    await session.execute(stmt)


async def process_bucket(agent: S3StorageAgent, bucket_name: str, session: AsyncSession):
    """Handles the synchronization of a single bucket."""
    logger.info(f"Starting sync for bucket: {bucket_name}")
    
    cache = FolderCache(bucket_name, session)
    await cache.initialize()

    paginator = agent.s3_client.get_paginator('list_objects_v2')
    total_objects = 0
    files_batch = []
    BATCH_SIZE = 500

    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get('Contents', []):
            key = obj['Key']
            size = obj.get('Size', 0)
            
            # Use os.path logic for cleaner parsing
            folder_part, filename = os.path.split(key)
            folder_str = normalize_folder_full_path("/" + folder_part)

            # Case: Folder Marker
            if key.endswith("/") and size == 0:
                await cache.ensure_exists(normalize_folder_full_path("/" + key))
                continue

            # Case: File
            folder_id = await cache.ensure_exists(folder_str)
            files_batch.append({
                "bucket": bucket_name,
                "folder_id": folder_id,
                "name": filename or folder_part,
                "key": key,
                "size": size,
                "etag": obj.get('ETag', '').strip('"'),
                "last_modified": obj.get('LastModified'),
            })
            
            total_objects += 1
            if len(files_batch) >= BATCH_SIZE:
                await bulk_upsert_files(session, files_batch)
                files_batch.clear()
                await session.commit()
                logger.info(f"[{bucket_name}] Synced {total_objects} files...")

    if files_batch:
        await bulk_upsert_files(session, files_batch)
        await session.commit()
        
    logger.info(f"Finished bucket {bucket_name}. Total: {total_objects}")


async def run_sync_all():
    """Main orchestrator for syncing all instances."""
    from core.services.injectors import get_instance_manager
    instances = get_instance_manager().instances
    
    if not instances:
        logger.warning("No storage instances found.")
        return
        
    async with AsyncSessionMaker() as session:
        for instance in instances:
            logger.info(f"Processing instance: {instance.name} (UUID: {instance.uuid})")
            
            if instance.flavour != 's3':
                logger.debug(f"Skipping {instance.name} - Flavour '{instance.flavour}' is not S3 compatible.")
                continue

            agent: S3StorageAgent = instance.agent
                
            try:
                buckets = agent.fetch_all_buckets()
                for bucket_name in (buckets or []):
                    await process_bucket(agent, bucket_name, session)
            except Exception as e:
                logger.error(f"Error processing instance {instance.name} (UUID: {instance.uuid}): {e}", exc_info=True)

def main():
    argparse.ArgumentParser(description="Sync S3 objects to Postgres.").parse_args()
    asyncio.run(run_sync_all())

if __name__ == "__main__":
    main()