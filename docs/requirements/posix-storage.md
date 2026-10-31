# POSIX storage requirements

Testable requirements for working with files held on connected POSIX machines through the portal.
Each one serves part of the INN Digital Infrastructure Strategy (2026). The access rules themselves
are in [access-control.md](access-control.md) and apply here unchanged; this register holds only
what is specific to POSIX machines.

Open items name the question that settles them in *INN use cases: decisions* (27 October 2026):
A1 to A3 in Part A, D1 to D9 in Part D.

**Status:** *settled* (agreed; tests required), *proposed* (awaiting a functional decision),
*open* (needed by the strategy, not yet decided; no tests yet).

| ID | Requirement | Serves (strategy) | Status |
|------|----------------------------------------------|-------------------------|--------|
| <a id="px-1"></a>PX-1 | Through the portal, a user can browse, download and upload files held on a connected POSIX machine. | 4.1 steps 2–4 | settled |
| <a id="px-2"></a>PX-2 | Through the portal, a user can delete files held on a connected POSIX machine. | 4.1 | proposed |
| <a id="px-3"></a>PX-3 | A request gets the same answer on a POSIX machine as on object storage: the same access rules, refusals and listings. | 4.1; 5.1 postcondition | settled |
| <a id="px-4"></a>PX-4 | Identifiable data considered so far is held on the INN and ImageTech machines and scrubbed there; only scrubbed data leaves them. What the portal must do to support this: D3. | 5.1; 4.7 | open |
| <a id="px-5"></a>PX-5 | An interrupted download resumes rather than restarts. | 5.8 main flow step 3; 4.1 outcome (large files) | proposed |
| <a id="px-6"></a>PX-6 | An upload is either complete or absent: a failed upload never leaves part of a file, and never replaces an existing file. | 5.1 postcondition | proposed |
| <a id="px-7"></a>PX-7 | File contents move directly between the user and the machine, not through the portal's servers. | 5.8 main flow step 2 | proposed |
| <a id="px-8"></a>PX-8 | It works on a machine where INN has no administrator access. Where INN has it, it is used only where another requirement needs it. | decisions Part A (the setup balance) | proposed |
| <a id="px-9"></a>PX-9 | Who decides who else can open the governed files on each machine is as A1 decides. | 5.1 postcondition | open |
| <a id="px-10"></a>PX-10 | Activity on POSIX data is recorded as A2 decides (access through the portal is also covered by [AC-9](access-control.md#ac-9)). | 4.1 outcome (transparent logging); 5.1 non-functional requirements | open |
| <a id="px-11"></a>PX-11 | Files created, changed or deleted directly on a machine appear in the portal within the time A3 sets. | 4.1 step 2 | open |
| <a id="px-12"></a>PX-12 | Identifiable data moves between the INN and ImageTech machines as D1 decides. | 5.1; 4.7 | open |
| <a id="px-13"></a>PX-13 | A user can download several files at once as one archive, and an interrupted download resumes rather than restarts. | 4.1 steps 3–4; 5.8 main flow step 3 | proposed |
| <a id="px-14"></a>PX-14 | Downloading several files leaves no copy of them anywhere but the machine: nothing is built ahead or kept afterwards. | 5.1 postcondition; 4.7 (as [PX-4](#px-4)) | proposed |
| <a id="px-15"></a>PX-15 | An upload of a study-sized file (100 GB or more) completes through the portal, however long it takes. | 4.1 outcome (large files) | open |

[PX-1](#px-1) and [PX-3](#px-3) come from the decisions document's settled list. [PX-4](#px-4)'s scope is settled there too,
but what the portal must do about it waits on D3, so it has no tests yet. [PX-8](#px-8) states the aim of the
setup balance in Part A and awaits that decision. [PX-15](#px-15) records a known gap: today an upload must
finish within its link's lifetime (15 minutes). The answers to A1 to A3 decide which requirements need
administrator access.
