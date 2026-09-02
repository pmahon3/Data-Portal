# Asset-Management Backend

The backend authorizes requests, returns tree metadata, coordinates storage
operations, and submits multi-file downloads to the bundler. The frontend owns
selection and search-term filtering.

## Responsibilities

| Component | Work performed |
| --- | --- |
| Keycloak integration | Decode the bearer token and identify the user. |
| Casbin | Check `read`, `write`, or `delete` permission for resource paths. |
| PostgreSQL | Store completed folder and file metadata used by the tree. |
| Storage agent | List instance buckets and create presigned storage requests. |
| Object storage | Store and transfer the actual file bytes. |
| Bundler | Read authorized files and create ZIP archives for multi-item downloads. |

## Tree requests

| Method | Endpoint | Backend work |
| --- | --- | --- |
| `GET` | `/api/tree/dashboard/{instance_uuid}/children` | Return authorized roots or one folder's immediate children. |
| `GET` | `/api/tree/dashboard/{instance_uuid}` | Return the complete authorized tree for one action. |

For both requests, the backend:

1. identifies the user and storage instance;
2. reads completed folder and file metadata from PostgreSQL;
3. builds folder and file resource paths;
4. filters nodes with Casbin for the requested action;
5. returns a flat node list.

Tree requests do not search object storage and do not process the user's search
text.

## File actions

| Flow | Main endpoints | Backend work |
| --- | --- | --- |
| Upload | `POST /api/tree/files/upload/init` and `/complete` | Authorize the destination, create pending metadata, return a presigned upload, then mark completion. |
| Folder upload | `POST /api/tree/folders/ensure-path` | Create or reuse metadata for the uploaded directory path. |
| Delete file | `DELETE /api/tree/files/{file_id}` | Authorize and remove the object and its metadata. |
| Delete folder | `DELETE /api/tree/folders/{folder_id}` | Authorize and remove the folder contents and metadata. |
| Download | `POST /api/tree/bundle/zip` | Expand folder selections, authorize each file, and generate presigned source URLs. |

For one authorized file, the bundle endpoint returns its presigned URL directly.
For multiple files, the backend sends the authorized URLs to the configured
bundler. The frontend polls `/api/tree/bundle/{bundle_id}/status`, then requests
`/api/tree/bundle/{bundle_id}/download` for the completed archive URL.

## Keeping tree metadata current

PostgreSQL contains metadata only; the files remain in object storage. Metadata
is updated by portal uploads and deletes, explicit instance sync, and storage
events.

```http
POST /api/instances/{instance_uuid}/sync
```

A frontend tree refresh rereads PostgreSQL. It does not run this storage sync.

## Main backend files

| Purpose | File |
| --- | --- |
| Authorized tree endpoints | `backend/api/v0_1/endpoints/file_tree_db.py` |
| Upload, delete, and bundle endpoints | `backend/api/v0_1/endpoints/s3_endpoints.py` |
| Folder and file services | `backend/core/services/filetree/` |
| PostgreSQL schema | `backend/core/db/postgres/scripts/schema.sql` |
