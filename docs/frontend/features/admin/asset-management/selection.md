# Asset Selection

Selection is stored separately for every storage instance and action.

```text
selected
`-- instance UUID
    |-- read: Set of node IDs
    |-- write: Set of node IDs
    `-- delete: Set of node IDs
```

Folder IDs are numeric strings. File IDs use the form `file-{database_id}`.

## Rules by action

| Behavior | Download | Upload | Delete |
| --- | --- | --- | --- |
| Select files | Yes | No | Yes |
| Select folders | Yes | Yes | Yes |
| Selection cascades to loaded children | Yes | No | Yes |
| Multiple selections | Yes | No, the action requires one folder | Yes |
| Bucket root can be submitted | Yes | Yes | No |

Upload selection does not cascade because the selected folder is a destination,
not a group of items to process.

## Parent and child behavior

For Download and Delete:

- selecting a folder selects all children currently loaded below it;
- selecting every loaded child selects their parent;
- clearing a selection clears its loaded descendants;
- clearing a child also clears selected ancestors above it.

If a selected folder is expanded later, newly loaded children inherit the
selection. This inheritance does not happen in Upload mode.

A collapsed folder containing a selected descendant displays a small marker so
the user can locate selections deeper in the tree.

## Preparing actions

### Download

Selected IDs are split into numeric `file_ids` and `folder_ids`. The backend
expands folders and removes duplicate files when a selected folder overlaps a
selected descendant.

### Upload

The action validates that exactly one selectable folder is selected. It uses the
folder ID and bucket stored on the tree node as the upload destination.

### Delete

Only top-level selected nodes are submitted. If both a folder and one of its
children are selected, only the folder is sent. Bucket roots are excluded.

## When selection is cleared

| Event | Result |
| --- | --- |
| Change Download, Upload, or Delete tabs | Clear selections for all three tabs in that storage card. |
| Submit a path search | Clear the selection for the active tab. |
| Clear a path search | Clear the selection for the active tab. |
| Complete a delete | Clear the Delete selection. |
| Reload or leave the page | Clear all in-memory selections. |

## Main source files

| Purpose | File |
| --- | --- |
| Selection state by instance and action | `frontend/src/components/admin_page/asset_management/index.js` |
| Action validation and selection clearing | `frontend/src/components/admin_page/asset_management/EndpointCard.js` |
| Action ID conversion | `frontend/src/components/admin_page/asset_management/EndpointCardUtils.js` |
| Parent and child cascade rules | `frontend/src/components/admin_page/asset_management/tree/TreeUtils.js` |
| Checkbox behavior | `frontend/src/components/admin_page/asset_management/tree/TreeNode.js` |
