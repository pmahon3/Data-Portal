# Notifications
<!-- claim: NT-1; tests: test_a_stored_upload_is_recorded_for_its_researcher, test_a_folder_upload_is_one_notification_with_its_counts, test_the_endpoint_lists_only_the_callers_own, test_newest_first_and_capped, test_an_email_tells_the_researcher_without_naming_files, test_an_email_says_when_files_failed, test_email_is_off_until_a_relay_is_set -->

When your upload is stored, the portal tells you. The bell at the top shows how many
notifications are new; open it to see them, newest first.

![The bell opened: each upload that was stored, newest first](../images/notifications.png)

- A file upload says "Stored" and the file's name.
- A folder upload is one notification with how many files were stored, and how many failed, if
  any did.
- You see only your own notifications, up to the newest 50. The bell checks for new ones every 30
  seconds.

If the portal has email set up, you're also sent an email. It never names your files, since file
names can identify participants; it says how many were stored and links to the portal.

## For administrators and project managers
<!-- claim: AC-8; tests: test_administrators_and_the_instances_project_managers_are_reminded, test_each_reminder_is_sent_once_however_often_the_job_runs, test_a_reminder_email_names_no_files -->

You're also told two weeks before a policy you manage ends, and on the day, so you can renew or let
it end. See [Giving people access](policies.md).

## Related

- [Uploading files and folders](uploading.md)
