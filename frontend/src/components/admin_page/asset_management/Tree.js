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
  cascadeSelection = false
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
        cascadeSelection={cascadeSelection}
        />
      ))}
    </SimpleTreeView>
  );
}

function TreeNode({ node, selected, onChange, disableFileSelection, disableFolderSelection, cascadeSelection}) {
   const id = String(node.id);
  const isFile = id.startsWith("file-");
  const checked = selected.has(String(node.id));
  const isFolder = node.children && node.children.length > 0;

  const toggle = () => {
     if ((disableFileSelection && isFile) || (disableFolderSelection && isFolder)) return;
    const next = new Set(selected);

    if (cascadeSelection) {
      if (checked) unselectSubtree(next, node);
      else selectSubtree(next, node);
    } else {
      const id = String(node.id);
      if (checked) next.delete(id);
      else next.add(id);
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
          cascadeSelection={cascadeSelection}
          />
        ))}
    </TreeItem>
  );
}

/* ---------------- helpers  ---------------- */

function buildTreeFromFlat(list) {
  if (!Array.isArray(list) || list.length === 0) return [];
  const map = Object.create(null);

  // create a node shell for every id once
  for (const it of list) {
    const id = String(it.id);
    if (!map[id]) map[id] = { id, text: it.text || nameFromId(id), children: [] };
    else if (!map[id].text) map[id].text = it.text || nameFromId(id);
  }

  const roots = [];

  // attach each node to its parent (or make it a root)
  for (const it of list) {
    const id = String(it.id);
    const parent = it.parent;
    const node = map[id];

    if (parent && parent !== "#" && parent !== id) {
      const pid = String(parent);
      if (!map[pid]) map[pid] = { id: pid, text: nameFromId(pid), children: [] };
      map[pid].children.push(node);
    } else {
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

function nameFromId(id) {
  const s = String(id);
  const parts = s.endsWith("/") ? s.slice(0, -1).split("/") : s.split("/");
  const base = parts[parts.length - 1];
  return s.endsWith("/") ? base + "/" : base;
}
