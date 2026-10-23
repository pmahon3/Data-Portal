# POSIX Storage: Temporary ID Lifecycle

Each approved link gets its own temporary user ID from a reserved range, the first time the link is
used to read or upload. This diagram is **checked**: a test drives the helper through every situation
and records the states each ID actually passes through. The transitions it observes must be exactly
these, no more and no fewer.

```mermaid
%% check: link-lifecycle
stateDiagram-v2
    [*] --> Free
    Free --> Active: a link is first used (read or write)
    Active --> Quarantined: link expired, every grant revoked on the same file
    Active --> Retired: link expired, a granted file was moved or replaced on the machine
    Quarantined --> Free: quarantine period over
    Retired --> [*]
```

| State | Meaning | Where it's recorded |
|---|---|---|
| Free | Not held by any link | absent from the helper's state |
| Active | Held by one live link; may have ACL entries and a staging folder | `links` |
| Quarantined | Link expired and fully revoked; not reused yet, so audit records never mix two links | `quarantine` (until a time) |
| Retired | An ACL entry may survive on a moved file, so the ID is never reused; logged for an administrator | `retired` |

---

**Last Updated:** 2026-10-23
**Branch:** feature/posix-port
