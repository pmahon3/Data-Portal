/** Search modes supported by the tree filter UI. */
export const SEARCH_MODES = Object.freeze({
  GLOB: "glob",
  REGEX: "regex",
});

/**
 * Converts the flat backend payload into the nested shape expected by MUI TreeView.
 *
 * @param {Array<Object>} list - The flat array of assets from the backend.
 * @returns {Array<Object>} Top-level nodes with nested `children` arrays.
 */
export function buildTreeFromFlat(list) {
  if (!Array.isArray(list) || list.length === 0) return [];

  const map = Object.create(null);

  // First pass: create one normalized node record for every item.
  for (const item of list) {
    const id = String(item.id);

    if (!map[id]) {
      map[id] = { id, text: item.text || nameFromId(id), children: [] };
    } else if (!map[id].text) {
      map[id].text = item.text || nameFromId(id);
    }

    map[id]._parentId =
      item.parent && item.parent !== "#" ? String(item.parent) : null;
  }

  const roots = [];

  // Second pass: connect child nodes to parents and collect top-level roots.
  for (const item of list) {
    const id = String(item.id);
    const parent = item.parent;
    const node = map[id];

    if (parent && parent !== "#" && parent !== id) {
      const parentId = String(parent);

      if (!map[parentId]) {
        map[parentId] = {
          id: parentId,
          text: nameFromId(parentId),
          children: [],
        };
      }

      map[parentId].children.push(node);
      node._parentRef = map[parentId];
    } else {
      roots.push(node);
    }
  }

  sortByText(roots);
  return roots;
}

/** Sorts each tree level by visible label for stable rendering. */
export function sortByText(nodes) {
  nodes.sort((left, right) =>
    String(left.text).localeCompare(String(right.text)),
  );

  for (const node of nodes) {
    if (node.children && node.children.length) {
      sortByText(node.children);
    }
  }
}

/** Falls back to the last path segment when a node has no explicit label. */
export function nameFromId(id) {
  const value = String(id);
  const parts = value.endsWith("/")
    ? value.slice(0, -1).split("/")
    : value.split("/");
  const base = parts[parts.length - 1];
  return value.endsWith("/") ? `${base}/` : base;
}

/** Uses full path metadata for filtering when the backend provides it. */
export function getSearchablePath(node) {
  const attrs = node.li_attr || {};
  return String(attrs.key || attrs.full_path || node.text || "");
}

/**
 * Filters the flat node list while preserving ancestor context for visible matches.
 *
 * @param {Array<Object>} nodes - The flat list of all nodes.
 * @param {Object} options - Filtering parameters.
 * @param {RegExp|null} options.pathMatcher - Compiled matcher for path filtering.
 * @param {Set<string>} options.selected - Set of selected node IDs.
 * @param {boolean} options.selectedOnly - Whether to limit results to selected nodes.
 * @returns {Array<Object>} Visible nodes plus any ancestors needed to anchor them.
 */
export function filterNodes(nodes, { pathMatcher, selected, selectedOnly }) {
  if (!pathMatcher && !selectedOnly) return nodes;

  const { nodeMap, childrenMap } = indexNodes(nodes);
  const visibleIds = new Set();

  for (const node of nodes) {
    const id = String(node.id);
    const matchesPath = pathMatcher
      ? pathMatcher.test(getSearchablePath(node))
      : true;
    const matchesSelection = selectedOnly ? selected.has(id) : true;

    if (matchesPath && matchesSelection) {
      // include the node AND its ancestors folders so the user can see where the match lives.
      includeWithAncestors(id, visibleIds, nodeMap);

      if (!selectedOnly) {
        // Path searches keep matching folders useful by showing their contents.
        // Selected-only skip this so an explicitly selected folder
        // does not automatically reveal every unselected child.
        includeDescendants(id, visibleIds, childrenMap);
      }
    }
  }

  return nodes.filter((node) => visibleIds.has(String(node.id)));
}

