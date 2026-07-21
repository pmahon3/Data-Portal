**Last Updated:** 2026-07-21

# Filetree Service

Manages files and folders in the INN Data Portal, providing a hierarchical view of
data stored in S3-compatible object storage. The service consists of three main
components:

- **Tree Service** (`tree_service.py`) - CRUD operations on folders using PostgreSQL
  `ltree` paths for efficient hierarchical queries.
- **File Service** (`file_service.py`) - CRUD operations on individual file metadata
  records.
- **Object Storage Sync** (`object_storage_sync.py`) - One-way synchronisation from
  S3-compatible buckets into the PostgreSQL database.

---

## Object Storage Sync

### What It Does

The object storage sync walks every object in one or more S3-compatible buckets and
mirrors the complete folder/file hierarchy into PostgreSQL.

**Key behaviours:**

1. **Folder hierarchy mirroring** - For every object key (e.g., `photos/2024/cat.jpg`),
   the sync ensures a corresponding chain of `Folder` rows exists in the database:
   `/` → `/photos/` → `/photos/2024/`. Folder paths are stored as PostgreSQL `ltree`
   values for efficient tree traversal.

2. **File metadata upsert** - Each S3 object (that is not a zero-byte folder marker)
   is bulk-upserted into the `File` table. The upsert uses the composite key
   `(bucket, key)` so that re-running the sync updates existing records (size, etag,
   last_modified, folder_id, name, status) without creating duplicates.

3. **Folder marker handling** - Zero-byte S3 keys ending in `/` are recognised as
   S3 folder markers. They cause a `Folder` row to be created but are **not** stored
   as `File` rows.

4. **Orphaned folder restoration** - If a folder was previously marked with a
   non-`"complete"` status (e.g., `"orphaned"`), the sync restores it to `"complete"`
   when the folder is encountered again in S3.

5. **Add/update only** - The sync does **not** handle deletions. Files or folders
   that exist in the database but no longer exist in S3 are left untouched.

6. **Batched processing** - S3 objects are fetched in paginated batches and written
   to the database in configurable batch sizes (default: 1,000 objects per batch)
   to manage memory and transaction size.

### Architecture

```
S3 Bucket(s)
     │
     ▼
iter_s3_object_batches()   ← paginates list_objects_v2, yields batches
     │
     ▼
sync_bucket()              ← per-bucket: FolderCache + bulk_upsert_files
     │
     ▼
sync_s3_agent_to_postgres() ← top-level: iterates buckets, aggregates summaries
     │
     ▼
PostgreSQL (Folder + File tables)
```

### Data Structures

- **`BucketSyncSummary`** - Per-bucket result: `bucket`, `files_synced`, `folders_synced`.
- **`ObjectStorageSyncSummary`** - Aggregate result across all buckets with computed
  properties `bucket_count`, `file_count`, `folder_count`, and a `to_dict()` method
  for serialisation.
- **`FolderCache`** - In-memory cache of all existing folders in a bucket (id, ltree
  path, status). Avoids repeated database lookups during sync and creates missing
  ancestor folders on-the-fly.

---

## Tests

All tests live in `backend/tests/test_object_storage_sync.py`. They use lightweight
fakes (no real database or S3 connection) to exercise the sync logic in isolation.

| Test | What It Verifies |
|------|-----------------|
| `test_batches_s3_objects_by_size` | S3 pagination results are correctly flattened into fixed-size async batches. A multi-page S3 response with `batch_size=2` yields `[["a","b"], ["c","d"], ["e"]]`. |
| `test_folder_cache_creates_nested_folders` | When a deeply nested path like `/Photos/Raw Files/` is requested, all missing ancestor folders are created in order, assigned auto-incrementing IDs, given correct `ltree` paths (e.g., `root.photos.raw_files`), and cached for subsequent lookups. |
| `test_folder_cache_restores_orphaned_folder` | A cached folder with `"orphaned"` status is restored to `"complete"` when `ensure_exists` is called, and the in-memory status cache is updated accordingly. |
| `test_sync_bucket_builds_file_rows` | A full `sync_bucket` run correctly: (a) skips zero-byte folder markers (`photos/`), (b) creates file rows with the correct bucket, folder_id, name, key, size, etag, and status, and (c) returns an accurate `BucketSyncSummary`. |
| `test_sync_bucket_handles_multiple_batches` | When `batch_size` is smaller than the number of objects, `sync_bucket` writes and commits each batch independently, and the final commit count and file count are correct. |
| `test_sync_all_uses_agent_buckets` | The top-level `sync_s3_agent_to_postgres` calls `sync_bucket` for each bucket reported by the agent and correctly aggregates per-bucket summaries into the overall `ObjectStorageSyncSummary`. |
