import React from "react";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { Checkbox } from "@mui/material";

/*
  Props:
    - nodes: jsTree flat array [{ id, parent, text }]
    - selected: Set<string>
    - onChange(nextSet: Set<string>)
*/
export default function Tree({ 
  nodes = [], selected, onChange, 
  disableFileSelection = false,  
  disableFolderSelection = false,
  disableCascade = false
}) {
  const tree = buildTreeFromFlat(nodes);      // nested [{ id, text, children }]
  if (tree.length === 0) {
    return <div style={{ fontSize: 12, color: "#6b7280" }}>No items.</div>;
  }

  // expand root folders by default
  const rootIds = tree.map(n => String(n.id));

  return (
    <SimpleTreeView defaultExpandedItems={rootIds}>
      {tree.map((n) => (
        <TreeNode key={n.id} node={n} selected={selected} onChange={onChange} disableFileSelection={disableFileSelection}
        disableFolderSelection={disableFolderSelection}
        disableCascade={disableCascade}
        />
      ))}
    </SimpleTreeView>
  );
}

function TreeNode({ node, selected, onChange, disableFileSelection, disableFolderSelection, disableCascade}) {
   const id = String(node.id);
  const isFile = id.startsWith("file-");
  const checked = selected.has(String(node.id));
  const isFolder = node.children && node.children.length > 0;

  const toggle = () => {
     if ((disableFileSelection && isFile) || (disableFolderSelection && isFolder)) return;
    const next = new Set(selected);

    if (disableCascade) {
      const id = String(node.id);
      if (checked) next.delete(id);
      else next.add(id);
    } else {
      if (checked) {
        unselectSubtree(next, node);
        uncheckAncestors(next, node);
      } else {
        selectSubtree(next, node);
        checkAncestors(next, node);
      }
    }

    onChange(next);
  };

  return (
    <TreeItem
      itemId={String(node.id)}
      label={
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Checkbox
            size="small"
            checked={checked}
            disabled={(disableFileSelection && isFile) || (disableFolderSelection && isFolder)}
            onChange={toggle}
            onClick={(e) => e.stopPropagation()} // don’t collapse when clicking the checkbox
          />
          <span style={{ userSelect: "none" }}>{node.text}</span>
        </div>
      }
    >
      {isFolder &&
        node.children.map((c) => (
          <TreeNode 
          key={c.id} 
          node={c} 
          selected={selected} 
          onChange={onChange} 
          disableFileSelection={disableFileSelection}
          disableFolderSelection={disableFolderSelection}
          disableCascade={disableCascade}
          />
        ))}
    </TreeItem>
  );
}

/* ---------------- helpers  ---------------- */

// Converts a flat array of objects into a hierarchical tree structure.
function buildTreeFromFlat(list) {
  if (!Array.isArray(list) || list.length === 0) return [];
  const map = Object.create(null);

  // First Pass: Create a "shell" or reference for every node in the list
  for (const it of list) {
    const id = String(it.id);

    // If the node isn't in our map yet, initialize it with basic properties
    if (!map[id]) map[id] = { id, text: it.text || nameFromId(id), children: [] };
    // If the node exists, ensure its text is populated
    else if (!map[id].text) map[id].text = it.text || nameFromId(id);

    // Store the parent reference temporarily on the node object.
    // Handles "#" as a common convention for "root" or no parent.
    map[id]._parentId = it.parent && it.parent !== "#" ? String(it.parent) : null;
  }

  const roots = [];

  // Second Pass: Establish parent-child relationships
  for (const it of list) {
    const id = String(it.id);
    const parent = it.parent;
    const node = map[id];

    // Check if the node has a valid parent
    if (parent && parent !== "#" && parent !== id) {
      const pid = String(parent);
      // Placeholder Logic: If the parent doesn't exist in the map yet
      if (!map[pid]) map[pid] = { id: pid, text: nameFromId(pid), children: [] };

      // Link the current node to its parent's children array
      map[pid].children.push(node);

      // Store reference of parent in current node  
      node._parentRef = map[pid];
    } else {
      // If no valid parent exists, this node is a top-level root
      roots.push(node);
    }
  }

  // simple sort by text for stable display
  sortByText(roots);
  return roots;
}

function sortByText(arr) {
  arr.sort((a, b) => String(a.text).localeCompare(String(b.text)));
  for (const n of arr) {
    if (n.children && n.children.length) sortByText(n.children);
  }
}

function selectSubtree(sel, node) {
  sel.add(String(node.id));
  if (node.children) node.children.forEach((c) => selectSubtree(sel, c));
}
function unselectSubtree(sel, node) {
  sel.delete(String(node.id));
  if (node.children) node.children.forEach((c) => unselectSubtree(sel, c));
}

function checkAncestors(sel, node) {
  // If there is no parent reference, we've reached the root of the tree
  if (!node._parentRef) return;

  const p = node._parentRef;

  // Check the status of all children belonging to this parent
  const allSiblingsChecked = p.children.every((c) => sel.has(String(c.id)));

  // If all children (the current node and its siblings) are checked, add the parent
  if (allSiblingsChecked) {
    sel.add(String(p.id));

    // Continue moving up the tree to check the grandparent
    checkAncestors(sel, p);
  }
}

function uncheckAncestors(sel, node) {
  // If there is no parent reference, we've reached the root
  if (!node._parentRef) return;

  const p = node._parentRef;

  // If the parent is marked as selected, we must remove it because 
  // one of its child (this node) was just unselected.
  if (sel.has(String(p.id))) {
    sel.delete(String(p.id));

    // Continue moving up the tree to uncheck the grandparent
    uncheckAncestors(sel, p);
  }
}

function nameFromId(id) {
  const s = String(id);
  const parts = s.endsWith("/") ? s.slice(0, -1).split("/") : s.split("/");
  const base = parts[parts.length - 1];
  return s.endsWith("/") ? base + "/" : base;
}
