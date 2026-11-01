# Writing the user guide

How to write pages in `docs/user-guide/`, which is published as the
[wiki](https://github.com/pmahon3/Data-Portal/wiki) for researchers and administrators. Developer
documentation goes elsewhere in `docs/`.

## Page types

- **Task pages** (most pages): one thing a person does, such as uploading a folder or giving
  someone access.
- **Reference pages**: what something means or allows, looked up rather than followed, such as
  [How access works](user-guide/how-access-works.md).

Add a page to the right group in `docs/user-guide/README.md`, which is the wiki's Home page and
sidebar.

## Task page template

```markdown
# Doing the thing                      (what the reader does, in their words)

One or two sentences: what this is for.

## Before you start                    (the access or role it needs)

## Steps
1. One action per step, saying where before what: "Open **Upload**, then tick one folder."

## Result                              (what they see when it worked)

## If something goes wrong             (the messages they'll actually see, quoted, and what to do)

## Related                             (two or three links)
```

Extra sections, such as a table of cases, go between **Result** and **If something goes wrong**.

## Style

- Write for the reader's task, not the system's parts. Say "you".
- Short sentences (under about 25 words) and short paragraphs. Put the point first.
- Name interface labels exactly as they appear, in bold: **Upload Folder**, not "the upload folder
  button". Quote messages exactly.
- No "please", no "simply", no "just".
- Every image has alt text saying what it shows. Images come from `docs/images/capture.py`, which
  retakes them from the local stack with made-up data; never use screenshots of real data.
- Text carries the instructions; images confirm what the reader should see.

## Claims, tests and review

Each section that states how the portal behaves carries a marker naming the requirements and the
tests that show it, for example
`<!-- claim: AC-4; tests: test_a_folder_download_holds_only_files_the_user_may_read -->`.
Write the claim from those tests and the code, not from memory. A section with no test is reviewed
by a person instead. Every page is read by a person before it's published, and the wiki shows the
date of its last review.
