# Deleting files

Open the storage instance's card and choose the **Delete** tab. It shows only what you may delete.

1. Tick the files or folders to delete. Ticking a folder ticks everything in it.
2. Choose **Delete**. The portal asks you to confirm how many folders and files will go.
   Deleting can't be undone.

## What a delete removes
<!-- claim: AC-2, AC-4; tests: test_a_user_can_delete_a_file_they_hold, test_a_user_cannot_delete_a_file_they_do_not_hold, test_deleting_a_folder_never_removes_a_file_the_user_could_not_delete, test_a_file_grant_does_not_allow_deleting_the_folder_above -->

Only what you ticked, and only what you may delete. Deleting a folder never removes a file in it
that you couldn't delete yourself. Permission to delete a file doesn't let you delete the folder
it's in.

A bucket at the top of the tree can't be deleted from here.
