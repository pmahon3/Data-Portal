import React, { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { CircularProgress } from "@mui/material";
import { useVirtualizer } from "@tanstack/react-virtual";
import TreeFilter from "./TreeFilter.js";
import TreeNode from "./TreeNode.js";
import {
  SEARCH_MODES,
  buildTreeFromFlat,
  createPathMatcher,
  filterNodes,
  flattenVisibleTree,
  isValidSearchPattern,
  trimFilterText,
} from "./TreeUtils.js";
import "./Tree.css";

/**
 * A virtualized hierarchical tree component.
 * 
 * Props:
 *   - nodes: A flat array of node objects [{ id, parent, text, li_attr }].
 *   - selected: A React Set<string> storing selected node IDs.
 *   - onChange: Callback on selection change; receives the new Set<string>.
 *   - disableFileSelection: If true, disables checkboxes for file nodes.
 *   - disableFolderSelection: If true, disables checkboxes for folder nodes.
 *   - disableCascade: If true, no cascading between parents and children.
 *   - enableSearch: If true, shows the search/filter UI.
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

  // Tracks which nodes are expanded
  const [expandedIds, setExpandedIds] = useState(new Set());

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

  const tree = useMemo(() => buildTreeFromFlat(filteredNodes), [filteredNodes]);

  // Collapse when filter is cleared.
  useEffect(() => {
    if (!filterState.hasActiveFilter && !filterState.hasSearchText) {
      setExpandedIds(new Set());
    }
  }, [filterState.hasActiveFilter, filterState.hasSearchText]);

  // flatten visible nodes for virtualization
  const flatNodes = useMemo(
    () => flattenVisibleTree(tree, expandedIds),
    [tree, expandedIds],
  );

  // toggle expand / collapse
  const toggleExpand = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // virtualizer
  const scrollRef = useRef(null);
  const virtualizer = useVirtualizer({
    count: flatNodes.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 40,
    getItemKey: (index) => flatNodes[index].node.id,
  });

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
        /* Virtual scroll container — height is capped so the tree
           doesn't push everything else off screen. */           
        <div
          ref={scrollRef}
          className="tree-virtual-container"
        >
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: "100%",
              position: "relative",
            }}
          >
            {virtualizer.getVirtualItems().map((virtualItem) => {
              const { node, depth } = flatNodes[virtualItem.index];
              return (
                <div
                  key={virtualItem.key}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${virtualItem.size}px`,
                    transform: `translateY(${virtualItem.start}px)`,
                  }}
                >
                  <TreeNode
                    node={node}
                    depth={depth}
                    isExpanded={expandedIds.has(String(node.id))}
                    selected={selected}
                    onChange={onChange}
                    disableFileSelection={disableFileSelection}
                    disableFolderSelection={disableFolderSelection}
                    disableCascade={disableCascade}
                    onToggleExpand={toggleExpand}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
