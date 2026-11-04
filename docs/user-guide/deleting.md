# Deleting files

Delete files or folders from a storage instance. Deleting can't be undone.

## Before you start

You need `delete` access to what you're deleting. The **Delete** tab shows only what you may delete.

## Steps

1. Open **My Assets** (administrators: **Asset Management**), then open the storage instance's card.
2. Choose the **Delete** tab.
3. Tick the files or folders to delete. Ticking a folder ticks everything in it.
4. Choose **Delete**, and confirm. The portal says how many folders and files will go.

## Result

The files are removed from storage and from the portal, and the tree refreshes.

## What a delete removes
<!-- claim: AC-2, AC-4; tests: test_a_user_can_delete_a_file_they_hold, test_a_user_cannot_delete_a_file_they_do_not_hold, test_deleting_a_folder_never_removes_a_file_the_user_could_not_delete, test_a_file_grant_does_not_allow_deleting_the_folder_above -->

Only what you ticked, and only what you may delete. Deleting a folder never removes a file in it
that you couldn't delete yourself. Permission to delete a file doesn't let you delete the folder
it's in. A bucket at the top of the tree can't be deleted from here.

## Related

- [Uploading files and folders](uploading.md)
- [How access works](how-access-works.md)
