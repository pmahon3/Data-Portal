import { describeCheck } from "./describeCheck.js";

// DS-check-access (AC-1, AC-3): the answer reads as one sentence plus the policies responsible.

test("an allowed answer names each policy that allows it", () => {
  const answer = {
    allowed: true,
    shown: null,
    because: [{ resource: "study/*", action: "read", excluded: ["study/sub-03/*"] }],
  };
  expect(describeCheck(answer, "alice", "read", "study/a.nii")).toEqual({
    sentence: "Yes: alice can read study/a.nii, because of:",
    reasons: ["everything in study/ except study/sub-03/, including files added later (read)"],
  });
});

test("a refusal says no policy allows it, and nothing else", () => {
  const answer = { allowed: false, shown: null, because: [] };
  expect(describeCheck(answer, "alice", "write", "other/x.txt")).toEqual({
    sentence: "No: none of alice's policies lets them write to other/x.txt.",
    reasons: [],
  });
});

test("a folder shown but not allowed says why it still appears", () => {
  const answer = { allowed: false, shown: true, because: [] };
  expect(describeCheck(answer, "alice", "read", "study/").sentence).toBe(
    "No: none of alice's policies lets them read study/. " +
      "The folder still appears in their tree, because they hold something inside it.",
  );
});
