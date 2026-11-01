# How access works

What a policy gives, exactly. For the steps to give someone access, see
[Giving people access](policies.md).

## A policy has four parts

| Part | What it is | Example |
|---|---|---|
| Person | Who gets the access | `alice` |
| Instance | Which storage it applies to | `inn-storage` |
| Path | What it covers, starting with the bucket | `study-a/patient-7/*` |
| Action | What they may do | `read` |

A person's access is everything their policies give, added together. There are no "deny" policies:
to take access away, remove the policy that gives it.

## The path
<!-- claim: AC-1, AC-5; tests: test_a_file_grant_does_not_cover_longer_names, test_a_folder_grant_does_not_cover_folders_sharing_its_name, test_a_dot_in_a_grant_is_just_a_dot, test_a_grant_on_a_file_named_with_a_bracket_gives_access_to_it, test_a_folder_holding_a_file_named_with_a_bracket_can_be_browsed -->

A path names exactly one of three things. It is read literally: no character in it is a pattern.

| Path | Covers |
|---|---|
| `study-a/patient-7/scan.nii` | That one file. Not `scan.nii.bak`, not anything else in the folder. |
| `study-a/patient-7/*` | That folder and everything in it, at any depth, **including files and folders added later**. Not `patient-70/`. |
| `*` | Everything on the instance, including what's added later. |

## The action
<!-- claim: AC-2, AC-3, AC-5; tests: test_a_user_can_read_a_file_they_hold, test_a_user_can_delete_a_file_they_hold, test_a_folder_grant_allows_uploading_into_and_deleting_the_folder, test_a_file_grant_does_not_allow_creating_longer_names, test_a_new_instance_grants_its_creator_a_rule_the_portal_accepts -->

| Action | With a file path, the person can | With a folder path (`folder/*`), the person can |
|---|---|---|
| `read` | Download that file, alone or in a ZIP with other files they can read | Browse the folder and download anything in it |
| `write` | Upload a file with that exact name where none exists | Upload files and create folders inside it; a folder upload may replace files there |
| `delete` | Delete that file | Delete anything in it, and the folder itself |
| `*` | All of the above | All of the above |

The `admin` action is given to whoever creates an instance. It has no effect on files: file
access always comes from `read`, `write` and `delete`.

## What the person sees
<!-- claim: AC-1, AC-2; tests: test_listings_above_a_file_show_only_the_path_to_it, test_a_folder_listing_shows_only_files_the_user_may_read, test_a_listing_for_an_action_shows_what_the_user_may_do_it_to, test_a_file_grant_does_not_allow_deleting_the_folder_above -->

When browsing, a person sees what they can act on, and the folders on the way to it, nothing else.
With `read` on `study-a/patient-7/scan.nii` alone, they see `study-a/`, then `patient-7/` inside
it, then `scan.nii`, and no other file or folder at any of those levels. Seeing a folder on the way
gives no access to it: they can't download, upload into or delete it.

The file tree is shown per action: browsing to upload shows what they may write, browsing to delete
shows what they may delete.

## Does this policy allow it?

Each row is one policy and one question about it: may the person `read`, `write` or `delete` the
path, or is a folder `shown in tree`? A folder is shown when it lies on the way to something the
person holds; only its name appears. That gives no access to the folder, and its other contents stay
hidden. "Refused" means the portal won't save the policy.

