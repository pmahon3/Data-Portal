# File Tree Loading

The asset-management file tree reads folder and file metadata from PostgreSQL.
The files themselves remain in object storage.

The frontend supports two loading modes:

- **Browse mode** loads bucket roots first, then loads folders as they are opened.
- **Search mode** loads the full authorized tree, then filters it in the browser.

## Guides

- [PostgreSQL object tree](./postgres-object-tree.md)
- [Browse and search modes](./browse-and-search-modes.md)
- [Lazy loading](./lazy-loading.md)

## Basic flow

1. The frontend requests tree nodes from `/api/tree`.
2. The backend reads metadata from PostgreSQL.
3. Casbin removes nodes the user cannot access.
4. The frontend builds and displays the tree.

Tree data is stored separately for the `read`, `write`, and `delete` tabs.

## Main files

| Purpose | File |
| --- | --- |
| Tree API | `backend/api/v0_1/endpoints/file_tree_db.py` |
| Tree services | `backend/core/services/filetree/` |
| Database schema | `backend/core/db/postgres/scripts/schema.sql` |
| Frontend loading | `frontend/src/components/admin_page/asset_management/useEndpointAssetTree.js` |
| Tree display and filtering | `frontend/src/components/admin_page/asset_management/tree/` |
