# Use-case instances behind the permission model

Concrete cases Patrick gave on 2026-10-31, from how INN's studies actually work. They settle B1 (and
R-RENAME) without a general question to leadership. Each answer is what should happen.

| # | Case | Answer |
|---|---|---|
| 1 | A researcher is given a study folder; the technician adds next week's session to it. | They see it, with no new grant. |
| 2 | Access to one participant's folder (`patient-7/`); a new file appears there. | They see it. For identifiable data: a signed DAA covering a study participant includes later additions to that participant's folder, since it sits in the study's folder. The same participant in another study needs a new DAA. |
| 3 | An admin picks three files out of fifty in a folder for a collaborator. | New files in that folder stay hidden from them. A file grant shows the path to the file (its folders, when browsing) but no other files in those folders, and no rights on the folders themselves (AC-1, AC-2; tested). |
| 4 | A file someone can read is renamed or moved (e.g. during curation). | Their access stops. Carrying it over could later be offered as a prompt on move or rename. |
| 5 | A participant's files are removed, then replaced with corrected ones of the same name. | The old grants apply to the replacements. |
| 6 | An admin filters to `*.nii`, ticks the folder and grants it. | The scans only: the files the filter shows. |

## What follows

- **A folder grant covers files added later** (1, 2): `folder/*`.
- **Selected files are only those files** (3): a file selection is never turned into a folder grant.
- **Access is by name** (4, 5): a grant names a path; renaming or moving ends access; a new file at the
  same path inherits it. A prompt to carry access over on a move can come later (deferred).
- **A selection under a filter holds what the filter shows** (6, as AC-4): grants go on those files.

## Choosing from the file tree (built; exclusions added 2026-11-01)

Granting by picking items from the tree follows the same rules, with no conversion beyond them:

| Selected | Grant |
|---|---|
| A folder, no filter | `folder/*` |
| Files | One grant per file; never collapsed into a folder |
| A folder under a filter | One grant per file the filter shows |
| A ticked folder with things unticked inside it | One grant on the folder, leaving out what's unticked (AC-10, Patrick 2026-11-01) |

Before saving, the admin sees the rules in plain words ("Alice can read everything in
`study/patient-7/`, including files added later. 3 rules.") and approves them. Grants go through the
policy API, so the picker can't make a rule that typing couldn't.
