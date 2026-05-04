import React from "react";
import { Checkbox } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ClearIcon from "@mui/icons-material/Clear";
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
 *   - onValueChange: Callback triggered when the text input value changes.
 *   - onModeChange: Callback triggered when the regex toggle button is clicked.
 *   - onSelectedOnlyChange: Callback triggered when the "Search selected items only" checkbox is toggled.
 *   - onApply: Callback triggered when the search is submitted.
 *   - onClear: Callback triggered when the search filter is cleared.
 */
export default function TreeFilter({
  value,
  mode,
  selectedOnly,
  filterState,
  onValueChange,
  onModeChange,
  onSelectedOnlyChange,
  onApply,
  onClear,
}) {
  const isRegexMode = mode === SEARCH_MODES.REGEX;
  const helperText = isRegexMode
    ? filterState.isPatternValid
      ? "Regex mode uses JavaScript regular expressions."
      : "Invalid regex. Fix the pattern before searching."
    : "Glob mode uses * for many characters and ? for a single character.";

  return (
    <div className="tree-filter-group">
      <form
        className="tree-search-row"
        onSubmit={(event) => {
          event.preventDefault();
          onApply();
        }}
      >
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
        <button
          type="button"
          className={`tree-search-button${
            isRegexMode ? " tree-search-toggle-active" : ""
          }`}
          onClick={() =>
            onModeChange(
              isRegexMode ? SEARCH_MODES.GLOB : SEARCH_MODES.REGEX,
            )
          }
          title={isRegexMode ? "Switch to glob search" : "Switch to regex search"}
          aria-label={
            isRegexMode ? "Switch to glob search" : "Switch to regex search"
          }
          aria-pressed={isRegexMode}
        >
          <span>Regex</span>
        </button>
        {filterState.hasSearchText && (
          <button
            type="button"
            className="tree-search-button"
            onClick={onClear}
            title="Clear search"
            aria-label="Clear search"
          >
            <ClearIcon fontSize="small" />
          </button>
        )}
        <button
          type="submit"
          className="tree-search-button tree-search-primary"
          disabled={!filterState.hasPendingSearch}
          title="Apply search"
          aria-label="Apply search"
        >
          <SearchIcon fontSize="small" />
          <span>Search</span>
        </button>
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
      <label className="tree-label">
        <Checkbox
          size="small"
          checked={selectedOnly}
          onChange={(event) => onSelectedOnlyChange(event.target.checked)}
          className="tree-checkbox"
        />
        Search selected items only
      </label>
    </div>
  );
}
