# Browse and Search Modes

Each access tab starts in browse mode. Search mode begins when the user submits
a search.

## Browse mode

Browse mode loads only what the user opens.

1. Load bucket roots:

   ```http
   GET /api/tree/dashboard/{instance_uuid}/children?access=read
   ```

2. Load a folder when it is expanded:

   ```http
   GET /api/tree/dashboard/{instance_uuid}/children?access=read&parent_id=12
   ```

This mode is better for large trees because unopened folders are not sent to the
browser.

## Search mode

Search mode loads the complete authorized tree for one access type:

```http
GET /api/tree/dashboard/{instance_uuid}?access=read
```

The frontend then filters the returned nodes. Search does not query PostgreSQL
for each search term.

Search supports:

- glob patterns, such as `*.csv` and `study-?`;
- JavaScript regular expressions;
- filtering to selected items only.

Search is case-insensitive. `*` and `?` do not cross `/` path separators.
Matching results keep their parent folders visible.

## Switching modes

- Opening a card loads the `read` roots in browse mode.
- Changing access tabs loads browse data for the new tab.
- Starting a search clears the current selection and loads the full tree.
- Clearing a search returns to browse mode and clears the selection.
- If the full tree is already cached, the frontend reuses it instead of loading
  roots again.

## When the search cache is cleared

The full tree is cached separately for each `read`, `write`, and `delete` tab.

| Action | Cache behavior |
| --- | --- |
| Clear the search | Kept and reused. |
| Change tabs | Kept for each tab. |
| Return to browse mode normally | Kept and reused. No root request is made. |
| Force-refresh in search mode | Replaced with a newly loaded full tree. |
| Force-refresh in browse mode | Cleared and replaced with root nodes. |
| Reload the page or unmount the card | Cleared with the React state. |

Uploads and deletes force-refresh the active mode. In search mode, the full
tree is refreshed and stays cached. In browse mode, the cache for that tab is
cleared and the roots are loaded again.

The full tree remains in browser memory after search until one of the clearing
actions above occurs.
