/**
 * Turning a selection in the file tree into policy rules (requirements AC-4, AC-5).
 *
 * The rules are the ones typing would make, with no conversion beyond them:
 *   - a folder the admin ticked, with no filter active: `bucket/folder/*` (covers files added later)
 *   - a ticked file: `bucket/path/file.ext`, never collapsed into its folder
 *   - under a filter: one rule per file the filter shows
 * A folder becomes a folder rule only when it was ticked itself (a "folder grant"); the tree's
 * own selection can't tell that apart from a folder whose files were all ticked.
 */

const isFile = (id) => String(id).startsWith("file-");

function index(nodes) {
  const byId = new Map();
  const children = new Map();
  for (const node of nodes) {
    const id = String(node.id);
    byId.set(id, node);
    const parent = String(node.parent);
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(id);
  }
  return { byId, children };
}

function hasAncestorIn(id, set, byId) {
  let parent = byId.get(id)?.parent;
  while (parent !== undefined && String(parent) !== "#") {
    if (set.has(String(parent))) return true;
    parent = byId.get(String(parent))?.parent;
  }
  return false;
}

function everythingLoadedIsSelected(id, selected, children) {
  return (children.get(id) || []).every(
    (child) => selected.has(child) && everythingLoadedIsSelected(child, selected, children),
  );
}

/**
 * The folder grants after a change in the tree's selection. A folder newly selected with no
 * filter active was ticked itself; one selected under a filter only stands for the files the
 * filter shows. A grant lapses once its folder, or anything loaded under it, is unticked, or
 * once the selection was cleared from outside (a search starting).
 */
export function nextFolderGrants(grants, previous, next, nodes, filterActive) {
  const { children } = index(nodes);
  const result = new Set(
    [...grants].filter(
      (id) => previous.has(id) && next.has(id) && everythingLoadedIsSelected(id, next, children),
    ),
  );
  if (!filterActive) {
    for (const id of next) {
      if (!isFile(id) && !previous.has(id)) result.add(id);
    }
  }
  return result;
}

/** A folder's rule: its bucket and path, then "*". The bucket itself is `bucket/*`. */
export function folderRule(node) {
  const attrs = node.li_attr || {};
  let path = String(attrs.full_path || "/");
  if (!path.startsWith("/")) path = `/${path}`;
  if (!path.endsWith("/")) path = `${path}/`;
  return `${attrs.bucket}${path.replace(/\/{2,}/g, "/")}*`;
}

/** A file's rule: its bucket and key. */
export function fileRule(node) {
  const attrs = node.li_attr || {};
  return `${attrs.bucket}/${String(attrs.key || "").replace(/^\/+/, "")}`;
}

/** The rules for a selection, in tree order: folder grants first unless under another, then files. */
export function rulesFromSelection(nodes, selected, grants) {
  const { byId } = index(nodes);
  const rules = [];
  for (const node of nodes) {
    const id = String(node.id);
    if (!selected.has(id) || hasAncestorIn(id, grants, byId)) continue;
    if (isFile(id)) rules.push(fileRule(node));
    else if (grants.has(id)) rules.push(folderRule(node));
  }
  return rules;
}

const VERBS = { read: "read", write: "write to", delete: "delete", admin: "administer" };

/** The rules in plain words, one line each: "everything in study/patient-7/, including files added later". */
export function describeRule(rule) {
  return rule.endsWith("/*")
    ? `everything in ${rule.slice(0, -1)}, including files added later`
    : rule;
}

/** "alice can read:" for the preview's heading. */
export function describeWho(username, action) {
  return `${username || "This user"} can ${VERBS[action] || action}:`;
}

export function describeCount(rules) {
  return `${rules.length} ${rules.length === 1 ? "rule" : "rules"}.`;
}
