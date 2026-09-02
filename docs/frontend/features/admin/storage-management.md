# Storage Management

Storage management creates and maintains the storage connections available to
the portal.

The current frontend creation form supports S3-compatible storage.

## Available actions

| Action | Administrator | Project manager |
| --- | --- | --- |
| List visible instances | Yes | Yes, for managed projects |
| Create an instance | Yes | Yes, for managed projects |
| Rename an instance | Yes | No |
| Sync S3 tree metadata | Yes | Yes, for managed projects |
| Delete an instance | Yes | No |

The backend authorizes each action. The current page renders the rename control
for project managers, but the API accepts rename requests from administrators
only. The delete button is hidden from project managers.

## Creating an S3 instance

| Field | Required | Purpose |
| --- | --- | --- |
| Instance Name | Yes | Display name used to derive the stable instance UUID. |
| Projects | No | Projects that should receive the new instance. |
| S3 Endpoint URL | Yes | Address of the S3-compatible service. |
| Access Key | Yes | Storage credential. |
| Secret Key | Yes | Storage credential. |
| Region Name | No | Region passed to the S3 client. |

Sensitive configuration values are masked when an instance card displays its
configuration.

## Sync behavior

Sync can take time, so the page displays a blocking progress dialog. When sync
finishes, it reports the number of files and buckets returned by the backend.

Sync updates tree metadata from object storage. It does not move ownership of
the underlying files into the portal.

## API calls

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/instances/` | List visible instances. |
| `POST` | `/api/instances/` | Create an instance and attach selected projects. |
| `PATCH` | `/api/instances/{instance_uuid}` | Rename an instance. |
| `POST` | `/api/instances/{instance_uuid}/sync` | Synchronize S3 contents into tree metadata. |
| `DELETE` | `/api/instances/{instance_uuid}` | Delete an instance. |
| `GET` | `/api/projects` | Populate the project selector. |

## Main source files

| Purpose | File |
| --- | --- |
| Page layout and sync dialog | `frontend/src/components/admin_page/storage_management/index.js` |
| Instance state and API calls | `frontend/src/components/admin_page/storage_management/useStorageInstances.js` |
| Create-instance form | `frontend/src/components/admin_page/storage_management/StorageForm.js` |
| Instance display and actions | `frontend/src/components/admin_page/storage_management/StorageCard.js` |
