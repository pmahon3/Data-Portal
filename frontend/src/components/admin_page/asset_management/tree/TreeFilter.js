import React from "react";
import { CircularProgress } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ClearIcon from "@mui/icons-material/Clear";
import TableRowsIcon from "@mui/icons-material/TableRows";
import { SEARCH_MODES } from "./TreeUtils.js";

/**
 * TreeFilter is intentionally presentational.
 * It receives derived state from the parent so the filtering rules stay in one
 * place while the UI remains easy to reuse and adjust.
 * 
 * Props:
 *   - value: The current text value in the search input.
 *   - mode: Either "glob" or "regex" to control how the input is interpreted.
 *   - selectedOnly: Boolean indicating if the user has chosen to view only selected items.
 *   - filterState: An object specifying ui-derived states like
 *       { hasSearchText, hasPendingSearch, isPatternValid }.
 *   - isSearching: Boolean indicating whether the tree is applying a search.
 *   - onValueChange: Callback triggered when the text input value changes.
 *   - onModeChange: Callback triggered when the regex toggle button is clicked.
 *   - onSelectedOnlyChange: Callback triggered when the "Search selected items only" checkbox is toggled.
 *   - onApply: Callback triggered when the search is submitted.
 *   - onClear: Callback triggered when the search filter is cleared.
 *   - actions: Optional controls displayed inline with the search input.
 */
export default function TreeFilter({
  value,
  mode,
  selectedOnly,
  filterState,
  isSearching,
  onValueChange,
  onModeChange,
  onSelectedOnlyChange,
  onApply,
  onClear,
  actions,
}) {
  const isRegexMode = mode === SEARCH_MODES.REGEX;
  const helperText = isRegexMode
    ? filterState.isPatternValid
      ? "Regex mode uses JavaScript regular expressions."
      : "Invalid regex. Fix the pattern before searching."
    : "Search uses * for many characters and ? for a single character.";

  return (
    <div className="tree-filter-group">
      <form
        className="tree-search-row"
        onSubmit={(event) => {
          event.preventDefault();
          onApply();
        }}
      >
        <div className="tree-search-wrapper">
          <input
            type="text"
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            placeholder={
              isRegexMode ? "Filter paths with regex" : "Filter paths, e.g. *.csv"
            }
            className="tree-input"
            aria-invalid={isRegexMode && !filterState.isPatternValid}
          />
          <div className="tree-search-actions search-actions">
            <button
              type="button"
              className={`tree-search-button action-icon${
                selectedOnly ? " tree-search-toggle-active" : ""
              }`}
              onClick={() => onSelectedOnlyChange(!selectedOnly)}
              title="Find in selection"
              aria-label="Find in selection"
              aria-pressed={selectedOnly}
            >
              <TableRowsIcon fontSize="small" />
            </button>
            <button
              type="button"
              className={`tree-search-button action-icon${
                isRegexMode ? " tree-search-toggle-active" : ""
              }`}
              onClick={() =>
                onModeChange(
                  isRegexMode ? SEARCH_MODES.GLOB : SEARCH_MODES.REGEX,
                )
              }
              title="Use Regular Expression"
              aria-label="Use Regular Expression"
              aria-pressed={isRegexMode}
            >
              <span>(.*)</span>
            </button>
            {filterState.hasSearchText && (
              <button
                type="button"
                className="tree-search-button action-icon"
                onClick={onClear}
                title="Clear search"
                aria-label="Clear search"
              >
                <ClearIcon fontSize="small" />
              </button>
            )}
            <button
              type="submit"
              className="tree-search-button action-icon tree-search-primary"
              disabled={!filterState.hasPendingSearch || isSearching}
              title={isSearching ? "Searching" : "Search"}
              aria-label={isSearching ? "Searching" : "Search"}
              aria-busy={isSearching}
            >
              {isSearching ? (
                <CircularProgress size={14} sx={{ color: "#fff" }} />
              ) : (
                <SearchIcon fontSize="small" />
              )}
            </button>
          </div>
        </div>
        {actions && <div className="tree-filter-actions">{actions}</div>}
      </form>
      <div
        className={`tree-filter-helper${
          isRegexMode && !filterState.isPatternValid
            ? " tree-filter-helper-error"
            : ""
        }`}
      >
        {helperText}
      </div>
    </div>
  );
}
