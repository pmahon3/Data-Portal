/**
 * Test suite for TreeUtils.js
 * 
 * This file contains unit tests for the utility functions used by the tree components.
 * It verifies functionalities such as hierarchal tree structing, cascade selection logic,
 * glob matching, and node filtering.
 */
import {
  SEARCH_MODES,
  buildTreeFromFlat,
  checkAncestors,
  collectFilteredSelection,
  createGlobMatcher,
  createPathMatcher,
  createRegexMatcher,
  filterNodes,
  flattenVisibleTree,
  getSearchablePath,
  isValidSearchPattern,
  selectSubtree,
  uncheckAncestors,
  unselectSubtree,
} from "./TreeUtils.js";
import { getSelectedDownloadIds, getSelectTopLevel } from "../EndpointCardUtils.js";

describe("tree helpers", () => {
  // Verifies that a flat array of nodes is correctly structured into a nested tree.
  // It also checks that both roots and children are sorted alphabetically.
  test("buildTreeFromFlat builds sorted nested roots and children", () => {
    const nodes = [
      { id: "folder-b/", parent: "#", text: "Folder B/" },
      { id: "file-2", parent: "folder-a/", text: "zeta.csv" },
      { id: "folder-a/", parent: "#", text: "Folder A/" },
      { id: "file-1", parent: "folder-a/", text: "alpha.csv" },
    ];

    const tree = buildTreeFromFlat(nodes);

    expect(tree.map((node) => node.id)).toEqual(["folder-a/", "folder-b/"]);
    expect(tree[0].children.map((node) => node.id)).toEqual(["file-1", "file-2"]);
  });

  // Confirms that filtering by a path retains the matching nodes along with 
  // all their parent directories, while excluding non-matching nodes.
  test("filterNodes keeps matching nodes with their ancestors", () => {
    const nodes = [
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folder/", parent: "root/", text: "folder/" },
      {
        id: "file-1",
        parent: "root/folder/",
        text: "keep.csv",
        li_attr: { key: "root/folder/keep.csv" },
      },
      {
        id: "file-2",
        parent: "root/folder/",
        text: "skip.txt",
        li_attr: { key: "root/folder/skip.txt" },
      },
    ];

    const filtered = filterNodes(nodes, {
      pathMatcher: createGlobMatcher("keep.csv"),
      selected: new Set(),
      selectedOnly: false,
    });

    expect(filtered.map((node) => node.id)).toEqual([
      "root/",
      "root/folder/",
      "file-1",
    ]);
  });

  // Tests that the custom glob matcher properly handles '*' (match anything) 
  // and '?' (match exactly one character) wildcards when matching file paths.
  test("createGlobMatcher supports star and question-mark wildcards", () => {
    const csvMatcher = createGlobMatcher("*.csv");
    const singleCharMatcher = createGlobMatcher("data-?.csv");

    expect(csvMatcher.test("root/folder/report.csv")).toBe(true);
    expect(csvMatcher.test("root/folder/report.txt")).toBe(false);
    expect(singleCharMatcher.test("root/data-a.csv")).toBe(true);
    expect(singleCharMatcher.test("root/data-aa.csv")).toBe(false);
  });

  test("createGlobMatcher applies filename globs to path segments", () => {
    const txtStartingWithA = createGlobMatcher("a*.txt");

    expect(txtStartingWithA.test("root/folder/alpha.txt")).toBe(true);
    expect(txtStartingWithA.test("root/folder/ALPHA.TXT")).toBe(true);
    expect(txtStartingWithA.test("root/folder/beta.txt")).toBe(false);
    expect(txtStartingWithA.test("root/archive/beta.txt")).toBe(false);
  });

  test("createGlobMatcher keeps plain text searches as substring matches", () => {
    const pngMatcher = createGlobMatcher(".png");

    expect(pngMatcher.test("root/folder/chart.png")).toBe(true);
    expect(pngMatcher.test("root/folder/chart.PNG")).toBe(true);
    expect(pngMatcher.test("root/folder/chart.jpg")).toBe(false);
  });

  test("createRegexMatcher supports case-insensitive regular expressions", () => {
    const regexMatcher = createRegexMatcher("\\.(txt|wav)$");

    expect(regexMatcher.test("root/folder/notes.TXT")).toBe(true);
    expect(regexMatcher.test("root/folder/sample.wav")).toBe(true);
    expect(regexMatcher.test("root/folder/report.csv")).toBe(false);
  });

  test("regex search patterns are validated before apply", () => {
    expect(isValidSearchPattern("\\.(txt|wav)$", SEARCH_MODES.REGEX)).toBe(true);
    expect(isValidSearchPattern("(", SEARCH_MODES.REGEX)).toBe(false);
    expect(isValidSearchPattern("*.csv", SEARCH_MODES.GLOB)).toBe(true);
  });

  test("filterNodes works with regex search mode", () => {
    const nodes = [
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folder/", parent: "root/", text: "folder/" },
      {
        id: "file-1",
        parent: "root/folder/",
        text: "notes.txt",
        li_attr: { key: "root/folder/notes.txt" },
      },
      {
        id: "file-2",
        parent: "root/folder/",
        text: "sample.wav",
        li_attr: { key: "root/folder/sample.wav" },
      },
      {
        id: "file-3",
        parent: "root/folder/",
        text: "ignore.csv",
        li_attr: { key: "root/folder/ignore.csv" },
      },
    ];

    const filtered = filterNodes(nodes, {
      pathMatcher: createPathMatcher("\\.(txt|wav)$", SEARCH_MODES.REGEX),
      selected: new Set(),
      selectedOnly: false,
    });

    expect(filtered.map((node) => node.id)).toEqual([
      "root/",
      "root/folder/",
      "file-1",
      "file-2",
    ]);
  });

  test("filter for selected only", () => {
    const nodes = [
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folderA/", parent: "root/", text: "folderA/" },
      { id: "root/folderB/", parent: "root/", text: "folderB/" },
      {
        id: "file-1",
        parent: "root/folderA/",
        text: "file.txt",
        li_attr: { key: "root/folderA/file.txt" },
      },
      {
        id: "file-2",
        parent: "root/folderB/",
        text: "file.txt",
        li_attr: { key: "root/folderB/file.txt" },
      },
    ];

    const filtered = filterNodes(nodes, {
      pathMatcher: createGlobMatcher("*.txt"),
      selected: new Set(["root/folderA/", "file-1"]),
      selectedOnly: true,
    });

    expect(filtered.map((node) => node.id)).toEqual([
      "root/",
      "root/folderA/",
      "file-1",
    ]);
  });

  // Checks the cascaded selection logic:
  // 1. Selecting a folder should recursively select its children and update ancestors.
  // 2. Unselecting a child should also dynamically cascade and unselect invalid ancestors.
  test("cascade helpers update descendants and ancestors", () => {
    const tree = buildTreeFromFlat([
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folder/", parent: "root/", text: "folder/" },
      { id: "file-1", parent: "root/folder/", text: "alpha.csv" },
      { id: "file-2", parent: "root/folder/", text: "beta.csv" },
    ]);
    const root = tree[0];
    const folder = root.children[0];
    const fileA = folder.children[0];

    const selection = new Set();
    selectSubtree(selection, folder);
    checkAncestors(selection, folder);

    expect(selection).toEqual(
      new Set(["root/", "root/folder/", "file-1", "file-2"]),
    );

    unselectSubtree(selection, fileA);
    uncheckAncestors(selection, fileA);

    expect(selection).toEqual(new Set(["file-2"]));
  });

  // flattenVisibleTree

  test("flattenVisibleTree returns only roots when nothing is expanded", () => {
    const nodes = [
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folder/", parent: "root/", text: "folder/" },
      { id: "file-1", parent: "root/folder/", text: "a.csv" },
      { id: "file-2", parent: "root/folder/", text: "b.csv" },
    ];
    const tree = buildTreeFromFlat(nodes);
    const flat = flattenVisibleTree(tree, new Set());

    expect(flat.map((f) => f.node.id)).toEqual(["root/"]);
    expect(flat[0].depth).toBe(0);
  });

  test("flattenVisibleTree includes children of expanded folders at correct depths", () => {
    const nodes = [
      { id: "root/", parent: "#", text: "root/" },
      { id: "root/folder/", parent: "root/", text: "folder/" },
      { id: "file-1", parent: "root/folder/", text: "a.csv" },
    ];
    const tree = buildTreeFromFlat(nodes);
    const flat = flattenVisibleTree(tree, new Set(["root/", "root/folder/"]));

    expect(flat.map((f) => f.node.id)).toEqual([
      "root/",
      "root/folder/",
      "file-1",
    ]);
    expect(flat[0].depth).toBe(0);
    expect(flat[1].depth).toBe(1);
    expect(flat[2].depth).toBe(2);
  });

  test("flattenVisibleTree with deeply nested expansion", () => {
    const nodes = [
      { id: "a/", parent: "#", text: "a/" },
      { id: "a/b/", parent: "a/", text: "b/" },
      { id: "a/b/c/", parent: "a/b/", text: "c/" },
      { id: "file-x", parent: "a/b/c/", text: "x.csv" },
    ];
    const tree = buildTreeFromFlat(nodes);
    // expand only a/
    const flat1 = flattenVisibleTree(tree, new Set(["a/"]));
    expect(flat1.map((f) => f.node.id)).toEqual(["a/", "a/b/"]);

    // expand the full path to the file
    const flat2 = flattenVisibleTree(tree, new Set(["a/", "a/b/", "a/b/c/"]));
    expect(flat2.map((f) => f.node.id)).toEqual([
      "a/",
      "a/b/",
      "a/b/c/",
      "file-x",
    ]);
    expect(flat2[3].depth).toBe(3);
  });

});

