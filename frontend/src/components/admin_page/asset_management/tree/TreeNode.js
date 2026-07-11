import React from "react";
import { Checkbox, CircularProgress } from "@mui/material";
import FolderOpenRoundedIcon from "@mui/icons-material/FolderOpenRounded";
import FolderRoundedIcon from "@mui/icons-material/FolderRounded";
import InsertDriveFileRoundedIcon from "@mui/icons-material/InsertDriveFileRounded";
import Inventory2RoundedIcon from "@mui/icons-material/Inventory2Rounded";
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
 * TreeNode renders a single row in the virtualized tree.
 * Replaces the old recursive TreeNode + MUI TreeItem.
 *
 * Props:
 *   - node: The tree node object (id, text, parent, children, _parentRef).
 *   - depth: Nesting depth (0 = root).
 *   - isExpanded: Whether this folder is currently expanded.
 *   - selected: A React Set<string> storing selected node IDs.
 *   - onChange: Callback triggered when node selection changes.
 *   - disableFileSelection, disableFolderSelection, disableCascade
 *   - onToggleExpand: Called with node id when chevron is clicked.
 */
export default function TreeNode({
  node,
  depth,
  isExpanded,
  selected,
  onChange,
  disableFileSelection,
  disableFolderSelection,
  disableCascade,
  onToggleExpand,
  isLoading = false,
}) {
  const id = String(node.id);
  const hasChildren = Array.isArray(node.children) && node.children.length > 0;
  const hasExpandableChildren = hasChildren || Boolean(node.li_attr?.has_children);
  const nodeType = getNodeType(node, id, hasExpandableChildren);
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

  const handleChevronClick = (e) => {
    e.stopPropagation();
    if (hasExpandableChildren && !isLoading) {
      onToggleExpand(id, node);
    }
  };

  return (
    <div
      className={getNodeLabelClassName(checked, disabled)}
      onClick={toggle}
      style={{ height: 40, display: "flex", alignItems: "center" }}
    >
      {/* Indent spacer */}
      <div style={{ width: depth * 20, flexShrink: 0 }} />

      {/* Expand/collapse chevron */}
      <div
        className={[
          "tree-row-chevron",
          !hasExpandableChildren && "tree-row-chevron-hidden",
          isLoading && "tree-row-chevron-loading",
        ].filter(Boolean).join(" ")}
        onClick={handleChevronClick}
        aria-label={isLoading ? "Loading folder contents" : undefined}
      >
        {isLoading ? (
          <CircularProgress size={14} thickness={5} />
        ) : isExpanded ? (
          "\u25BC"
        ) : (
          "\u25B6"
        )}
      </div>

      <span className="tree-node-control">
        <TreeNodeIcon type={nodeType} />
        <Checkbox
          size="small"
          checked={checked}
          disabled={disabled}
          onChange={toggle}
          onClick={(event) => event.stopPropagation()}
          className="tree-checkbox"
        />
      </span>
      <span className="tree-node-text" title={node.text}>
        {node.text}
      </span>
    </div>
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
