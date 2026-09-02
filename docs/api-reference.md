# API Reference

**Last updated:** 2026-08-27

Backend routes use the `/api` prefix. Swagger UI is available at `/docs` and
ReDoc at `/redoc` while the backend is running.

Most routes require a Keycloak bearer token. Keycloak handles users and
projects, Casbin handles storage permissions, PostgreSQL stores file-tree
metadata, and MongoDB stores instance configurations and policies. Files remain
in object storage and are transferred with presigned URLs.

## Authentication

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/auth/validate` | Validate a bearer token and return its user claims. |

## File Tree

See [File Tree Loading](./file-tree-loading/) for loading modes, caching, and
tree authorization behavior.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tree/root` | Get a bucket root. Requires `instance_name` and `bucket` query parameters. |
| `GET` | `/api/tree/{folder_id}` | List a folder's immediate children. Requires `instance_name` and `bucket`. |
| `POST` | `/api/tree/folders` | Create a child folder. |
| `POST` | `/api/tree/folders/ensure-path` | Create a nested folder path if it does not exist. |
| `GET` | `/api/tree/dashboard/{instance_uuid}` | Return the complete authorized tree for one `access` type: `read`, `write`, or `delete`. |
| `GET` | `/api/tree/dashboard/{instance_uuid}/children` | Lazy-load roots or children for one `access` type. Pass `parent_id` to load a folder. |
| `POST` | `/api/tree/files/upload/init` | Create a pending file record and return a presigned upload URL. |
| `POST` | `/api/tree/files/upload/complete` | Verify the upload and finalize its PostgreSQL metadata. |
| `GET` | `/api/tree/files/{file_id}/download-url` | Return a presigned download URL. Requires `instance_name`. |
| `DELETE` | `/api/tree/files/{file_id}` | Delete a file from object storage and PostgreSQL. Requires `instance_name`. |
| `DELETE` | `/api/tree/folders/{folder_id}` | Delete a folder subtree from object storage and PostgreSQL. Requires `instance_name` and `bucket`. |

The old `/api/assets/...` routes are no longer available. Use `/api/tree/...`
for all file and folder operations.

## Bundle Downloads

The backend checks Casbin read access before sending files to the bundler.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tree/bundle/zip` | Create a bundle from `file_ids` and `folder_ids`. A single file may return `single_file_url` immediately. |
| `GET` | `/api/tree/bundle/{bundle_id}/status` | Poll a bundle job. |
| `GET` | `/api/tree/bundle/{bundle_id}/download` | Return a presigned `result_url` for the completed ZIP. The backend does not stream the ZIP. |

Java bundler is the default provider. It uploads completed ZIP files to object
storage, and the browser downloads them from the presigned URL.

## Users

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/users/` | List users *(admin or project manager)*. |
| `POST` | `/api/users/` | Create a user *(admin or project manager)*. |
| `GET` | `/api/users/me` | Get the current user's profile. |
| `GET` | `/api/users/{username}` | Get a user profile *(owner or admin)*. |
| `DELETE` | `/api/users/{username}` | Delete a user and their policies *(owner or admin)*. |
| `GET` | `/api/users/{username}/instances` | List the user's accessible storage instances *(owner or admin)*. |

## Policies

Project managers can manage policies only for users and instances in a project
they manage.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/policies/me` | List the current user's policies. |
| `GET` | `/api/policies/` | List or filter policies *(admin or project manager)*. |
| `POST` | `/api/policies/` | Add a policy *(admin or project manager)*. |
| `DELETE` | `/api/policies/` | Remove a policy *(admin or project manager)*. |
| `POST` | `/api/policies/validate` | Test a policy without adding it *(admin)*. |

## Storage Instances

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/instances/` | List all instances for an admin or assigned instances for a project manager. |
| `POST` | `/api/instances/` | Create an instance and grant the creator admin access. |
| `GET` | `/api/instances/{instance_id}` | Get instance details without secrets *(admin)*. |
| `POST` | `/api/instances/{instance_id}/sync` | Import S3 file-tree metadata into PostgreSQL *(admin or assigned project manager)*. |
| `PATCH` | `/api/instances/{instance_id}` | Rename an instance *(admin)*. |
| `DELETE` | `/api/instances/{instance_id}` | Delete the instance, tree metadata, project links, and policies *(admin)*. Stored objects are not deleted. |

## Projects

Projects are Keycloak groups. Casbin still controls access to storage paths.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List visible projects *(admin or project manager)*. |
| `POST` | `/api/projects` | Create a project *(admin)*. |
| `DELETE` | `/api/projects/{project_name}` | Delete a project *(admin)*. |
| `POST` | `/api/projects/{project_name}/users` | Add a user *(admin or manager of the project)*. |
| `DELETE` | `/api/projects/{project_name}/users/{username}` | Remove a user *(admin or manager of the project)*. |
| `POST` | `/api/projects/{project_name}/managers` | Add a project manager *(admin)*. |
| `DELETE` | `/api/projects/{project_name}/managers/{username}` | Remove a project manager *(admin)*. |
| `POST` | `/api/projects/{project_name}/storage-instances` | Attach an instance *(admin)*. |
| `DELETE` | `/api/projects/{project_name}/storage-instances/{instance_name}` | Detach an instance *(admin)*. |

## Object Storage Events

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/object-storage/events` | Receive an object-storage event. Uses `X-Webhook-Secret` or `webhook_secret` when a webhook secret is configured. |

## Health

These routes do not require a bearer token.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` or `/api/health/` | Basic health check. |
| `GET` | `/api/health/detailed` | Detailed component status. |
| `GET` | `/api/health/validate` | Validate the environment. |
| `GET` | `/api/health/ready` | Readiness probe. |
| `GET` | `/api/health/live` | Liveness probe. |

## Internal Bundler Routes

Portal clients should use `/api/tree/bundle/...` instead of calling a bundler
directly.

### Java Bundler (Default)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bundles` | Create an asynchronous bundle job. |
| `GET` | `/bundles/{bundleId}` | Get job status. |
| `GET` | `/bundles/{bundleId}/download` | Return a presigned `resultUrl`. |
| `GET` | `/bundles/admin/jobs` | List all jobs. |

### Python Bundler (Alternative)

The Python service exposes the same create, status, and download routes under
`/bundles`, `/v1/bundles`, and `/v2/bundles`. Its download route streams ZIP
bytes instead of returning a presigned URL. It also provides `/health`,
`/metrics`, and optional `/actuator` operational routes.
