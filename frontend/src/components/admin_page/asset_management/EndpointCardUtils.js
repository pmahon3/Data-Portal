/**
 * Format seconds into a human-readable "Xm Ys" string.
 * @param {number} s - Elapsed seconds
 * @returns {string}
 */
export function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

/**
 * Normalize tree data into { read, write, delete } arrays.
 * Accepts an array (treated as read-only) or an object with optional keys.
 *
 * @param {Array|Object} input - Raw tree data from state
 * @returns {{ read: Array, write: Array, delete: Array }}
 */
export function normalizeAccess(input) {
  if (!input) return { read: [], write: [], delete: [] };
  if (Array.isArray(input)) return { read: input, write: [], delete: [] };
  if (typeof input === "object") {
    return {
      read: Array.isArray(input.read) ? input.read : [],
      write: Array.isArray(input.write) ? input.write : [],
      delete: Array.isArray(input.delete) ? input.delete : [],
    };
  }
  return { read: [], write: [], delete: [] };
}

/**
 * Merge newly fetched child nodes into the existing tree, deduplicating by id.
 * When a parentId is given, updates that parent's has_children flag.
 *
 * @param {Array} existing - Current tree nodes
 * @param {Array} incoming - Newly fetched child nodes
 * @param {string|null} parentId - The parent folder ID whose children were loaded
 * @returns {Array} Merged and deduplicated node array
 */
export function mergeAssetNodes(existing, incoming, parentId = null) {
  const byId = new Map();
  for (const node of existing) {
    if (parentId !== null && String(node.id) === String(parentId)) {
      byId.set(String(node.id), {
        ...node,
        li_attr: {
          ...(node.li_attr || {}),
          has_children: incoming.length > 0,
        },
      });
    } else {
      byId.set(String(node.id), node);
    }
  }
  for (const node of incoming) {
    byId.set(String(node.id), node);
  }
  return Array.from(byId.values());
}

/**
 * When a parent folder is selected and its children are lazy-loaded, auto-select
 * those newly loaded children so the selection stays consistent.
 *
 * @param {Set} currentSelection - Currently selected node IDs
 * @param {Array} loadedNodes - Newly loaded child nodes
 * @param {string} parentId - The parent folder ID
 * @param {Function} onChange - Callback to update the selection
 */
export function cascadeLoadedChildrenSelection(currentSelection, loadedNodes, parentId, onChange) {
  if (!currentSelection.has(String(parentId)) || loadedNodes.length === 0) return;

  const next = new Set(currentSelection);
  let changed = false;

  for (const node of loadedNodes) {
    const id = String(node.id);
    if (!next.has(id)) {
      next.add(id);
      changed = true;
    }
  }

  if (changed) onChange(next);
}

/**
 * Split tree selection IDs into DB file IDs and folder IDs.
 * File nodes use "file-{id}" while folder nodes are plain numeric IDs.
 *
 * @param {Set} sel - Set of selected node IDs
 * @returns {{ fileIds: number[], folderIds: number[] }}
 */
export function getSelectedDownloadIds(sel) {
  const fileIds = new Set();
  const folderIds = new Set();

  sel.forEach((id) => {
    const selectedId = String(id);
    const numericId = Number.parseInt(selectedId.replace("file-", ""), 10);
    if (Number.isNaN(numericId)) return;

    if (selectedId.startsWith("file-")) {
      fileIds.add(numericId);
    } else {
      folderIds.add(numericId);
    }
  });

  return {
    fileIds: Array.from(fileIds),
    folderIds: Array.from(folderIds),
  };
}

/**
 * Get selected top-level nodes (files and folders) for WRITE and DELETE.
 * If a folder and its child are both selected, only the folder is returned.
 * File selection is disabled for WRITE elsewhere.
 *
 * @param {Array} list - Flat list of tree nodes
 * @param {Set} sel - Set of selected node IDs
 * @param {boolean} excludeRoot - Whether to exclude root nodes (#)
 * @returns {string[]} Top-level selected node IDs
 */
export function getSelectTopLevel(list, sel, excludeRoot) {
  // Create a map of Node Id -> Parent Id
  const parentMap = new Map();
  for (const node of list) {
    parentMap.set(String(node.id), String(node.parent));
  }

  const result = [];

  // Iterate through selections
  for (const id of sel) {
    // Skip if the ID isn't in our list
    if (!parentMap.has(id)) continue;

    // Do not include root nodes if excludeRoot is true
    if (excludeRoot && parentMap.get(id) === "#") continue;

    let currentParent = parentMap.get(id);
    let isTopLevel = true;

    // Climb the tree until we reach the top most selected node
    while (currentParent && currentParent !== "#") {
      // If this node's parent is in the selection it is not a top level node
      if (sel.has(currentParent)) {
        // We only mark as not top level if we aren't excluding roots
        // OR if the parent isn't actually a root.
        if (!excludeRoot || parentMap.get(currentParent) !== "#") {
          isTopLevel = false;
          break;
        }
      }
      currentParent = parentMap.get(currentParent);
    }

    if (isTopLevel) {
      result.push(id);
    }
  }

  return result;
}
