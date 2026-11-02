# POSIX storage requirements

Testable requirements for working with files held on connected POSIX machines through the portal.
Each one serves part of the INN Digital Infrastructure Strategy (2026). The access rules themselves
are in [access-control.md](access-control.md) and apply here unchanged; this register holds only
what is specific to POSIX machines. How each one is met, and which ones need administrator access on
a machine, is in the design ([docs/posix/README.md](../posix/README.md)).

Open items name the question that settles them in *INN use cases: decisions* (27 October 2026):
A1 to A3 in Part A, D1 to D9 in Part D.

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet decided; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|------|----------------------------------------------|-------------------------|--------|
| <a id="px-1"></a>PX-1 | Through the portal, a user can browse, download and upload files held on a connected POSIX machine. | 4.1 steps 2–4 | settled |
| <a id="px-2"></a>PX-2 | Through the portal, a user can delete files held on a connected POSIX machine. | 4.1 | settled |
| <a id="px-3"></a>PX-3 | A request gets the same answer on a POSIX machine as on object storage: the same access rules, refusals and listings. | 4.1; 5.1 postcondition | settled |
| <a id="px-4"></a>PX-4 | Identifiable data considered so far is held on the INN and ImageTech machines and scrubbed there. A file leaves a machine through the portal only if the conditions attached to it allow (D3). | 5.1; 4.7 | open |
| <a id="px-5"></a>PX-5 | An interrupted download resumes rather than restarts. | 5.8 main flow step 3; 4.1 outcome (large files) | settled |
| <a id="px-6"></a>PX-6 | A file appears at its path only when its upload is complete, and an upload never replaces an existing file. An interrupted upload resumes rather than restarts; until it finishes it is shown as incomplete, and one left unfinished is cleared after a set time. | 5.1 postcondition | settled |
| <a id="px-7"></a>PX-7 | File contents move directly between the user and the machine, not through the portal's servers. | 5.8 main flow step 2 | settled |
| <a id="px-8"></a>PX-8 | It works on a machine where INN has no administrator access. Where INN has it, it is used only where another requirement needs it. | decisions Part A (the setup balance) | proposed |
| <a id="px-9"></a>PX-9 | On each machine, its system administrators and project managers manage direct access to the governed files by hand (A1); the portal governs only access through itself. | 5.1 postcondition | proposed |
| <a id="px-10"></a>PX-10 | Activity on POSIX data is recorded for all data on the machines: access through the portal (as [AC-9](access-control.md#ac-9)), and who changes and who reads files directly on the machine (A2). | 4.1 outcome (transparent logging); 5.1 non-functional requirements | open |
| <a id="px-11"></a>PX-11 | Files created, changed or deleted directly on a machine appear in the portal within a few minutes, or when someone refreshes (A3). Until that is built, within a few hours or on refresh, with an email confirming each upload, is acceptable. | 4.1 step 2 | open |
| <a id="px-12"></a>PX-12 | Identifiable data can move between the INN and ImageTech machines three ways (D1): machine to machine, started through the portal; by staff outside the portal; and through the portal by download and upload. Each machine has a staging area and a pipeline-outputs area, with written rules for its administrators on which direct changes the portal handles and which carry no guarantees. | 5.1; 4.7 | open |
| <a id="px-13"></a>PX-13 | A user can download several files at once as one archive, and an interrupted download resumes rather than restarts. | 4.1 steps 3–4; 5.8 main flow step 3 | settled |
| <a id="px-14"></a>PX-14 | Downloading several files leaves no copy of them anywhere but the machine: nothing is built ahead or kept afterwards. | 5.1 postcondition; 4.7 (as [PX-4](#px-4)) | proposed |
| <a id="px-15"></a>PX-15 | An upload of a study-sized file (100 GB or more) completes through the portal, however long it takes. | 4.1 outcome (large files) | settled |

[PX-1](#px-1) and [PX-3](#px-3) come from the decisions document's settled list. Patrick settled the rest
on 1 November 2026, answering A2, A3, D1 and D3 and confirming [PX-2](#px-2), [PX-5](#px-5) to [PX-7](#px-7), [PX-13](#px-13) and [PX-15](#px-15)
([PX-6](#px-6) extended to resumable uploads). [PX-8](#px-8) states the aim of the setup balance in Part A.
[PX-15](#px-15) records a known gap: today an upload must finish within its link's lifetime (15 minutes).
