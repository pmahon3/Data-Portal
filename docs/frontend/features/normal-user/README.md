# Normal-User Feature

The normal-user interface lets authenticated users work with authorized assets
and review their access policies.

## Who sees this interface?

The frontend shows this interface to authenticated users who have neither:

- the Keycloak `admin` realm role; nor
- a project claim ending in `/managers`.

This choice only controls which interface is displayed. The backend still
authorizes every request.

## Available pages

| Tab | Purpose |
| --- | --- |
| **My Assets** | Browse storage instances and perform permitted file actions. |
| **My Policies** | Review the current user's storage access policies. |

## My Assets

The page loads the user's available storage instances from:

```http
GET /api/users/{username}/instances
```

Each instance has three action tabs. The backend returns only the tree data the
user is authorized to access.

| Tab | Permission | Available action |
| --- | --- | --- |
| **Download** | `read` | Download selected files or folders. |
| **Upload** | `write` | Upload files or a folder into one selected destination folder. |
| **Delete** | `delete` | Delete selected files or folders after confirmation. |

An empty action tab means the user has no matching permission or no visible
assets for that action.

### Finding assets

- Browse mode loads folders as the user opens them.
- Search mode loads the complete authorized tree for the selected action and
  filters it in the browser.

See [File tree loading](../../file-tree-loading/README.md) for more detail.

### Downloads

- A single file uses an authorized storage URL.
- Multiple files or folders are prepared by the bundler service.
- The page waits for the bundle to finish, then opens the completed archive.

### Uploads

The user selects exactly one destination folder, then chooses files or a local
folder. The backend authorizes the request and returns presigned upload details.
The browser sends the file data directly to object storage.

### Deletes

The page summarizes the selected files and folders before asking for
confirmation. Delete requests go through the backend so authorization and tree
metadata remain consistent.

## My Policies

The page loads the signed-in user's policies from:

```http
GET /api/policies/me
```

Policies are read-only on this page.

| Column | Meaning |
| --- | --- |
| Instance Name | Storage instance covered by the policy. |
| Resource | File or folder path covered by the policy. |
| Action | Allowed operation, such as `read`, `write`, or `delete`. |

Policy changes must be made through an authorized management flow. Normal users
cannot edit policies from this page.

## Main source files

| Purpose | File |
| --- | --- |
| Normal-user tabs | `frontend/src/components/normal_user_page/NormalUserPage.js` |
| Policy table | `frontend/src/components/normal_user_page/MyPolicies.js` |
| Shared asset page | `frontend/src/components/admin_page/asset_management/index.js` |
| Per-instance actions | `frontend/src/components/admin_page/asset_management/EndpointCard.js` |
| Tree loading | `frontend/src/components/admin_page/asset_management/useEndpointAssetTree.js` |
