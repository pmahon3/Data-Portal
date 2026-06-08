import React, { useMemo, useState, useTransition } from "react";
import { CircularProgress } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import TreeFilter from "./TreeFilter.js";
import TreeNode from "./TreeNode.js";
import {
  SEARCH_MODES,
  buildTreeFromFlat,
  createPathMatcher,
  filterNodes,
  isValidSearchPattern,
  trimFilterText,
} from "./TreeUtils.js";
import "./Tree.css";

/**
 * A hierarchical tree component using Material-UI's SimpleTreeView.
 * 
 * Props:
 *   - nodes: A flat array of node objects mimicking jsTree format [{ id, parent, text, li_attr }].
 *   - selected: A React Set<string> storing selected node IDs.
 *   - onChange: Callback function triggered on selection change; receives the new Set<string>.
 *   - disableFileSelection: If true, disables the checkbox for file nodes (id starts with "file-").
 *   - disableFolderSelection: If true, disables the checkbox for folder nodes.
 *   - disableCascade: If true, prevents cascading checking/unchecking between parents and children.
 *       or selection using glob or regex mode.
 *   - actions: Optional controls rendered inline with the search input.
 */
export default function Tree({
  nodes = [],
  selected,
  onChange,
  disableFileSelection = false,
  disableFolderSelection = false,
  disableCascade = false,
  enableSearch = false,
  actions = null,
}) {
  // States for draft input, applied input and whether to only filter selected nodes
  const [filterText, setFilterText] = useState("");
  const [appliedFilterText, setAppliedFilterText] = useState("");
  const [filterMode, setFilterMode] = useState(SEARCH_MODES.GLOB);
  const [appliedFilterMode, setAppliedFilterMode] = useState(SEARCH_MODES.GLOB);
  const [filterSelectedOnly, setFilterSelectedOnly] = useState(false);
  const [isSearching, startSearchTransition] = useTransition();

  const isPatternValid = useMemo(
    () => isValidSearchPattern(filterText, filterMode),
    [filterText, filterMode],
  );

  // We compile the applied search text into a matcher once so filtering work
  // stays cheap while the user clicks around the tree.
  const pathMatcher = useMemo(
    () => createPathMatcher(appliedFilterText, appliedFilterMode),
    [appliedFilterText, appliedFilterMode],
  );

  // These booleans drive small UI details such as whether the search button
  // should be enabled and whether the empty state should say "No matches".
  const filterState = useMemo(() => {
    const draftTrimmed = trimFilterText(filterText);
    const appliedTrimmed = trimFilterText(appliedFilterText);
    const draftText =
      filterMode === SEARCH_MODES.REGEX
        ? draftTrimmed
        : draftTrimmed.toLowerCase();
    const appliedText =
      appliedFilterMode === SEARCH_MODES.REGEX
        ? appliedTrimmed
        : appliedTrimmed.toLowerCase();
    const hasSearchText = Boolean(draftTrimmed || appliedTrimmed);

    return {
      hasActiveFilter: Boolean(pathMatcher || filterSelectedOnly),
      hasPendingSearch:
        isPatternValid &&
        (draftText !== appliedText ||
          (hasSearchText && filterMode !== appliedFilterMode)),
      hasSearchText,
      isPatternValid,
    };
  }, [
    filterText,
    appliedFilterText,
    filterSelectedOnly,
    pathMatcher,
    filterMode,
    appliedFilterMode,
    isPatternValid,
  ]);

  const applyFilter = () => {
    if (!isPatternValid) return;

    startSearchTransition(() => {
      setAppliedFilterText(filterText);
      setAppliedFilterMode(filterMode);
    });
  };

  // Clear draft and applied input and show unfiltered tree
  const clearFilter = () => {
    startSearchTransition(() => {
      setFilterText("");
      setAppliedFilterText("");
    });
  };

  // Filter the nodes based on user criteria
  const filteredNodes = useMemo(() => {
    return filterNodes(nodes, {
      pathMatcher,
      selected,
      selectedOnly: filterSelectedOnly,
    });
  }, [nodes, pathMatcher, filterSelectedOnly, selected]);

  // MUI renders a recursive structure, so we build that only after filtering.
  const tree = useMemo(() => buildTreeFromFlat(filteredNodes), [filteredNodes]);

  return (
    <div className="tree-container">
      <TreeFilter
        value={filterText}
        mode={filterMode}
        selectedOnly={filterSelectedOnly}
        filterState={filterState}
        onValueChange={setFilterText}
        onModeChange={setFilterMode}
        onSelectedOnlyChange={setFilterSelectedOnly}
        onApply={applyFilter}
        onClear={clearFilter}
        actions={actions}
      />

      {isSearching ? (
        <div className="tree-loading-state" role="status" aria-live="polite">
          <CircularProgress size={28} />
          <span>Searching...</span>
        </div>
      ) : tree.length === 0 ? (
        <div className="tree-empty-state">
          {filterState.hasActiveFilter ? "No matches." : "Empty."}
        </div>
      ) : (
        <SimpleTreeView
          className="tree-view"
          expansionTrigger="iconContainer"
          disableSelection
        >
          {tree.map((node) => (
            <TreeNode
              key={node.id}
              node={node}
              selected={selected}
              onChange={onChange}
              disableFileSelection={disableFileSelection}
              disableFolderSelection={disableFolderSelection}
              disableCascade={disableCascade}
            />
          ))}
        </SimpleTreeView>
      )}
    </div>
  );
}
