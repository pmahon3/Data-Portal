import { describeRule, verbFor } from "./treeRules.js";

/**
 * Return the answer in words: a first sentence, and the policies that allow it.
 * Example: allowed -> "Yes: alice can read study/a.nii, because of:" with ["everything in study/, ..."]
 */
export function describeCheck(answer, username, action, path) {
  const who = username || "This person";
  if (answer.allowed) {
    const reasons = answer.because.map(
      (policy) => `${describeRule({ resource: policy.resource, excluded: policy.excluded || [] })} (${policy.action})`,
    );
    return { sentence: `Yes: ${who} can ${verbFor(action)} ${path}, because of:`, reasons };
  }
  let sentence = `No: none of ${who}'s policies lets them ${verbFor(action)} ${path}.`;
  if (answer.shown) {
    sentence += " The folder still appears in their tree, because they hold something inside it.";
  }
  return { sentence, reasons: [] };
}
