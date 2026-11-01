# Uploading files and folders

Upload files, or a whole folder from your computer, into a folder on a storage instance.

## Before you start

You need `write` access to the folder you're uploading into. The **Upload** tab shows only the
folders you may upload into.

## Steps

1. Open **My Assets** (administrators: **Asset Management**), then open the storage instance's card.
2. Choose the **Upload** tab.
3. Tick **one** folder: that's where the upload goes.
4. Choose **Upload File** to pick one or more files, or **Upload Folder** to pick a folder from your
   computer. A folder keeps its subfolders.

![The Upload tab: sub-03 ticked as the destination, with Upload File and Upload Folder](../images/researcher-upload.png)

## Result

A bar shows how many files are done. When it finishes the portal says so, and you get a
[notification](notifications.md). Your files go straight from your browser to storage; the portal
checks and records them. System files such as `.DS_Store` are skipped when you upload a folder.

## If something goes wrong
<!-- claim: AC-2, AC-3; tests: test_uploading_a_file_never_replaces_an_existing_one, test_a_user_cannot_upload_into_a_folder_they_hold_nothing_in, test_a_file_grant_does_not_allow_replacing_other_files_by_folder_upload, test_a_file_grant_does_not_allow_creating_folders_above_it -->

- **"A file with the same name already exists in this folder"**: uploads never replace files. The
  upload stops and nothing in that folder changes. Rename your file, or ask someone who may delete
  the old one.
<!-- vale Portal.Filler = NO -->
- **"Please select exactly ONE folder to upload to"**: untick all but one folder.
<!-- vale Portal.Filler = YES -->
- **The upload is refused**: every file is checked before anything is stored, and if any one of
  them is refused, nothing is uploaded. Check **My Policies** for `write` access there.

## Related

- [Notifications](notifications.md)
- [Deleting files](deleting.md)
