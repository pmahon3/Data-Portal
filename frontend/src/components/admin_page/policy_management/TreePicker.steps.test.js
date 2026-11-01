/**
 * Steps for features/policy-from-selection.feature (requirements AC-4, AC-5).
 *
 * Renders the picker over the real Tree with a stateful selection and drives it the way an
 * administrator would.
 */
import React, { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { defineFeature, loadFeature } from "jest-cucumber";
import TreePicker from "./TreePicker.js";

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

const feature = loadFeature("./features/policy-from-selection.feature", {
  loadRelativePath: true,
});

// Builds the flat node list /tree/dashboard returns: the bucket is the root folder, folders have
// numeric ids and their full_path, files have "file-<n>" ids and their key.
function nodesFromPaths(paths) {
  const nodes = new Map();
  let next = 1;
  const folderId = new Map();
  for (const path of paths) {
    const [bucket, ...parts] = path.split("/");
    if (!folderId.has(bucket)) {
      folderId.set(bucket, String(next++));
      nodes.set(bucket, { id: folderId.get(bucket), parent: "#", text: bucket, li_attr: { type: "folder", bucket } });
    }
    let parent = folderId.get(bucket);
    for (let i = 0; i < parts.length - 1; i++) {
      const fullPath = `/${parts.slice(0, i + 1).join("/")}/`;
      const key = `${bucket}${fullPath}`;
      if (!folderId.has(key)) {
        folderId.set(key, String(next++));
        nodes.set(key, {
          id: folderId.get(key),
          parent,
          text: parts[i],
          li_attr: { type: "folder", bucket, full_path: fullPath },
        });
      }
      parent = folderId.get(key);
    }
    nodes.set(path, {
      id: `file-${next++}`,
      parent,
      text: parts[parts.length - 1],
      li_attr: { type: "file", bucket, key: parts.join("/") },
    });
  }
  return [...nodes.values()];
}

// Folders are written with a trailing "/" in the feature; the tree shows their names.
function rowFor(text) {
  return screen.getByText(text.replace(/\/$/, ""), { selector: ".tree-node-text" }).closest(".tree-node-label");
}

defineFeature(feature, (test) => {
  let rules;

  function Harness({ nodes }) {
    const [selected, setSelected] = useState(new Set());
    return (
      <TreePicker
        nodes={nodes}
        selected={selected}
        onSelectedChange={setSelected}
        username="alice"
        action="read"
        onRulesChange={(next) => { rules = next; }}
      />
    );
  }

  const background = (given, and) => {
    given(/^the bucket "(.*)" contains:$/, (_bucket, table) => {
      rules = [];
      render(<Harness nodes={nodesFromPaths(table.map((row) => row.path))} />);
    });
    and(/^the admin has opened "(.*)"$/, (text) => {
      fireEvent.click(within(rowFor(text)).getByText("▶"));
    });
  };

  const ticks = (step) => {
    step(/^the admin ticks "(.*)"$/, (text) => {
      fireEvent.click(rowFor(text));
    });
  };

  const expands = (step) => {
    step(/^the admin expands "(.*)"$/, (text) => {
      fireEvent.click(within(rowFor(text)).getByText("▶"));
    });
  };

  const filters = (step) => {
    step(/^the admin filters for "(.*)"$/, async (pattern) => {
      fireEvent.change(screen.getByPlaceholderText(/Filter paths/), { target: { value: pattern } });
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      // The filter applies in a React transition; wait for the tree to show it.
      await waitFor(() => expect(screen.queryByText("Searching...")).not.toBeInTheDocument());
    });
  };

  const rulesAre = (step) => {
    step(/^the rules are exactly "(.*)"$/, (expected) => {
      expect([...rules].sort()).toEqual(expected.split(", ").sort());
    });
  };

  const previewSays = (step) => {
    step(/^the preview says "(.*)"$/, (text) => {
      expect(screen.getByRole("region", { name: "Rules to create" })).toHaveTextContent(text);
    });
  };

  test("A ticked folder grants everything in it including files added later", ({ given, and, when, then }) => {
    background(given, and);
    ticks(when);
    rulesAre(then);
    previewSays(and);
    previewSays(and);
    previewSays(and);
  });

  test("Ticked files are granted one by one", ({ given, and, when, then }) => {
    background(given, and);
    ticks(when);
    expands(and);
    ticks(and);
    rulesAre(then);
    previewSays(and);
  });

  test("Ticking every file in a folder still grants only those files", ({ given, and, when, then }) => {
    background(given, and);
    expands(when);
    ticks(and);
    rulesAre(then);
  });

  test("A partly ticked folder grants the ticked files", ({ given, and, when, then }) => {
    background(given, and);
    ticks(when);
    expands(and);
    ticks(and);
    rulesAre(then);
  });

  test("The bucket itself grants everything in it", ({ given, and, when, then }) => {
    background(given, and);
    ticks(when);
    rulesAre(then);
    previewSays(and);
  });

  test("Under a filter a folder grants only the files the filter shows", ({ given, and, when, then }) => {
    background(given, and);
    filters(when);
    ticks(and);
    rulesAre(then);
  });

  test("Under a filter a folder matching it is granted file by file", ({ given, and, when, then }) => {
    background(given, and);
    filters(when);
    ticks(and);
    rulesAre(then);
  });
});
