# INN use cases: decisions

The questions as put on 27 October 2026 to Patrick Mahon and the INN Director of Operations. Some background has moved on since; the decision registry records each question's status and answer.

### Why these questions

To turn what INN needs into decisions specific enough to build and estimate. Part A comes first: it shapes the POSIX setup.

**A.** POSIX setup. **B.** One confirmation. **C.** The current portal. **D.** Other POSIX questions. **E.** Later, listed only.

### Already settled

> - **POSIX** means browsing, downloading and uploading files on POSIX machines through the portal, under its access rules. Compute through the portal is later (Part E).
> 
> - **This year's machines** are INN's and ImageTech's; the portal's service can use administrator access on them. More collaborators' machines are likely to follow (Part A).
> 
> - **Identifiable data** has so far been considered only on the INN and ImageTech machines, moving between them. It's scrubbed there by people the machine's administrator adds, and only scrubbed data leaves.
> 
> - **No sharing** between users in this release; administrators give all access.
> 
> - **Portal rules** apply in portal-managed storage, which includes connected POSIX machines.

<a id="priv-2"></a>Not covered here: a privacy impact assessment. POSIX would bring identifiable data into the portal for the first time, and the portal hasn't had one.

## Part A. POSIX setup

The questions that shape how POSIX machines are set up, and what that costs as more machines join.

> **The balance these questions set.** This year INN brings the INN and ImageTech machines online; more collaborators' machines are likely to follow, and their data may need to stay on them. The aim is the lowest total implementation cost across both.
> 
> Administrator access lets INN control a machine and lets the machine's own system enforce access and record who touched what, but each machine then needs administration, by INN or the collaborator. The portal can also enforce access itself, as it does for object storage: less administration per machine, more development, and less control over what happens on the machine. The service can use administrator access where it's available and needed.
> 
> Each question below notes how its answer moves that balance. The technical team is estimating both sides.

### <a id="a1"></a>A1. On each machine, who decides who else can open the governed files?

Whoever owns a file on a POSIX machine decides who else can open it, and answers for that access. Today that's the researchers who put the files there. The portal can work alongside them, or take that decision over for some or all governed data; whoever runs the portal (INN) then answers for access to those files on that machine. The files stay where they are either way.

**Why it matters now:** This has to be settled before a machine is connected.
**Before answering:** consent forms or data agreements may name who must be the principal, ultimate holder or controller of participants' data (for example the principal investigator). If they do, that may rule out some answers, or require the portal to act on that person's behalf; the privacy office or ethics board confirms.
**For the balance:** handing the decision to the portal means changing who owns the files on that machine, which takes administrator access there; it gives the most control. Leaving it with the researchers needs no administrator access; the portal then controls only who gets in through the portal.

*Example:* A lab's imaging folder sits under the lab manager's own account on the INN storage server.

Options:

- **The researchers who own them, as today. The portal can also read them.** *In practice:* Least change. The portal controls access through the portal; researchers can still give others access directly, outside the portal's records, and answer for it.
- **The portal, for some data (for example identifiable data); researchers for the rest.** *In practice:* Most control where it matters most. INN answers for access to that data; researchers for the rest.
- **The portal, acting on behalf of the researchers named in the consent.** *In practice:* The named researchers stay responsible; the portal controls access for them. Needs the consent and agreements to allow it.
- **The portal, for all governed data.** *In practice:* The most control. INN answers for all access to governed data on the machine; direct work there is arranged by its administrator.
- **The researchers, and the portal can't read the files.** *In practice:* The portal can't reach that data.

### <a id="a2"></a>A2. Which activity on POSIX data must be recorded, and for which data?

