import React from "react";
import { Checkbox } from "@mui/material";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import {
  checkAncestors,
  selectSubtree,
  uncheckAncestors,
  unselectSubtree,
} from "./TreeUtils.js";

/**
 * TreeNode renders one node plus all descendants.
 * The same component calls itself for child folders, which keeps the render
 * path and the selection behavior aligned at every level of the tree.
 * 
 * Props:
 *   - node: The tree node object (contains id, text, parent, and optionally children).
 *   - selected: A React Set<string> storing selected node IDs.
 *   - onChange: Callback function triggered when node selection changes.
 *   - disableFileSelection: If true, disables the checkbox for file nodes.
 *   - disableFolderSelection: If true, disables the checkbox for folder nodes.
 *   - disableCascade: If true, prevents cascading checking/unchecking between parents and children.
 */
export default function TreeNode({
  node,
  selected,
  onChange,
  disableFileSelection,
  disableFolderSelection,
  disableCascade,
}) {
  const id = String(node.id);
  const isFile = id.startsWith("file-");
  const checked = selected.has(id);
  const isFolder = node.children && node.children.length > 0;
  const disabled =
    (disableFileSelection && isFile) ||
    (disableFolderSelection && isFolder);

  // Toggling always starts from a fresh Set copy because the parent stores
  // selection in React state and expects immutable updates.
  const toggle = () => {
    if (disabled) return;

    const next = new Set(selected);

    if (disableCascade) {
      // Write mode uses this branch so only the clicked node changes.
      if (checked) next.delete(id);
      else next.add(id);
    } else if (checked) {
      // Unchecking removes the node, every descendant, and any now-invalid
      // selected ancestors above it.
      unselectSubtree(next, node);
      uncheckAncestors(next, node);
    } else {
      // Checking adds the full subtree first, then walks upward so parents
      // become selected only when all of their children are selected.
      selectSubtree(next, node);
      checkAncestors(next, node);
    }

    onChange(next);
  };

  return (
    <TreeItem
      itemId={id}
      label={
        <div className="tree-node-label">
          <Checkbox
            size="small"
            checked={checked}
            disabled={disabled}
            onChange={toggle}
            // MUI tree items also listen for click events to expand/collapse.
            // Stop propagation so checking a box does not also toggle the row.
            onClick={(event) => event.stopPropagation()}
            className="tree-checkbox"
          />
          <span className="tree-node-text">{node.text}</span>
        </div>
      }
    >
      {/* Child nodes are rendered recursively so folder behavior stays the same
          no matter how deep the nesting goes. */}
      {isFolder &&
        node.children.map((child) => (
          <TreeNode
            key={child.id}
            node={child}
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
