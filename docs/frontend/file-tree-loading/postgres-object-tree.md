# PostgreSQL Object Tree

PostgreSQL stores a searchable copy of the object-storage folder structure. It
stores metadata only, not file contents.

## Tables

### `folders`

Each bucket has one root folder. Other folders point to their parent with
`parent_id`.

Important fields:

- `id`: folder ID used by the API and frontend
- `bucket`: object-storage bucket name
- `parent_id`: parent folder ID
- `name`: folder name
- `path`: PostgreSQL `ltree` path, such as `root.research.scans`
- `full_path`: display path, such as `/research/scans/`
- `status`: only `complete` folders appear in the tree

### `files`

Each file points to its containing folder with `folder_id`.

Important fields:

- `id`: database ID; the frontend receives it as `file-{id}`
- `bucket`: object-storage bucket name
- `folder_id`: containing folder ID
- `name`: filename
- `key`: full object-storage key
- `size`, `etag`, `last_modified`, and `content_type`: object metadata
- `status`: only `complete` files appear in the tree

## Authorization

The backend checks Casbin before returning a node. It checks the requested
action: `read`, `write`, or `delete`.

Resource paths have these forms:

```text
folder: {bucket}{folder_path}
file:   {bucket}/{object_key}
```

The frontend only receives nodes the user is allowed to access.

## Keeping PostgreSQL up to date

Metadata can be updated by:

- application uploads and deletes;
- `POST /api/instances/{instance_id}/sync`;
- `backend/core/db/postgres/scripts/sync_s3_postgres.py`;
- object-storage events and the storage-events worker.

The full S3 sync adds and updates metadata, but **does not remove missing objects**.
Deletes must come from the portal or a storage removal event.

Tree requests read PostgreSQL only. They do not scan or synchronize S3. The
frontend's `refresh=1` parameter reloads PostgreSQL data; it does not run a sync.