Access through the portal is recorded file by file and person by person in the portal. Where INN has administrator access (this year's machines), the machine's own records can also show each portal access, by person. Work done directly on the machines, such as scrubbing, can be recorded if the machine's administrator sets it up.

**Why it matters now:** This sets what the machines' administrators must set up.
**For the balance:** records kept by the machine itself need administrator access on every machine where they're required; records kept by the portal need none.

*Example:* A privacy office asks who handled a participant's identifiable scans last month, including during scrubbing on ImageTech's machine.

Options:

- **Access through the portal only.** *In practice:* Already possible. Work done on the machine itself isn't recorded.
- **Also who changes files directly on the machine, for identifiable data.** *In practice:* Covers scrubbing. The machine's administrator sets up the recording.
- **Also who reads files directly on the machine, for identifiable data.** *In practice:* The fullest account. Set up by the administrator; the records grow large.
- **Whichever of the above is chosen, for all data on the machines, not only identifiable data.** *In practice:* One rule everywhere. More to store and review.

Where this comes from: strategy 4.1 (g)

### <a id="a3"></a>A3. How soon must the portal show changes made directly on the machines?

Changes made through the portal show up straight away. Files created, changed or deleted directly on the machine, for example by scrubbing, have to be noticed by the portal; until then they don't appear in it.

**Why it matters now:** This sets how the portal keeps track of files on the machines.
**For the balance:** reporting changes as they happen usually needs administrator access on the machine, at least to set up; a regular check every few minutes or hours works without it.

*Example:* ImageTech staff finish defacing a batch of scans. A researcher at INN opens the portal to look for them.

Options:

- **Within seconds, as if the files had been uploaded through the portal.** *In practice:* Feels immediate. Needs the machine to report every change as it happens.
- **Within a few minutes.** *In practice:* Little difference in practice for most work. A regular check of the machine is enough.
- **Within a few hours, or when someone asks the portal to refresh.** *In practice:* Simplest. People may look for files that aren't listed yet.

## Part B. Confirmation

This has already been decided and built. Confirming it takes it off the list.

### <a id="b1"></a>B1. Confirm: Access is given to files and folders by name, and access to a folder also covers files added to it later. The intended next step is a Data Access Agreement (DAA): signing one gives the person a predetermined set of access for its lifespan. That comes after POSIX.

This is how the access-control fixes now in review work (decided 1 October). The portal already has a placeholder for agreements (a set of access with a lifespan), but it doesn't do anything yet, and there's no way to sign one. DAA-granted access will use the same access rules, so nothing built now rules it out.

Source: strategy 4.1 (b), (e), (g); 4.2 (d); 5.1

## Part C. The current portal

Decisions the next release and the access-control fixes need. None of these depend on POSIX.

### <a id="c1"></a>C1. Who decides the access settings for newly uploaded data?

When data is uploaded, someone or something sets who can see it.

**Why it matters now:** New users now get a default role (tickets INN-282 and INN-283); new uploads need a default too.

*Example:* A student uploads a dataset covered by a restrictive agreement and leaves access open to the whole project by mistake.

Options:

- **The person uploading it.** *In practice:* Flexible. Errors depend on each uploader's care.
- **The project's default settings.** *In practice:* Consistent within a project. Data with different conditions gets the same default.
- **The conditions attached to the data, such as its agreement or sensitivity.** *In practice:* Settings match agreements automatically. The data's conditions must be recorded before or at upload.

Where this comes from: strategy 4.1 (e)

### <a id="c2"></a>C2. Who can read access records in this release?

The strategy asks for 'transparent logging' of access. The portal doesn't yet keep a record of who accessed what that anyone can read.

**Why it matters now:** This sets what has to be built before release, if anything.

*Example:* A data owner wants to see who accessed their dataset last month, without having to ask an administrator.

Options:

- **Administrators.** *In practice:* Simple. Owners depend on administrators for answers.
- **Data owners too, for their own data.** *In practice:* Owners can check for themselves. Records have to be filtered so each owner sees only their own data.
- **As above, and any change to the records can be detected.** *In practice:* Records can be trusted in an investigation. It adds technical work.
- **None needed for this release.** *In practice:* Nothing to build now. Questions about access go unanswered until it's built.

Where this comes from: strategy 4.1 (g); 5.5 non-functional 3

### <a id="c3"></a>C3. When the file list is filtered, what can be selected for download or delete?

The file list can be filtered to show only some files, for example only the .nii scans. The risk is selecting a folder while the list is filtered: the folder also holds files the filter is hiding, and a download or delete would include them without the person seeing them.

**Why it matters now:** This happened (ticket INN-295): selecting a folder under a filter downloaded or deleted everything in it. The fix waiting to merge uses the first answer below. This checks that's the behaviour you want.

*Example:* A researcher filters a folder of 2,000 files down to 40 scans and selects them to download.

Options:

- **Only the files shown. Folders can't be selected while filtering (the fix in review).** *In practice:* Nothing hidden is ever included. Selecting many files takes a few more clicks.
- **Selecting a folder selects only the files in it that the filter shows.** *In practice:* Quicker. Needs a further change before merging.
- **Selecting a folder selects the whole folder, after a warning.** *In practice:* Matches the folder view. Hidden files are included, which is what caused the original bug.

Where this comes from: ticket INN-295

### <a id="c4"></a>C4. Is access by type of file needed?

Today access is given to files and folders. Some uses may need access to one type of file only.

**Why it matters now:** If it's needed, the access-control fixes should leave room for it now.

*Example:* A collaborator should get the anatomical scans in a study folder but not the questionnaires beside them.

Options:

- **Not needed. Folders are organised so access by folder is enough.** *In practice:* Nothing to build. Data has to be laid out with access in mind.
- **Needed, by file name ending (for example .nii) within a folder.** *In practice:* Simple to state and check. File names can be misleading.
- **Needed, by what the data is (for example 'anatomical scan'), from its description.** *In practice:* Matches how people think about data. Depends on files being described accurately.

### <a id="c5"></a>C5. Is 'everything in this folder except ...' needed?

Today access to a folder covers everything in it. An exclusion would hold some files back.

**Why it matters now:** Exclusions change how every access check works, so it's better to know before the fixes merge.

*Example:* A collaborator gets a study folder, except one participant who restricted their data.

Options:

- **Not needed. Restricted files go in a separate folder.** *In practice:* Nothing to build. Relies on files being placed correctly.
- **Needed.** *In practice:* Fine-grained control. Every check has to look for exclusions as well as access, and mistakes are harder to see.

### <a id="c6"></a>C6. Should access be able to end on a date?

Today access lasts until an administrator removes it.

**Why it matters now:** Agreements often run for a fixed period.

*Example:* A collaborator's access should end when the data agreement ends in March.

Options:

- **Not needed now. Administrators remove access by hand.** *In practice:* Nothing to build. Access can outlast the agreement if nobody remembers.
- **Access can be given with an end date, and ends automatically.** *In practice:* Agreements are honoured without anyone remembering. A small addition to every access check.
- **No automatic end, but administrators are reminded to review.** *In practice:* Keeps a person in the loop. Relies on reminders being acted on.

## Part D. POSIX: other questions

Access to files on POSIX machines through the portal: browse, download, upload. POSIX brings data held on researcher-owned storage at INN and ImageTech under the portal's rules.

### <a id="d1"></a>D1. How does identifiable data move between INN and ImageTech?

Today the portal moves files through the user's own computer: download, then upload. For identifiable data, that puts it on someone's laptop.

**Why it matters now:** Moving data between the two sites is a main reason for POSIX. Moving it directly between the two machines is new work.

*Example:* A batch of scans collected at ImageTech has to reach INN's server for analysis.

Options:

- **Directly from one machine to the other, started through the portal.** *In practice:* Data never passes through a laptop, and the portal records each transfer. New work to build.
- **By staff, outside the portal, as now.** *In practice:* Nothing to build. The portal doesn't control or record those transfers.
- **Through the portal by download and upload.** *In practice:* Nothing new to build. Identifiable data lands on the user's computer on the way.

### <a id="d2"></a>D2. Who counts as an outside collaborator?

The strategy allows sharing with collaborators 'who may or may not be registered'. The portal needs some way to know who they are.

**Why it matters now:** External collaborators need access to data held on POSIX machines.

*Example:* A clinician at another hospital needs to view a few results for a joint paper.

Options:

- **Someone given a guest account when invited.** *In practice:* INN knows exactly who they are. Someone has to create and later remove guest accounts.
- **Someone who signs in through their own institution.** *In practice:* No new accounts. Only works for institutions in the federation.
- **Anyone holding the link or access code. No identity is recorded.** *In practice:* Quickest. Anyone the link is forwarded to gets access, and nobody knows who used it.

Where this comes from: strategy 4.2 (c)

### <a id="d3"></a>D3. When can files leave the POSIX machines?

Downloading a file takes it out of the governed environment. Scrubbed data is meant to leave this way; it's also where a missed face or a name in a file header would get out.

**Why it matters now:** Releasing scrubbed data is the main way data leaves the governed environment.

*Example:* A batch of defaced scans is ready to move to open storage, and a student wants maps made from identifiable data on their laptop.

Options:

- **Any file can be downloaded.** *In practice:* Convenient. Once downloaded, INN has no control over it.
- **Only if the conditions attached to it allow.** *In practice:* Respects the agreements. Depends on each file's conditions being recorded (Part C, question 1).
- **Only after someone approves it.** *In practice:* A person checks each download, like a trusted research environment's 'airlock'. Takes staff time.

Where this comes from: strategy 4.5 (c)

### <a id="d4"></a>D4. What conditions apply to results uploaded back?

Researchers upload results made from POSIX data. The question is whether the source data's conditions follow them. The portal only knows what a result was made from if the uploader says so.

**Why it matters now:** Some communities require derivatives of their data to stay in a governed environment.

*Example:* A result combines an open atlas with imaging under an agreement that forbids commercial use. Can it be shared with an industry partner?

Options:

- **None. Results belong to the person who made them.** *In practice:* Easy to share. Conditions on the original data can be bypassed by running an analysis.
- **All the conditions of every dataset that went into them.** *In practice:* Agreements are always honoured. Mixed results can become hard to share at all.
- **All the conditions, unless an approved step (for example, aggregation) relaxes them.** *In practice:* Agreements honoured, and approved steps free results for wider use. Someone approves the steps.

Where this comes from: strategy 4.3 (c); 5.5 step 6

### <a id="d5"></a>D5. Who may see results made from protected data?

Results made from protected data may themselves be sensitive.

*Example:* A student uploads results made from a restricted dataset. Their supervisor has no access to that dataset.

Options:

- **Only the researcher who made them.** *In practice:* Conservative. Sharing results needs a separate step every time.
- **Anyone with access to all the data that went in.** *In practice:* Consistent with the original data. Can be too strict for summaries.
- **Whoever the conditions attached to the results allow.** *In practice:* Matches the agreements. Depends on question 4.

Where this comes from: strategy 4.3 (d); 4.5 (b)

### <a id="d6"></a>D6. What counts as a copy of data?

Several promises, such as deleting data and honouring withdrawal, depend on what counts as 'a copy'.

*Example:* A participant's scan is removed. Do the statistics computed from it, the preview image and the log line naming the file also have to go?

Options:

- **Saved copies of the data itself.** *In practice:* Easiest to honour. Results, previews and logs can still reveal the removed data.
- **Also results made from it.** *In practice:* Results follow the data. Every result has to be traceable to its sources.
- **Also temporary files, backups and log entries that identify it.** *In practice:* Most complete. Touches backups and logs, which are hard to edit and sometimes needed for audit.

Where this comes from: strategy 4.6 (d); 5.4

### <a id="d7"></a>D7. May access records contain identifying details?

Access records say who did what to which data. If they name participants, the records themselves become sensitive.

**Why it matters now:** POSIX is where identifiable data first comes into the portal.

*Example:* An auditor needs to confirm a withdrawn participant's data was deleted, but the record proving it would itself name that participant.

Options:

- **Yes, they may identify the data and the people involved.** *In practice:* Easy to read and act on. They must be protected like personal information.
- **No, only coded references that can't identify anyone on their own.** *In practice:* Safe to keep. Reading them needs a protected lookup key.

Where this comes from: strategy 5.4 postcondition 3

### <a id="d8"></a>D8. If a participant withdraws consent, what has to be removed?

The strategy doesn't say what the platform must remove when consent is withdrawn.

**Why it matters now:** POSIX is where identifiable participant data first comes into the portal.

*Example:* A participant withdraws. Their scans were used in twelve analyses, and two have been published.

Options:

- **Their original data.** *In practice:* Achievable. Results built from their data remain.
- **Also everything made from it.** *In practice:* Honours withdrawal fully. Every result must be traceable to its sources.
- **Also log entries that identify them.** *In practice:* Most complete. Reaches into logs and backups.

Where this comes from: not in the strategy

### <a id="d9"></a>D9. Does de-identifying data change the conditions that apply to it?

Much INN imaging is de-identified, for example with faces removed from scans.

**Why it matters now:** Identifiable data on POSIX machines may produce de-identified versions that people want to share.

*Example:* A defaced dataset derived from identifiable scans is requested by a researcher at another university.

Options:

- **No. De-identified data keeps the original conditions.** *In practice:* Cautious. It stays as hard to share as the original.
- **Yes. An approved de-identification step can relax them.** *In practice:* Shared more widely. Someone, such as the privacy office, approves which methods count.

Where this comes from: not in the strategy

### General questions

#### 1. Can files within one dataset come under different agreements or conditions?

If they can, conditions have to be tracked file by file rather than once per dataset.

#### 2. How often do results combine data under different agreements or conditions?

If results take on every condition of their sources (Part D, question 4), frequent mixing makes them hard to share.

#### 3. Consent withdrawal and de-identification aren't in the strategy. How much should they count?

Part D, questions 8 and 9 cover them. This sets how much weight they get against what the strategy asks for.

## Part E. Later

These stay open. They don't hold up the current portal or POSIX, so nothing here needs an answer now.

#### Analysis through the portal (compute)

- Can protected data be copied elsewhere to be analysed?
- What must a computing system be able to show before it analyses protected data?
- Can researchers add their own tools to pipelines?
- What does 'reproducible' mean?
- What does checking that a pipeline is 'compatible' look at?
- Which completed analyses does a researcher see?
- Does one permission cover both the portal and computing?
- What does 'secure during computation' mean? Long-term use case: scrubbing outside the governed environment while the data stays encrypted.
- Can using uploaded data in an analysis create another copy of it?

#### Partner data

- What may the platform hold in order to reach a partner's data?
- What does 'without permanently storing external data' mean?
- How far must the audit trail reach when partner data is used?

#### Data agreements

- How far do the conditions of a data agreement travel?
- When does a data agreement count as met?
- Which conditions from a data agreement does the platform enforce?

#### Data description and records

- When a record or analysis refers to a dataset, what must it pin down?
- What are uploads checked against?
