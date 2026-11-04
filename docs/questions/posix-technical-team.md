# POSIX storage: decisions for the technical team

The questions as put on 27 October 2026 to the RDT team (Alireza, Ishan), through Kelly. Some background has moved on since; the decision registry records each question's status and answer.

### Why these questions

A draft of POSIX access through the portal is built and tested locally (GitHub branch posix/stack): a file service on each POSIX machine serves files to holders of portal-signed links. It can run with administrator access, where each approved request gets its own temporary user ID and the operating system also enforces it, or without, as an ordinary account. Which way is Kelly's choice once both are estimated. Single-file download, resumable download, upload and delete work end to end; it hasn't run on a real machine or been reviewed.

Some parts can't go further without decisions that belong to the technical team, or facts only it has. Those are below. Where an answer isn't clear yet, a best guess and a note are more useful than a blank.

Background for every item: the POSIX entries in the [decision log](../design/decision-log.md#posix-storage) and the POSIX diagrams (`docs/diagrams/posix-*.md`).

### <a id="r-track"></a>R-TRACK. How should POSIX files get into the portal's file tree?

Files uploaded through the portal are registered as they arrive. Files already on a machine, and files created there directly (scrubbing outputs, collaborators' preprocessing), aren't seen until something tracks them. The object-storage path uses a bucket walk plus Ceph events. Proposed boundary: the file service lists a machine's files, and the existing sync takes that list like a bucket walk.

**Why it matters now:** Without it, existing data and scrubbing outputs can't be reached through the portal. Kelly is asked separately how soon changes must show (minutes or seconds).

*Example:* A batch of scrubbed scans appears on ImageTech's machine overnight.

Options:

- **The machine reports changes (for example fanotify or the filesystem's change log), with a periodic full walk as a safety net.** *In practice:* Near-immediate; most to build; depends on the filesystem (system administrators' question S1).
- **A periodic walk only (add, update and remove).** *In practice:* Simplest; changes show after the next walk. The current object-storage walk doesn't remove rows yet.
- **Register files when someone first browses to them.** *In practice:* No background work; listing large folders is slower.

Where this comes from: scope of work §4; use-case note §4

### <a id="r-rename"></a>R-RENAME. What should happen to access when a file or folder is renamed or moved on the machine?

Access rules name literal paths (since the access-control rework). A rename on the machine changes which rules cover the file. A rename of a folder of 100,000 files changes 100,000 rows.

**Why it matters now:** This decides whether access follows the location or the file, and how file tracking handles renames.

*Example:* Staff move a finished study folder from 'incoming' to 'released'.

Options:

- **Access follows the location: rules apply to whatever is at the path.** *In practice:* Simplest. Moving a file into a shared folder exposes it.
- **Access follows the file: stable identifiers (use-case note R6), rules rewritten or keyed by ID.** *In practice:* Survives renames. Needs identifiers in the file tree and a change to how rules are stored.
- **Renames and moves only through the portal.** *In practice:* Keeps the record exact. People can't reorganise files directly on the machine.

Where this comes from: use-case note R6; access-control STATUS: move and rename

### <a id="r-host"></a>R-HOST. How should the file service run on the POSIX machines?

With administrator access it has two processes in one container image: a web service that can't read the data and a small helper that runs as root (temporary user IDs' access, placing uploads, revoking at expiry); it needs a Linux filesystem with ACLs. Without, it's one web service running as an ordinary account that can read the data. Either way it needs a port reachable by browsers and the portal, and the portal's public key. For multi-file downloads it also asks the portal for each approved request's file list, then streams the files as one ZIP.

**Why it matters now:** Where and how it runs on each machine is open, and differs between the two ways of running it.

*Example:* The new Water Tower server is connected first.

Options:

- **As a Nomad job, with each POSIX machine a Nomad client.** *In practice:* Same deployment path as the rest of the portal. The machines join the cluster.
- **As a container run by systemd on each machine.** *In practice:* Independent of the cluster; each machine is managed on its own.
- **As native services (no container).** *In practice:* Fewest moving parts on the machine; packaging and upgrades by hand.

Where this comes from: docs/diagrams/posix-deployment.md; scope of work §4

### <a id="r-year"></a>R-YEAR. What did the 'about a year longer' estimate for the no-administrator option cover?

**Why it matters:** The first machines will use administrator access, so this matters for later partners who won't give it. Knowing what the year was (file tracking? temporary users without root? many kinds of host?) shows what that option would really cost.

*For example:* file tracking without privileged change notification; running on hosts INN doesn't control

### <a id="r-namespace"></a>R-NAMESPACE. Is one namespace per POSIX instance right?

Each POSIX instance has one configured name (for example inn-posix) used where S3 uses a bucket name: in paths, access rules and the file tree. Proposed, built that way, not yet confirmed.

**Why it matters now:** It's hard to change later: access rules name it.

*Example:* Two machines at ImageTech, each its own instance.

Options:

- **Yes: one configured name per instance.** *In practice:* Simple; names checked against bucket names.
- **No: each top-level folder on the machine acts as a bucket.** *In practice:* Mirrors S3 more closely. A new folder silently becomes a new 'bucket'; names can clash with S3 buckets.
- **Something else (say what in the notes).**

Where this comes from: [DS-namespace](../design/decision-log.md#ds-namespace)

#### Found while building: should each be a ticket?

- **An instance creator's automatic 'admin' grant gives no file access.** Nothing checks the 'admin' action, on development or the access-control rework.
- **The bucket-name check misses instances created since the last restart.** Names reach the file tree only at the next restart or sync.
- **GET /api/policies/?username=… returns 500.** IndexError in filter_policies.
- **Python bundler: reuse keyed on file names only (stale contents); duplicate requests during a job error.** Possible stuck duplicates if a worker dies.
- **Instance wrappers close shared storage agents when garbage-collected.** S3's client recovers; the POSIX agent now reopens its client.
