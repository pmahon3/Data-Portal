# Asset Loading

The asset tree has two modes:

| Mode | Behavior |
| --- | --- |
| Browse | Load roots first, then load folders as they are opened. |
| Search | Load the complete authorized tree, then filter it in the browser. |

## Separate trees

Each storage instance has three independent trees:

- `read` for Download;
- `write` for Upload;
- `delete` for Delete.

Loading or caching one tree does not affect the other two.

## Browse mode

Opening a card loads the read roots:

```http
GET /api/tree/dashboard/{instance_uuid}/children?access=read
```

Opening a folder loads its immediate children:

```http
GET /api/tree/dashboard/{instance_uuid}/children?access=read&parent_id=12
```

Write and delete use the same endpoints with their own `access` value.

A browse tree is only partial. Unopened folders still need lazy-loading.
If no complete tree is cached, returning to an action requests its roots again.

## Complete-tree cache

A path search loads the complete tree for the active action:

```http
GET /api/tree/dashboard/{instance_uuid}?access=read
```

After the complete tree is cached:

- later searches for that action do not refetch it;
- folders do not lazy-load because all nodes are present;
- clearing search does not remove the cache;
- leaving and returning to the action does not remove the cache.

## When is it cleared?

Before the first path search, the action has no complete-tree cache.

| Event | Result |
| --- | --- |
| Upload or delete while browsing | Refresh the active action with roots and resume lazy-loading. |
| Upload or delete while searching | Replace the active action's complete cache. |
| Reload the page or unmount the card | Remove all three caches. |

Only the active action is refreshed. The other read, write, or delete caches are
unchanged. There is no time-based expiry.

Changes made elsewhere do not automatically clear the cache. Reload the page or
trigger the relevant refresh to retrieve them.

## Main source file

`frontend/src/components/admin_page/asset_management/useEndpointAssetTree.js`
