# POSIX storage: questions for system administrators

The questions as put on 27 October 2026 to RCG's system administrators, for the INN storage server, the Water Tower server and ImageTech's machine. Some background has moved on since; the decision registry records each question's status and answer.

### Why these questions

The portal will serve files on these machines through a small file service. Each approved download or upload link gets its own temporary user ID on the machine, and only that ID can read the link's files, so the operating system itself enforces every grant. A privileged helper (root) sets this up and removes it when the link expires; the web-facing part is unprivileged and can't read the data.

That design depends on facts about the machines. Answers per machine are fine; 'don't know' is a useful answer too.

Background for every item: the POSIX entries in the [decision log](../design/decision-log.md#posix-storage) and the POSIX diagrams (`docs/diagrams/posix-*.md`).

### <a id="sa-1"></a>SA-1. Which filesystem is the governed data on (ext4, XFS, ZFS, GPFS/Storage Scale, Lustre, an NFS mount)?

**Why it matters:** GPFS and Lustre have built-in change logs and access audit; on the others they have to be built. It also decides which ACL features exist.

### <a id="sa-2"></a>SA-2. Is the data on local disk or mounted over the network (NFS, SMB)? If NFS, which version, and how are user IDs mapped?

**Why it matters:** Network mounts change how per-user permissions and user IDs behave.

### <a id="sa-3"></a>SA-3. Can a large range of numeric user IDs be reserved for temporary IDs (no account entries)? Is it free locally, in LDAP/SSSD and across NFS ID mapping?

**Why it matters:** One ID per approved link; links are per click today, so a 10,000-file folder upload uses 10,000 IDs. The local build uses 2,000,000 upward.

### <a id="sa-4"></a>SA-4. Are POSIX ACLs enabled on the data filesystem, and is there a limit on ACL entries per file?

**Why it matters:** Each live link adds one ACL entry to each of its files; many links on the same file could reach a limit.

### <a id="sa-5"></a>SA-5. Can the file service's helper run as root (or with CAP_SETUID, CAP_SETGID, CAP_CHOWN, CAP_FOWNER)?

**Why it matters:** It starts per-request processes as temporary IDs and edits ACLs. Without it the operating system can't enforce each link.

### <a id="sa-6"></a>SA-6. Is auditd available, and can it log file access under the data folder? Where do logs go and how long are they kept?

**Why it matters:** Per-person audit of work done directly on the machine.

### <a id="sa-7"></a>SA-7. Kernel and OS versions?

**Why it matters:** Which change-notification and isolation features exist.

### <a id="sa-8"></a>SA-8. Which ports can be opened to users and the portal, and between the INN and ImageTech machines? Who manages the firewalls?

**Why it matters:** The file service must be reachable; direct transfer between sites.

### <a id="sa-9"></a>SA-9. Can the governed data be handed to a portal-managed account (owner changed in place, files private, folders pass-through only), or must it stay under researchers' own accounts?

**Why it matters:** The design needs the first. Kelly is asked whether it's acceptable; this asks whether it's possible.

### <a id="sa-10"></a>SA-10. Are filesystem snapshots available (ZFS, GPFS)?

**Why it matters:** Fixed-snapshot downloads, if ever required.

### <a id="sa-11"></a>SA-11. Is there a Globus endpoint on these machines, and does INN's licence include a subscription?

**Why it matters:** A possible off-the-shelf transfer path between sites.

### <a id="sa-12"></a>SA-12. How are TLS certificates issued for these hosts?

**Why it matters:** Browsers connect to the file service directly, so each host needs a certificate.

### <a id="sa-13"></a>SA-13. Is data at rest encrypted on these machines?

**Why it matters:** Handling identifiable data.

### <a id="sa-14"></a>SA-14. Who administers ImageTech's machine, and do the same answers apply there?

**Why it matters:** A partner facility; administrator access is available but details may differ.

### <a id="sa-15"></a>SA-15. If the data is on NFS or another network filesystem, what are the attribute-cache settings (actimeo, noac), and do other machines write to it?

**Why it matters:** A resumed download checks whether the file changed by its size and timestamps. Cached attributes can hide a change for seconds and splice old and new bytes. Seen in local testing.

### <a id="sa-16"></a>SA-16. Can auditd record file opens by the temporary ID range under the data folder?

**Why it matters:** Per-file audit of portal access by person: temporary ID, then link, then user.
