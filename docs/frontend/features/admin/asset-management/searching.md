# Asset Searching

A path search works in two steps:

1. load the complete authorized tree for the active action;
2. filter the tree in the browser.

The backend is not queried for each search term.

## Cache example

Read, write, and delete have separate complete-tree caches.

| Action | What happens? |
| --- | --- |
| First Download search | Fetch and cache the full `read` tree. |
| Another Download search | Filter the cached read tree. No request. |
| First Upload search | Fetch and cache the separate `write` tree. |
| Return to Download | Reuse the read cache. No request. |
| First Delete search | Fetch and cache the separate `delete` tree. |

After a tree is cached, expanding folders does not lazy-load children.

See [Loading](./loading.md) for refresh and cache-clearing rules.

## Search modes

| Mode | Example |
| --- | --- |
| Glob | `*.csv` or `study-?` |
| Regular expression | `session-[0-9]+` |
| Selected only | Show selected items and their parent folders. |

Search is case-insensitive. Glob `*` and `?` do not cross `/` path separators.
Invalid regular expressions cannot be submitted.

Matching items keep their parent folders visible. Matching folders also keep
their descendants visible.

## How filtering works

1. The user submits a glob or regular-expression pattern.
2. The frontend loads the complete tree if it is not already cached.
3. Each node is matched against its file key, folder path, or visible name.
4. Matching nodes and their parent folders remain visible.
5. If a folder matches, its descendants also remain visible.
6. The filtered flat list is rebuilt into a tree and displayed.

The filtering happens entirely in the browser. Changing the pattern reuses the
same complete-tree cache.

When **Selected only** is enabled, a node must also be selected to match. Parent
folders remain visible for context, but unselected descendants are not added.

## Clearing search

Clearing a path search:

- clears the active selection;
- returns to browse mode;
- keeps the complete-tree cache.

Because the full tree is still cached, clearing search does not fetch roots and
does not restore lazy-loading.

The selected-only toggle filters the nodes currently in memory. It does not load
a complete tree by itself.

## Main source files

| Purpose | File |
| --- | --- |
| Complete-tree loading | `frontend/src/components/admin_page/asset_management/useEndpointAssetTree.js` |
| Search state and UI | `frontend/src/components/admin_page/asset_management/tree/index.js` |
| Search matching | `frontend/src/components/admin_page/asset_management/tree/TreeUtils.js` |