describe("selection under a path filter", () => {
  // bucket root (1) -> study/ (2) -> sub-a/ (3): a.json, a.nii
  //                               -> sub-b/ (4): b.csv
  //                 -> other/ (5): c.json
  const nodes = [
    { id: "1", parent: "#", text: "inn-application", li_attr: { bucket: "b", full_path: "/" } },
    { id: "2", parent: "1", text: "study/", li_attr: { bucket: "b", full_path: "/study/" } },
    { id: "3", parent: "2", text: "sub-a/", li_attr: { bucket: "b", full_path: "/study/sub-a/" } },
    { id: "4", parent: "2", text: "sub-b/", li_attr: { bucket: "b", full_path: "/study/sub-b/" } },
    { id: "5", parent: "1", text: "other/", li_attr: { bucket: "b", full_path: "/other/" } },
    { id: "file-10", parent: "3", text: "a.json", li_attr: { key: "study/sub-a/a.json" } },
    { id: "file-11", parent: "3", text: "a.nii", li_attr: { key: "study/sub-a/a.nii" } },
    { id: "file-12", parent: "4", text: "b.csv", li_attr: { key: "study/sub-b/b.csv" } },
    { id: "file-13", parent: "5", text: "c.json", li_attr: { key: "other/c.json" } },
  ];

  const filteredTree = (pattern) => {
    const pathMatcher = createPathMatcher(pattern, SEARCH_MODES.GLOB);
    const visible = filterNodes(nodes, { pathMatcher, selected: new Set(), selectedOnly: false });
    const isMatch = (node) => pathMatcher.test(getSearchablePath(node));
    return { tree: buildTreeFromFlat(visible), isMatch };
  };
  const find = (roots, id) => {
    for (const node of roots) {
      if (node.id === id) return node;
      const hit = find(node.children || [], id);
      if (hit) return hit;
    }
    return null;
  };

  // Tester's report: filter *.json, click the folder, download -> whole bucket.
  test("clicking a folder that only contains matches selects just the matching files", () => {
    const { tree, isMatch } = filteredTree("*.json");
    const ids = collectFilteredSelection(find(tree, "3"), isMatch);

    expect(ids).toEqual(["file-10"]);
    expect(getSelectedDownloadIds(new Set(ids))).toEqual({ fileIds: [10], folderIds: [] });
  });

  // Delete case: previously the selection spread to study/ and deleted all of it.
  test("delete under a filter targets only the matching files", () => {
    const { tree, isMatch } = filteredTree("*.json");
    const ids = collectFilteredSelection(find(tree, "3"), isMatch);

    expect(getSelectTopLevel(nodes, new Set(ids), true)).toEqual(["file-10"]);
  });

  test("selection never spreads to parent folders", () => {
    const { tree, isMatch } = filteredTree("*.json");
    const ids = collectFilteredSelection(find(tree, "1"), isMatch);

    expect(ids.sort()).toEqual(["file-10", "file-13"]);
    expect(ids).not.toContain("1");
    expect(ids).not.toContain("2");
  });

  test("a folder whose own name matches the filter is selected whole", () => {
    const { tree, isMatch } = filteredTree("sub-a");
    const ids = collectFilteredSelection(find(tree, "3"), isMatch);

    expect(ids.sort()).toEqual(["3", "file-10", "file-11"]);
    expect(getSelectTopLevel(nodes, new Set(ids), true)).toEqual(["3"]);
  });
});
