# Policy conditions: exclusions, file types, end dates (design, reviewed: false)

2026-11-01. Implements AC-10 (C5), AC-6 (C4) and AC-8 (C6), settled by Patrick on 2026-11-01.
Registry: `DS-policy-conditions` and the nodes under it.

## The seam

Every access decision already goes through one place: `Checker` in
`backend/core/services/policies/rules.py`. Casbin only stores policies; its matcher isn't used for
decisions (`validate_policy` and every endpoint go through `checker()`). So the three features are
one change: **a policy gains an optional `conditions` field, and only `rules.py` reads it.**

- Storage: the Casbin policy definition gets a fifth field, `p = sub, dom, obj, act, cond`, holding
  a small JSON object (empty for every existing policy). The matcher is left as it is and ignores
  `cond`; a comment says so, and a test checks that no endpoint calls `enforcer.enforce`.
- `Rule(path, action, conditions)`; `rule_allows` and `rule_shows_folder` apply the conditions.
- `Checker` indexes every policy by the folder it covers, with or without conditions; a conditioned
  policy is checked only for paths inside its folder (see Scale).
- The policy API and form gain the three optional fields; `normalize_rule_path` rules apply to
  every path in them.

```json
{"except": ["study/sub-03/"], "endings": [".nii", ".nii.gz"], "kinds": ["anat"], "ends": "2027-06-30"}
```

## Exclusions (AC-10)

**An exclusion belongs to one folder policy:** `study/*` except `study/sub-03/*` covers everything in
`study/` but not `sub-03/` or anything in it, now or later. It removes nothing that *another* policy
gives, so policies still only add up; the guide's "How policies add up" stays true, with one added
sentence. Excluded paths are written like policy paths: a file, or a folder ending in `/*`, inside
the policy's folder. An excluded folder isn't shown in the tree unless another policy shows it.

Rejected: a separate "deny" policy that overrides others. It's what makes Windows and AWS
permissions hard to read (the research behind *How access works*), and it makes access depend on
every policy at once instead of each on its own.

## File types (AC-6)

- **By name ending:** a folder policy with `endings` covers only files in that folder whose names
  end with one of them (case-insensitive; `.nii.gz` works). Folders on the way to such files are
  shown; other files aren't.
- **By kind of data:** `kinds` names kinds as the dataset's standard defines them (for BIDS, the
  datatype: `anat`, `func`, `dwi`, ...). *Revised 2026-11-01 (agent):* no stored classification. Each
  standard's plugin names a file's kind from its path inside the dataset (BIDS: the folder after
  `sub-*/` or `sub-*/ses-*/`, so sidecars count with their scans). A policy with kinds records its
  dataset's root and standard when saved; saving requires the policy's folder to be inside a dataset
  that declares a standard, and each kind to be one that standard defines. Decisions classify by path,
  so nothing runs at upload or sync, and it follows access by name. A file the standard doesn't
  classify (`dataset_description.json`, `participants.tsv`) has no kind, so a `kinds` policy doesn't
  cover it. Robust to STD-WHICH: a second standard brings its own kinds.
- Both together: a file must match both.

## End dates (AC-8)

- `ends` is a date. From that date the policy allows nothing: the `Checker` skips it, so access ends
  without a scheduled job and nothing is deleted (the table shows it as **Ended**).
- Policies with no `ends` never end (open datasets, C6).
- **Reminders:** a daily job notifies the instance's administrators and the managers of its projects,
  through the existing notification channels, `POLICY_END_REMINDER_DAYS` (default 14) before a policy
  ends, and again on the day.
- Download links already handed out still run to their expiry (up to 15 minutes), as when a policy
  is removed.

## Scale (AC-11)

*Added 2026-11-02 (agent).* The first build assumed conditioned policies would be rare and checked
them one by one against every path. They aren't rare: the tree picker makes one whenever a ticked
folder has something unticked. Measured in the backend container (amd64 under emulation), a user
with 200 such policies took about 30 s to decide a 100,000-file folder, and 20 policies on one folder
about 50 s, against AC-11's 1 s.

Now:

- **Per path:** conditioned policies are looked up by the folders the path is in (as plain folder
  policies are), so the cost is one lookup per folder level plus the policies on those folders.
  Exclusions are set lookups over the same folders. A folder's policies are skipped together when a
  file matches none of their endings.
- **Measured (`test_access_scaling.py`, in the gate):** 100,000 files in 0.27 s with 2,200 policies
  (200 conditioned), or 20 conditioned policies on one folder; a 10,000-entry listing in 0.03 s.
- **What still grows:** many policies on the *same* folder that differ only in exclusions or kinds
  are each checked for that folder's files; kinds call the standard's `kind_of` once per policy.
  Bounded by policies per folder per user, which the picker keeps to one.
- **Storage:** conditions add a short JSON string per policy; nothing is stored per file. End
  reminders read the policies with end dates once an hour.

## Choices made here (reversible, testable)

- Conditions in one JSON field rather than one column each: one migration, one seam.
- End dates enforced when deciding, not by deleting policies.
- Reminders 14 days ahead, to administrators and project managers, by a setting.
- Endings case-insensitive.

## Decided by Patrick (2026-11-01)

1. Exclusions belong to one folder policy, not a separate deny rule.
2. The tree picker turns "tick a folder, then untick something inside it" into one policy with an
   exclusion, covering files added later. Ticking files on their own still gives one policy per file.
   This refines the picker's mapping ([use-case instances](use-case-instances.md), `DS-policy-from-selection`).

## Order of work

One lane (all change `rules.py`): conditions seam and end dates first (smallest, no new data), then
exclusions, then endings, then kinds (needs the classifier column). Each lands test-first: the
checked table in *How access works* gains rows for each, which needs the multi-column parse noted
in the research report (T1), and the guide gets its sections in the same branch.
