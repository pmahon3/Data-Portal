import React, { useCallback, useEffect, useMemo, useState } from "react";
import Tree from "../asset_management/tree/index.js";
import { describeCount, describeRule, describeWho, nextFolderGrants, ruleText, rulesFromSelection } from "./treeRules.js";

/**
 * Choosing what a policy covers from the file tree (DS-policy-from-selection; AC-4, AC-5).
 *
 * The parent holds the selection (so lazy loading can extend it) and receives the rules through
 * onRulesChange; this shows the rules in plain words before anything is saved.
 */
export default function TreePicker({
  nodes,
  selected,
  onSelectedChange,
  username,
  action,
  onRulesChange,
  ...treeProps
}) {
  // Folders the admin ticked themselves, with no filter active: only these become folder rules.
  const [grants, setGrants] = useState(new Set());
  const [filterActive, setFilterActive] = useState(false);

  const handleChange = (next) => {
    setGrants((current) => nextFolderGrants(current, selected, next, nodes, filterActive));
    onSelectedChange(next);
  };
  const handleFilterChange = useCallback((active) => setFilterActive(active), []);

  const rules = useMemo(() => rulesFromSelection(nodes, selected, grants), [nodes, selected, grants]);
  useEffect(() => {
    if (onRulesChange) onRulesChange(rules);
  }, [rules, onRulesChange]);

  return (
    <div className="pm-tree-picker">
      <Tree
        nodes={nodes}
        selected={selected}
        onChange={handleChange}
        promoteSelection={false}
        onFilterChange={handleFilterChange}
        enableSearch
        {...treeProps}
      />
      <section className="pm-rule-preview" aria-label="Rules to create">
        {rules.length === 0 ? (
          <p className="pm-muted">Tick files or folders to grant.</p>
        ) : (
          <>
            <p>{describeWho(username, action)}</p>
            <ul>
              {rules.map((rule) => <li key={ruleText(rule)}><code>{describeRule(rule)}</code></li>)}
            </ul>
            <p className="pm-muted">{describeCount(rules)}</p>
          </>
        )}
      </section>
    </div>
  );
}
