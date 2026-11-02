/**
 * Turn a selection in the file tree into policy rules (requirements AC-4, AC-5, AC-10).
 *
 * The rules are the ones typing would make, with no conversion beyond them:
 *   - a folder the admin ticked, with no filter active: `bucket/folder/*` (covers files added later),
 *     leaving out whatever was then unticked inside it (AC-10)
 *   - a ticked file: `bucket/path/file.ext`, never collapsed into its folder
 *   - under a filter: one rule per file the filter shows
 * A folder becomes a folder rule only when it was ticked itself (a "folder grant"); the tree's
 * own selection can't tell that apart from a folder whose files were all ticked. Each rule is
 * `{ resource, excluded }`, as the policy API takes it.
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

function anythingSelected(id, selected, children) {
  if (selected.has(id)) return true;
  const inside = children.get(id) || [];
  return inside.some((child) => anythingSelected(child, selected, children));
}

/**
 * Return the folder grants after a change in the tree's selection. A folder newly selected with no
 * filter active was ticked itself; one selected under a filter only stands for the files the
 * filter shows. A grant lasts while anything in it stays ticked (what's unticked inside it is left
 * out), and lapses once nothing in it is, or once the selection was cleared from outside (a search
 * starting).
 */
export function nextFolderGrants(grants, previous, next, nodes, filterActive) {
  const { children } = index(nodes);
  const result = new Set(
    [...grants].filter(
      (id) => anythingSelected(id, previous, children) && anythingSelected(id, next, children),
    ),
  );
  if (!filterActive) {
    for (const id of next) {
      if (!isFile(id) && !previous.has(id)) result.add(id);
    }
  }
  return result;
}

/**
 * Return a folder's rule: its bucket and path, then "*". The bucket itself is `bucket/*`.
 * Example: bucket "study", full_path "/sub-01" -> "study/sub-01/*"
 */
export function folderRule(node) {
  const attrs = node.li_attr || {};
  let path = String(attrs.full_path || "/");
  if (!path.startsWith("/")) path = `/${path}`;
  if (!path.endsWith("/")) path = `${path}/`;
  return `${attrs.bucket}${path.replace(/\/{2,}/g, "/")}*`;
}

/**
 * Return a file's rule: its bucket and key.
 * Example: bucket "study", key "sub-01/anat/t1.nii" -> "study/sub-01/anat/t1.nii"
 */
export function fileRule(node) {
  const attrs = node.li_attr || {};
  return `${attrs.bucket}/${String(attrs.key || "").replace(/^\/+/, "")}`;
}

/**
 * Return what a folder grant leaves out: the largest unticked parts loaded inside it. A folder with
 * nothing ticked in it is left out whole (`folder/*`, so files added there later stay out too);
 * one with some things ticked is looked into; an unticked file is left out by name.
 */
function leftOut(id, selected, children, byId) {
  const out = [];
  for (const child of children.get(id) || []) {
    if (selected.has(child)) continue;
    if (isFile(child)) {
      out.push(fileRule(byId.get(child)));
    } else if (anythingSelected(child, selected, children)) {
      out.push(...leftOut(child, selected, children, byId));
    } else {
      out.push(folderRule(byId.get(child)));
    }
  }
  return out;
}

/** Return the rules for a selection, in tree order: folder grants (unless under another), then files. */
export function rulesFromSelection(nodes, selected, grants) {
  const { byId, children } = index(nodes);
  const rules = [];
  for (const node of nodes) {
    const id = String(node.id);
    if (hasAncestorIn(id, grants, byId)) continue;
    if (grants.has(id) && anythingSelected(id, selected, children)) {
      rules.push({ resource: folderRule(node), excluded: leftOut(id, selected, children, byId) });
    } else if (isFile(id) && selected.has(id)) {
      rules.push({ resource: fileRule(node), excluded: [] });
    }
  }
  return rules;
}

/**
 * Return a rule as one line of text, for keys and tests.
 * Example: "study/*" or "study/* leaving out study/sub-03/*"
 */
export function ruleText(rule) {
  if (!rule.excluded.length) return rule.resource;
  return `${rule.resource} leaving out ${rule.excluded.join(", ")}`;
}

const VERBS = { read: "read", write: "write to", delete: "delete", admin: "administer" };

/** Return an action as a verb in a sentence. Example: "write" -> "write to" */
export function verbFor(action) {
  return VERBS[action] || action;
}

const asWords = (path) => (path.endsWith("/*") ? path.slice(0, -1) : path);

/**
 * Return a rule in plain words.
 * Example: "everything in study/patient-7/ except study/patient-7/notes.txt, including files added later"
 */
export function describeRule(rule) {
  if (!rule.resource.endsWith("/*") && rule.resource !== "*") return rule.resource;
  let what = `everything in ${asWords(rule.resource)}`;
  if (rule.resource === "*") what = "everything on the instance";
  let except = "";
  if (rule.excluded.length) except = ` except ${rule.excluded.map(asWords).join(", ")}`;
  return `${what}${except}, including files added later`;
}

/** Return the preview's heading. Example: "alice can read:" */
export function describeWho(username, action) {
  return `${username || "This user"} can ${verbFor(action)}:`;
}

/** Return how many rules there are. Example: "2 rules." */
export function describeCount(rules) {
  return `${rules.length} ${rules.length === 1 ? "rule" : "rules"}.`;
}
