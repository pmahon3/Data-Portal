# Policy preview: what a policy will allow, before it's saved (design, reviewed: false)

2026-11-03 (agent; reversible). Registry: `DS-broad-grant-warning`, `DS-grant-extent-preview` (parent
AC-5). From [Explaining access rules to users](explaining-access-rules.md): show the
extent of a change before it's made, and state the outcome in plain words, not the rule.

## What it does

On the policy form, before **Create Policy**:

1. **Broad-grant warning** (`DS-broad-grant-warning`). When a policy covers the whole instance (`*`)
   or a whole bucket (`bucket/*`), the form says so in one sentence: "This covers the whole bucket
   study, including files added later." It shows for a typed path and for a bucket ticked in the
   tree. It warns; it doesn't block (giving a whole bucket is sometimes right).
2. **Plain-words preview for a typed path** (first half of `DS-grant-extent-preview`). The sentence
   the tree picker already shows ("alice can read: everything in study/ except study/sub-03/,
   including files added later"), with the typed path's conditions: endings, kinds of data, end date.
3. **Not yet: a file count** ("1,240 files today", the other half). It needs a read of the file tree
   per preview; brought to Patrick before building (see Scale).

## The seam

Pure functions in `treeRules.js` beside `describeRule`: `broadExtent(resource)` returns the warning
or nothing; the typed preview reuses `describeRule` and `describeWho`, so the picker and the typed
path say the same thing in the same words. Nothing is stored and the backend is unchanged.

"Broad" is the instance or a bucket: the two levels every instance has. A folder high inside a
bucket isn't flagged: the form can't tell a study's top folder from a small one without the count.

## Scale

No reads and no storage: a string check per rule as the form changes; the tree picker's rules are
already in memory. A file count would be one indexed count under a prefix in PostgreSQL, but
exclusions, endings and kinds need each key checked (`Checker`): a 100,000-file bucket means
fetching and checking 100,000 keys per preview (about 0.3 s, by `test_access_scaling.py`), so it
would need debouncing, a cap ("over 10,000 files") and its own timing test.
