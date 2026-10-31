/**
 * Steps for features/filtered-selection.feature (requirement AC-4).
 *
 * Renders the real Tree with a stateful selection and drives it the way a user would.
 */
import React, { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { defineFeature, loadFeature } from "jest-cucumber";
import Tree from "./index.js";

// The virtualizer measures the scroll container, which jsdom can't do, so render every row.
jest.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }) => ({
    getTotalSize: () => count * 40,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({
        index,
        key: index,
        start: index * 40,
        size: 40,
      })),
  }),
}));

const feature = loadFeature("./features/filtered-selection.feature", {
  loadRelativePath: true,
});

// Builds the flat node list the portal's API returns: folders have ids ending in "/",
// files have "file-<path>" ids and their full path in li_attr.key.
function nodesFromPaths(paths) {
  const nodes = new Map();
  for (const path of paths) {
    const parts = path.split("/");
    let parent = "#";
    for (let i = 0; i < parts.length - 1; i++) {
      const id = `${parts.slice(0, i + 1).join("/")}/`;
      if (!nodes.has(id)) nodes.set(id, { id, parent, text: `${parts[i]}/` });
      parent = id;
    }
    const id = `file-${path}`;
    nodes.set(id, { id, parent, text: parts[parts.length - 1], li_attr: { key: path } });
  }
  return [...nodes.values()];
}

function rowFor(text) {
  return screen.getByText(text, { selector: ".tree-node-text" }).closest(".tree-node-label");
}

function selectionAsPaths(selection) {
  return [...selection].map((id) => id.replace(/^file-/, "")).sort();
}

defineFeature(feature, (test) => {
  let selection;

  function Harness({ nodes }) {
    const [selected, setSelected] = useState(new Set());
    selection = selected;
    return <Tree nodes={nodes} selected={selected} onChange={setSelected} enableSearch />;
  }

  const givenTheBucket = (given) => {
    given(/^the bucket "(.*)" contains:$/, (_bucket, table) => {
      render(<Harness nodes={nodesFromPaths(table.map((row) => row.path))} />);
    });
  };

  const whenFiltering = (when) => {
    when(/^the user filters for "(.*)"$/, async (pattern) => {
      fireEvent.change(screen.getByPlaceholderText(/Filter paths/), {
        target: { value: pattern },
      });
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      // The filter applies in a React transition; wait for the tree to show it.
      await waitFor(() => expect(screen.queryByText("Searching...")).not.toBeInTheDocument());
    });
  };

  const whenClicking = (step) => {
    step(/^the user clicks the row "(.*)"$/, (text) => {
      fireEvent.click(rowFor(text));
    });
  };

  const whenExpanding = (step) => {
    step(/^the user expands "(.*)"$/, (text) => {
      fireEvent.click(within(rowFor(text)).getByText("\u25B6"));
    });
  };

  const thenSelectionIs = (step) => {
    step(/^the selection is exactly "(.*)"$/, (paths) => {
      expect(selectionAsPaths(selection)).toEqual(paths.split(", ").sort());
    });
  };

  const thenSelectionIsEmpty = (step) => {
    step("the selection is empty", () => {
      expect(selection.size).toBe(0);
    });
  };

  test("Under a filter, a folder selects only the files the filter shows", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenFiltering(when);
    whenClicking(and);
    thenSelectionIs(then);
  });

  test("Clicking the folder again deselects what it showed", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenFiltering(when);
    whenClicking(and);
    whenClicking(and);
    thenSelectionIsEmpty(then);
  });

  test("A folder shows as partly selected when only some of what it shows is", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenFiltering(when);
    whenExpanding(and);
    whenClicking(and);
    then(/^the checkbox for "(.*)" is partly checked$/, (text) => {
      expect(within(rowFor(text)).getByRole("checkbox")).toHaveAttribute("data-indeterminate", "true");
    });
  });

  test("Selecting the only visible file in a folder doesn't select the folder", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenFiltering(when);
    whenExpanding(and);
    whenExpanding(and);
    whenClicking(and);
    thenSelectionIs(then);
  });

  test("A folder whose own name matches the filter is selected whole", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenFiltering(when);
    whenExpanding(and);
    whenClicking(and);
    thenSelectionIs(then);
  });

  test("Without a filter, selecting a folder selects everything in it", ({ given, when, then }) => {
    givenTheBucket(given);
    whenClicking(when);
    thenSelectionIs(then);
  });

  test("Under \"Find in selection\", clicking a folder acts only on the selected items it shows", ({ given, when, and, then }) => {
    givenTheBucket(given);
    whenExpanding(when);
    whenClicking(and);
    and(/^the user turns on "(.*)"$/, (label) => {
      fireEvent.click(screen.getByLabelText(label));
    });
    whenClicking(and);
    thenSelectionIsEmpty(then);
  });
});
