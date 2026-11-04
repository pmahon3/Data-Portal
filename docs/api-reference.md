# API Reference

**Last updated:** 2026-10-31

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

See [File Tree Loading](./frontend/file-tree-loading/) for loading modes, caching, and
tree authorization behavior.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tree/root` | Get a bucket root. Requires `instance_name` and `bucket` query parameters. |
| `GET` | `/api/tree/{folder_id}` | List a folder's immediate children. Requires `instance_name` and `bucket`; `access` (`read` by default, `write` or `delete`) lists only what the user may act on, and the folders on the way to it. |
| `POST` | `/api/tree/folders` | Create a child folder. |
| `POST` | `/api/tree/folders/ensure-path` | Create a nested folder path if it does not exist. |
| `GET` | `/api/tree/dashboard/{instance_uuid}` | Return the complete authorized tree for one `access` type: `read`, `write`, or `delete`. |
| `GET` | `/api/tree/dashboard/{instance_uuid}/children` | Lazy-load roots or children for one `access` type. Pass `parent_id` to load a folder. |
| `POST` | `/api/tree/files/upload/init` | Create a pending file record and return a presigned upload URL. |
| `POST` | `/api/tree/files/upload/complete` | Verify the upload and finalize its PostgreSQL metadata. Returns `checks` (see below). |
| `POST` | `/api/tree/folders/upload/init` | Check a folder upload's manifest, create its folders and pending files, and return one presigned upload URL per file. |
| `POST` | `/api/tree/folders/upload/complete` | Verify a folder upload's files and finalize them. Returns `completed`, `failed` and `checks`. |
| `GET` | `/api/tree/files/{file_id}/download-url` | Return a presigned download URL. Requires `instance_name`. |
| `DELETE` | `/api/tree/files/{file_id}` | Delete a file from object storage and PostgreSQL. Requires `instance_name`. |
| `DELETE` | `/api/tree/folders/{folder_id}` | Delete a folder subtree from object storage and PostgreSQL. Requires `instance_name` and `bucket`. |

Completing an upload checks every dataset it belongs to that declares a standard (BIDS: a
`dataset_description.json` at the dataset's root) by file names and layout. `checks` lists one entry
per dataset and standard: `root`, `standard`, `quarantined`, `problems` (the count) and `findings`
(the first 100, each `path` and `problem`). A failing dataset is held in quarantine until a later
upload makes it pass.

The old `/api/assets/...` routes are no longer available. Use `/api/tree/...`
for all file and folder operations.

## Bundle Downloads

The backend checks read access to every file before sending files to the bundler; one refused file
refuses the bundle (403). A bundle belongs to the user who created it: anyone else gets 404 on its
status and download. When the ZIP is fetched, every file in it is checked again, so revoked access or
a deleted file refuses the download (403).

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
| `GET` | `/api/users/` | List users: every user for an admin; the members and managers of their own projects for a project manager. |
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
| `GET` | `/api/policies/check` | May a person do an action on a path, and which of their policies allows it? Takes `username`, `instance_name`, `resource` and `action`; returns `allowed`, `because` (the policies) and, for a folder path ending in `/`, `shown` *(admin, or project manager for people in their projects)*. |
| `POST` | `/api/policies/` | Add a policy *(admin or project manager)*. |
| `DELETE` | `/api/policies/` | Remove a policy *(admin or project manager)*. |

`GET /api/policies/` filters by `username` or `instance_name` as well as by UUID. A policy's
`resource` is a literal path: `bucket/path/file.txt` (that file), `bucket/folder/*` (that folder and
everything in it) or `*` (the whole instance). Its `action` is one action (`read`, `write`, `delete`, `admin`) or `*`.
Other forms are refused (400). An optional `ends` (an ISO date, e.g. `2027-06-30`) is the last day
the policy applies; from the next day (UTC) it allows nothing. A date already past is refused (400),
and policies are listed with their `ends`. An optional `excluded` lists paths inside a folder policy
(or `*`) that it leaves out, written like policy paths; anything outside the folder is refused (400). An optional `endings` (e.g. `[".nii", ".nii.gz"]`)
limits a folder policy to files whose names end in one, in any case; each must start with `.`. An optional `kinds` (e.g. `["anat"]`) limits a folder policy
inside a dataset that declares a standard to those kinds of data as the standard defines them (BIDS:
datatypes); a folder outside such a dataset, or a kind the standard doesn't define, is refused (400).

## Notifications

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notifications/` | The current user's newest 50 notifications, newest first: `kind` (`stored`, `stored_with_failures`), `message`, `created_at` (UTC), and what it's about (`file_id` or `folder_id`, counts). |

## Storage Instances

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/instances/` | List all instances for an admin or assigned instances for a project manager. |
| `POST` | `/api/instances/` | Create an instance and grant the creator admin access. `flavour` is `s3` or `posix`; a POSIX instance gives `instance_url` (its file service) and `namespace`. |
| `GET` | `/api/instances/{instance_id}` | Get instance details without secrets *(admin)*. |
| `POST` | `/api/instances/{instance_id}/sync` | Import S3 file-tree metadata into PostgreSQL *(admin or assigned project manager)*. |
| `PATCH` | `/api/instances/{instance_id}` | Rename an instance *(admin)*. |
| `DELETE` | `/api/instances/{instance_id}` | Delete the instance, tree metadata, project links, and policies *(admin)*. Stored objects are not deleted. |

## Storage Links

For POSIX file services, not browsers. File URLs for a POSIX instance are links to its file service,
signed by the backend.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/storage-links/jwks.json` | Public keys the file services verify links with. |

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

### Java Bundler

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bundles` | Create an asynchronous bundle job. |
| `GET` | `/bundles/{bundleId}` | Get job status. |
| `GET` | `/bundles/{bundleId}/download` | Return a presigned `resultUrl`. |
| `GET` | `/bundles/admin/jobs` | List all jobs. |
