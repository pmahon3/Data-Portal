# Access-control requirements

Testable requirements for who can see and act on data in the portal. Each one serves part of
the INN Digital Infrastructure Strategy (2026), which sets the outcomes but not these rules.
They apply wherever the portal manages storage, including connected POSIX machines.

Each test names the entry it checks: a Gherkin tag in a feature file (`@AC-4 @UC-5.1`), or, in
pytest, the ID at the start of the test's docstring (`AC-3.`) or a `Verifies:` line in the module's
docstring. Ticket tags and markers such as `@INN-295` record where a regression was found; they are
not the reason a test exists.

Open and proposed entries name the question that settles them in *INN use cases: decisions*
(27 October 2026).

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet designed; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|----|----------------------------------------------|-------------------------|--------|
| <a id="ac-1"></a>AC-1 | A user sees only the folders on the path to what they hold, and nothing else in those folders. This is decided per action: when browsing to read, write or delete, a folder appears if the user holds that action on it or on something inside it, so write-only and delete-only permissions stay usable. Seeing a folder doesn't allow acting on it. This applies to the screen and to the API. | 5.1 postcondition ("accessible only to authorized users"); value Integrity and Ethics | settled |
| <a id="ac-2"></a>AC-2 | Access to one item never lets a user delete or overwrite any other item. | 5.1 postcondition | settled |
| <a id="ac-3"></a>AC-3 | The backend refuses every request the user isn't authorized for, whatever the client sends. | 5.1 postcondition; 4.1 | settled |
| <a id="ac-4"></a>AC-4 | A bulk action (download, delete) acts only on the items the user selected. While a filter is active, selecting a folder selects only the files in it that the filter shows; a folder whose own path matches the filter shows everything in it, and is selected whole. Decided by C3. | 5.1 postcondition | settled |
| <a id="ac-5"></a>AC-5 | A permission names a single file, or a folder and everything in it, including files added to it later. Its path is literal: no character in it is a pattern. Access is by name: renaming or moving a file ends access to it, and a new file at the same path inherits it. Decided by B1. | 4.1; 2.4 (tiered access) | settled |
| <a id="ac-6"></a>AC-6 | Permissions can be limited by type of file: by file name ending (for example `.nii`) within a folder, and by kind of data (for example 'anatomical scan') from its description (C4). | 2.4 (tiered access) | settled |
| <a id="ac-7"></a>AC-7 | When a participant withdraws, new access to their data is blocked, and what is removed is what their consent or agreement requires: their original data, data derived from it, log entries that identify them, in any combination (D8). | 5.7 main flow step 4; 4.7 | open |
| <a id="ac-8"></a>AC-8 | Access can be given with an end date and then ends automatically; administrators are reminded before it does. Access with no end date, such as to an open dataset, is allowed (C6). | 5.8 main flow step 1; 2.4 (agreement-aware sharing) | settled |
| <a id="ac-9"></a>AC-9 | Every access is logged and attributable to a user. Administrators, and data owners for their own data, can read the records, and any change to them can be detected (C2). Records name files and people as they are; coding participant IDs in file names is the study team's responsibility (D7). | 5.1 non-functional requirements; value Integrity and Ethics | open |
| <a id="ac-10"></a>AC-10 | A permission on a folder can exclude named files or folders inside it (C5). | 2.4 (tiered access) | settled |
| <a id="ac-11"></a>AC-11 | Access decisions stay fast as data and permissions grow, including permissions with conditions ([AC-6](#ac-6), [AC-8](#ac-8), [AC-10](#ac-10)). For a user holding thousands of permissions: one check under 1 ms, a 10,000-entry folder listing under 200 ms, and a 100,000-file folder (a download or a delete) decided in under 1 s, not counting reading the listing from storage. Targets proposed to RDT; not yet adopted. | 5.4 non-functional requirements ("scalability to handle large external datasets"); 5.8 | proposed |
| <a id="ac-12"></a>AC-12 | Access follows research relationships: a person's access to a project's data comes from their membership, within terms set by those accountable (agreements, consent, end dates), and ends when the membership does. Access given to one person directly is shown as an exception, and those allowed can see who has access through which relationship (REL-MEMBERSHIP-ACCESS). | 7.1 (Proposal A, for discussion) | open |

[AC-4](#ac-4) and [AC-5](#ac-5) were decided on 31 October 2026 by Patrick, from concrete cases in INN's studies (a study folder gaining sessions, a participant folder under a DAA, picked files, renames, replaced files, a filtered selection). [AC-4](#ac-4)'s filter rule was decided the same day (C3): a selection holds what the filter
shows, so a download or delete never acts on files the filter hid. [AC-6](#ac-6) to [AC-10](#ac-10) were decided
on 1 November 2026 by Patrick (C2, C4, C5, C6, D7, D8). They stay open until each is designed and has tests; [AC-6](#ac-6), [AC-8](#ac-8) and [AC-10](#ac-10) are built. [AC-11](#ac-11) was added on 2 November 2026, when conditioned permissions were measured
at about 30 s for a 100,000-file folder; its targets are the ones proposed in the authorization plan, awaiting RDT.
