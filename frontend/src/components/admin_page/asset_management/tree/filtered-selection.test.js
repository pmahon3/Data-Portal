/**
 * Selecting a folder while a filter is active (INN-295).
 *
 * Under a filter the tree shows only part of each folder. Ticking a folder there should select only
 * the files it shows, so a download or delete can't act on files the filter hid. Renders the real
 * Tree and drives it the way a user would.
 */
import React, { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Tree from "./index.js";

// The virtualizer measures the scroll container, which jsdom can't do, so render every row.
jest.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }) => ({
    getTotalSize: () => count * 40,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({ index, key: index, start: index * 40, size: 40 })),
  }),
}));

// Known-failing until INN-295 is fixed: passes while the test fails, and fails once it passes.
// RUN_KNOWN_FAILING=1 runs it as written, to see the failure.
const knownFailing = (name, fn) =>
  process.env.RUN_KNOWN_FAILING ? test(name, fn) : test(`${name} (known-failing: INN-295)`, async () => {
    let failed = false;
    try {
      await fn();
    } catch {
      failed = true;
    }
    if (!failed) throw new Error("INN-295 looks fixed: remove knownFailing from this test");
  });

const PATHS = ["study/a.json", "study/b.csv", "study/sub/c.csv"];

// The flat node list the portal's API returns: folder ids end in "/", file ids are "file-<path>".
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
    nodes.set(`file-${path}`, { id: `file-${path}`, parent, text: parts[parts.length - 1], li_attr: { key: path } });
  }
  return [...nodes.values()];
}

let selection;

function Harness() {
  const [selected, setSelected] = useState(new Set());
  selection = selected;
  return <Tree nodes={nodesFromPaths(PATHS)} selected={selected} onChange={setSelected} enableSearch />;
}

async function filterFor(pattern) {
  fireEvent.change(screen.getByPlaceholderText(/Filter paths/), { target: { value: pattern } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(screen.queryByText("Searching...")).not.toBeInTheDocument());
}

function clickRow(text) {
  fireEvent.click(screen.getByText(text, { selector: ".tree-node-text" }).closest(".tree-node-label"));
}

knownFailing("under a filter, ticking a folder selects only the files the filter shows", async () => {
  render(<Harness />);
  await filterFor("*.csv");
  clickRow("study/");
  expect([...selection].sort()).toEqual(["file-study/b.csv", "file-study/sub/c.csv"]);
});
