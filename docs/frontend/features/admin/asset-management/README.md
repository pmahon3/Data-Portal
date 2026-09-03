# Asset Management

Asset management lets users browse authorized storage trees and perform file
actions. The same feature is used by the administration and normal-user
interfaces.

## Guides

| Topic | Guide |
| --- | --- |
| Checkbox and action selection rules | [Selection](./selection.md) |
| Browse mode, lazy loading, and caching | [Loading](./loading.md) |
| Glob, regular-expression, and selected-item filters | [Searching](./searching.md) |
| Backend authorization, metadata, storage, and bundling | [Backend](./backend.md) |

## Page flow

1. Load the storage instances available to the signed-in user.
2. Display one expandable card for each instance.
3. Load the authorized read roots when a card is opened.
4. Let the user browse or search the Download, Upload, and Delete trees.
5. Send the selected action to the backend with a Keycloak bearer token.

The page loads available instances from:

```http
GET /api/users/{username}/instances
```

## Action tabs

Each storage card has three views:

| Tab | Permission | Selection | Action |
| --- | --- | --- | --- |
| **Download** | `read` | Files or folders | Download one file directly or prepare a ZIP bundle. |
| **Upload** | `write` | Exactly one folder | Upload files or a local folder into that destination. |
| **Delete** | `delete` | Files or folders | Delete the selected items after confirmation. |

Download, Upload, and Delete each have independent tree data and an independent
complete-tree cache. See [Loading](./loading.md) for the cache lifecycle.

The frontend only displays tree nodes returned by the authorized backend tree
endpoints. The backend checks permission again when an action is submitted.

## File-transfer model

File bytes normally move directly between the browser, object storage, and the
bundler:

- uploads use presigned storage requests returned by the backend;
- a single-file download uses an authorized presigned URL;
- multi-file and folder downloads are prepared by the bundler;
- deletes go through the backend so storage and PostgreSQL metadata are updated
  together.

## Main frontend source files

| Purpose | File |
| --- | --- |
| Load visible storage instances | `frontend/src/components/admin_page/asset_management/index.js` |
| Per-instance tabs and actions | `frontend/src/components/admin_page/asset_management/EndpointCard.js` |
| Tree loading and mode state | `frontend/src/components/admin_page/asset_management/useEndpointAssetTree.js` |
| Upload, download, and delete requests | `frontend/src/components/admin_page/asset_management/actions.js` |
| Selection and node helpers | `frontend/src/components/admin_page/asset_management/EndpointCardUtils.js` |
| Tree rendering and filtering | `frontend/src/components/admin_page/asset_management/tree/` |
