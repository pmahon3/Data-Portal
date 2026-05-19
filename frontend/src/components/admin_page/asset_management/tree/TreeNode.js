import React from "react";
import { Checkbox } from "@mui/material";
import FolderOpenRoundedIcon from "@mui/icons-material/FolderOpenRounded";
import FolderRoundedIcon from "@mui/icons-material/FolderRounded";
import InsertDriveFileRoundedIcon from "@mui/icons-material/InsertDriveFileRounded";
import Inventory2RoundedIcon from "@mui/icons-material/Inventory2Rounded";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import {
  checkAncestors,
  selectSubtree,
  uncheckAncestors,
  unselectSubtree,
} from "./TreeUtils.js";

const NODE_ICON_BY_TYPE = {
  bucket: {
    Icon: Inventory2RoundedIcon,
    className: "tree-node-icon-bucket",
  },
  folder: {
    Icon: FolderRoundedIcon,
    className: "tree-node-icon-folder",
  },
  emptyFolder: {
    Icon: FolderOpenRoundedIcon,
    className: "tree-node-icon-empty-folder",
  },
  file: {
    Icon: InsertDriveFileRoundedIcon,
    className: "tree-node-icon-file",
  },
};

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
  const hasChildren = Array.isArray(node.children) && node.children.length > 0;
  const nodeType = getNodeType(node, id, hasChildren);
  const isFile = nodeType === "file";
  const isFolder = nodeType !== "file";
  const checked = selected.has(id);
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

  const handleLabelClick = () => {
    toggle();
  };

  return (
    <TreeItem
      itemId={id}
      label={
        <div
          className={getNodeLabelClassName(checked, disabled)}
          onClick={handleLabelClick}
        >
          <span className="tree-node-control">
            <TreeNodeIcon type={nodeType} />
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
          </span>
          <span className="tree-node-text">{node.text}</span>
        </div>
      }
    >
      {/* Child nodes are rendered recursively so folder behavior stays the same
          no matter how deep the nesting goes. */}
      {hasChildren &&
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

function getNodeType(node, id, hasChildren) {
  if (id.startsWith("file-")) return "file";
  if (node._parentId === null || node.parent === "#") return "bucket";
  return hasChildren ? "folder" : "emptyFolder";
}

function getNodeLabelClassName(checked, disabled) {
  return [
    "tree-node-label",
    checked && "tree-node-label-checked",
    disabled && "tree-node-label-disabled",
  ]
    .filter(Boolean)
    .join(" ");
}

function TreeNodeIcon({ type }) {
  const { Icon, className } =
    NODE_ICON_BY_TYPE[type] ?? NODE_ICON_BY_TYPE.file;

  return (
    <span className={`tree-node-icon ${className}`} aria-hidden="true">
      <Icon fontSize="inherit" />
    </span>
  );
}