<!-- check: policy-examples (run by backend/tests/test_policy_guide.py) -->
| Policy path | Action | Asked | About | Answer |
|---|---|---|---|---|
| `study-a/patient-7/scan.nii` | read | read | `study-a/patient-7/scan.nii` | yes |
| `study-a/patient-7/scan.nii` | read | read | `study-a/patient-7/scan.nii.bak` | no |
| `study-a/patient-7/scan.nii` | read | read | `study-a/patient-7/notes.txt` | no |
| `study-a/patient-7/scan.nii` | read | shown in tree | `study-a/` | yes |
| `study-a/patient-7/scan.nii` | read | shown in tree | `study-a/patient-7/` | yes |
| `study-a/patient-7/scan.nii` | read | read | `study-a/patient-7/` | no |
| `study-a/patient-7/scan.nii` | read | shown in tree | `study-a/patient-8/` | no |
| `study-a/patient-7/scan.nii` | read | delete | `study-a/patient-7/scan.nii` | no |
| `study-a/patient-7/*` | read | read | `study-a/patient-7/session-2/new.nii` | yes |
| `study-a/patient-7/*` | read | read | `study-a/patient-70/scan.nii` | no |
| `study-a/incoming/*` | write | write | `study-a/incoming/s1.nii` | yes |
| `study-a/incoming/*` | write | read | `study-a/incoming/s1.nii` | no |
| `*` | * | delete | `study-b/any/file.txt` | yes |
| `/study-a/scan.nii` | read | read | `study-a/scan.nii` | yes |
| `study-a/sub-0[1-3]/*` | read | read | `study-a/sub-0[1-3]/scan.nii` | yes |
| `study-a/sub-0[1-3]/*` | read | read | `study-a/sub-02/scan.nii` | no |
| `.*` | read | | | refused |
| `study-a/.*` | read | | | refused |
| `study-a/sub-*/scan.nii` | read | | | refused |
| `study-a/patient-7/` | read | | | refused |

## Examples, read aloud
<!-- claim: AC-1, AC-5 -->

| Policy | Means |
|---|---|
| `alice`, `inn-storage`, `study-a/*`, `read` | Alice can browse and download everything in study A, including sessions added later. |
| `bob`, `inn-storage`, `study-a/patient-7/summary.csv`, `read` | Bob can download that one file. He sees the folders leading to it and nothing else in them. |
| `tech1`, `inn-storage`, `study-a/incoming/*`, `write` | The technician can upload into `incoming/`, but can't download or delete anything, there or elsewhere. |
| `carol`, `inn-storage`, `*`, `*` | Carol can do anything with any file on the instance. |

## Things that surprise people
<!-- claim: AC-2, AC-3, AC-4, AC-5; tests: test_uploading_a_file_never_replaces_an_existing_one, test_a_download_refuses_a_selected_file_the_user_may_not_read, test_a_folder_download_holds_only_files_the_user_may_read, test_another_users_bundle_cant_be_checked_or_fetched, test_a_bundle_is_refused_once_access_to_a_file_in_it_is_revoked, test_a_grant_written_with_a_leading_slash_gives_access -->

- **Paths aren't regular expressions.** `.*`, `study-a/.*` or a `*` in the middle of a path are
  refused, with a message giving the right form. Other characters mean themselves: `sub-0[1-3]/*`
  is a folder literally named `sub-0[1-3]`, not `sub-01` to `sub-03`. The file tree's search does
  accept regular expressions; policies don't.
- **A folder path needs the `/*`.** `study-a/patient-7/` without it is refused: write
  `study-a/patient-7/*`.
- **Access is by name.** A policy names a path, not a file. If a file is renamed or moved, policies on
  its old path no longer reach it. A new file put at the same path is covered by them.
- **Single-file uploads never replace an existing file.** Replacing goes through a folder upload
  that chooses to replace, and needs `write` on what it replaces.
- **A download of several files is all or nothing.** If any selected file can't be read, the whole
  download is refused. Selecting a folder downloads only the files in it the person can read.
- **A ZIP belongs to the person who asked for it.** Nobody else can fetch it. If their access to any
  file in it is removed before they download it, the download is refused.
- **A link already handed out runs until it expires.** Removing a policy stops new access at once,
  but a download link given before lasts up to 15 minutes.
- **A leading `/` is fine.** `/study-a/scan.nii` is saved as `study-a/scan.nii`.

## Not yet part of a policy
<!-- planned: AC-7, AC-8, STD-1 -->

These are planned but not decided, so no policy expresses them yet:
- access that expires with the agreement that grants it ([AC-8](../requirements/access-control.md#ac-8));
- blocking new access to a withdrawn participant's data ([AC-7](../requirements/access-control.md#ac-7));
- what quarantine holds back when data fails its standard's checks ([STD-1](../requirements/data-standards.md#std-1)).

## Where this comes from

Each statement here is a requirement in [access control](../requirements/access-control.md)
([AC-1](../requirements/access-control.md#ac-1) to [AC-5](../requirements/access-control.md#ac-5)), checked by `backend/tests/test_access_control.py` against the running portal.
How the portal decides is in `backend/core/services/policies/rules.py`.