/** Precomputes lookup tables for parent-child traversal on the flat node list. */
export function indexNodes(nodes) {
  const nodeMap = new Map();
  const childrenMap = new Map();

  for (const node of nodes) {
    const id = String(node.id);
    // nodeMap gives upward traversal a quick way to find a node's parent id.
    nodeMap.set(id, node);

    // Root nodes use "#" or an empty parent value, so they do not belong in a
    // parent's child list.
    const parentId =
      node.parent && node.parent !== "#" ? String(node.parent) : null;
    if (!parentId) continue;

    // childrenMap groups child ids by parent id for fast downward traversal.
    if (!childrenMap.has(parentId)) {
      childrenMap.set(parentId, []);
    }

    // Store ids instead of node objects so visibility checks can stay centered
    // on the visibleIds Set used by filterNodes.
    childrenMap.get(parentId).push(id);
  }

  return { nodeMap, childrenMap };
}

/** Builds a matcher for the current search mode. */
export function createPathMatcher(input, mode = SEARCH_MODES.GLOB) {
  return mode === SEARCH_MODES.REGEX
    ? createRegexMatcher(input)
    : createGlobMatcher(input);
}

/** Validates search input before the UI applies it. */
export function isValidSearchPattern(input, mode = SEARCH_MODES.GLOB) {
  if (mode !== SEARCH_MODES.REGEX) return true;

  const pattern = trimFilterText(input);
  if (!pattern) return true;

  try {
    new RegExp(pattern, "i");
    return true;
  } catch {
    return false;
  }
}

/** Compiles the lightweight glob syntax used by the filter UI. */
export function createGlobMatcher(input) {
  const glob = trimFilterText(input).toLowerCase();
  return glob ? globToRegExp(glob) : null;
}

/** Compiles user-provided regex input case-insensitively. */
export function createRegexMatcher(input) {
  const pattern = trimFilterText(input).toLowerCase();
  if (!pattern) return null;

  try {
    return new RegExp(pattern, "i");
  } catch {
    return null;
  }
}

/** Normalizes optional filter input to a trimmed string. */
export function trimFilterText(value) {
  return String(value || "").trim();
}

/** Converts `*` and `?` wildcards into a case-insensitive regular expression. */
export function globToRegExp(glob) {
  // Escape regex operators first so user text stays literal, then reintroduce
  // only the two wildcard operators supported by glob mode.
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  const pattern = escaped.replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`.*${pattern}.*`, "i");
}

/** Marks a node and all of its ancestors as visible. */
export function includeWithAncestors(id, visibleIds, nodeMap) {
  let currentId = id;

  // Stop when we reach a root, a placeholder root marker, or a node that was
  // already visited by another match.
  while (currentId && currentId !== "#" && !visibleIds.has(currentId)) {
    visibleIds.add(currentId);
    const node = nodeMap.get(currentId);
    currentId =
      node?.parent && node.parent !== "#" ? String(node.parent) : null;
  }
}

/** Marks a node's full subtree as visible. */
export function includeDescendants(id, visibleIds, childrenMap) {
  const children = childrenMap.get(id);
  if (!children) return;

  // Walk depth-first from the matched folder.
  for (let index = 0; index < children.length; index += 1) {
    const childId = children[index];
    if (!visibleIds.has(childId)) {
      visibleIds.add(childId);
      includeDescendants(childId, visibleIds, childrenMap);
    }
  }
}

// Checking a folder means every item under that folder becomes selected.
export function selectSubtree(selection, node) {
  selection.add(String(node.id));
  if (node.children) {
    node.children.forEach((child) => selectSubtree(selection, child));
  }
}

export function unselectSubtree(selection, node) {
  selection.delete(String(node.id));
  if (node.children) {
    node.children.forEach((child) => unselectSubtree(selection, child));
  }
}

// Promote selection upward when a whole sibling group becomes selected.
export function checkAncestors(selection, node) {
  if (!node._parentRef) return;

  const parent = node._parentRef;
  const allSiblingsChecked = parent.children.every((child) =>
    selection.has(String(child.id)),
  );

  if (allSiblingsChecked) {
    selection.add(String(parent.id));
    checkAncestors(selection, parent);
  }
}

// Clear selected ancestors once a child in that branch becomes unselected.
export function uncheckAncestors(selection, node) {
  if (!node._parentRef) return;

  const parent = node._parentRef;
  if (selection.has(String(parent.id))) {
    selection.delete(String(parent.id));
    uncheckAncestors(selection, parent);
  }
}
