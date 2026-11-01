# Finding and downloading files

Download a file, a folder, or a selection of files from a storage instance.

## Before you start

You need `read` access to the files. **My Policies** lists what you have; if something is missing,
ask your administrator or project manager.

## Steps

1. Open **My Assets** (administrators: **Asset Management**), then open the storage instance's card.
2. Choose the **Download** tab.
3. Find the files: open folders with the arrow beside them, or [search](#searching).
4. Tick the files or folders you want. Ticking a folder ticks everything in it.
5. Choose **Download**.

## Result

- **One file** downloads straight away.
- **Several files or a folder** become one ZIP file. The button shows "Preparing download…" with a
  timer while it's made, then your browser downloads it. Large selections take a while.

## Searching

Type a pattern in the filter box and press Enter. `*` matches any characters and `?` one, so
`*.nii.gz` finds every compressed scan. The **(.\*)** button switches to regular expressions, and
the list button shows only what you've already ticked. Starting or clearing a search clears what
you've ticked.

## What a download holds
<!-- claim: AC-4; tests: Selecting the only visible file in a folder doesn't select the folder, A folder whose own name matches the filter is selected whole, test_a_download_refuses_a_selected_file_the_user_may_not_read, test_a_folder_download_holds_only_files_the_user_may_read -->

While a search is on, ticking a folder ticks only the files the search shows, so you download what
you see. A folder whose own name matches the search shows, and ticks, everything in it.

![Searching for *T1w.nii.gz and ticking sub-01 ticks only the scan the search shows](../images/asset-filtered-selection.png)

A download holds only files you may read. A ticked folder downloads only the files in it you may
read.

## If something goes wrong
<!-- claim: AC-3; tests: test_the_user_who_asked_for_a_bundle_can_fetch_it, test_another_users_bundle_cant_be_checked_or_fetched, test_a_bundle_is_refused_once_access_to_a_file_in_it_is_revoked -->

- **"Download failed"** after preparing: if your access to a file in the ZIP was removed before you
  fetched it, the download is refused. Ask whoever manages your access.
- A ZIP can be fetched only by the person who asked for it, so a download link can't be passed on.

## Related

- [Uploading files and folders](uploading.md)
- [How access works](how-access-works.md)
