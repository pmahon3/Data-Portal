# Design decision log

Design decisions made in conversation and recorded only in working notes until now. Each entry has a
fixed anchor; the decision registry links to it. Where code implements a decision, the entry names
the branch that brought it in.

### <a id="ds-literal-paths"></a>DS-literal-paths. Literal policy paths, one decision layer

Decided by Patrick, 2026-10-01. The access-control bugs (INN-289, INN-291, INN-292, INN-293) are fixed
by a redesign rather than patches: policy paths are literal (no character in them is a pattern), and
every access decision goes through one layer (`Checker` in `backend/core/services/policies/rules.py`).
It supersedes the regular-expression validation of policies. Built in `bug/INN-297-decision-layer`.

### <a id="ds-listing-action"></a>DS-listing-action. The listing API takes an action

Decided by Patrick, 2026-10-27. `GET /api/tree/{folder_id}` filtered on `read` only, so a write-only or
delete-only user couldn't list their own files through the API (AC-1). "Any action implies read" was
rejected: write on a study folder must not show other participants' files, since a site uploads its
participant's data without seeing the others. The listing API takes `access=read|write|delete`
(default `read`), filtered per action as the screens are. Built in `bug/listing-per-action`.

### <a id="ds-bundle-recheck"></a>DS-bundle-recheck. Access is checked again when a bundle is downloaded

A multi-file download (bundle) is checked per file when it's created. Its owner is recorded, so only
the person who asked can fetch it (`bug/INN-272-bundle-owner`), and access is checked again at
download, so a policy removed in between takes effect (`bug/INN-272-recheck`).

### <a id="ds-s3-bundler"></a>DS-s3-bundler. Object storage keeps the application bundler

Decided by Patrick, 2026-10-29, walking back the plan of 2026-10-27. For object storage
(non-identifiable data by default) the application bundler stays as it is: no browser-built ZIP and
no command-line tool as the default. For POSIX (identifiable data), multi-file downloads are a ZIP
streamed by the file service on the machine, with nothing stored ([streaming spec](streaming-spec.md)).
Users know which data is identifiable and choose the storage accordingly; the portal doesn't tag it.

### <a id="ds-no-front-ends"></a>DS-no-front-ends. Nothing in front of storage

Decided by Patrick, 2026-10-27. No content delivery network or HTTP/2 proxy sits between users and
storage, even one that relays bytes unchanged. So browsers keep HTTP/1.1's six connections per host to
object storage, and storage must be reachable from users' machines. Both are accepted limits of the
browser path. Relaxed for non-identifiable data's bundles by [DS-s3-bundler](#ds-s3-bundler).

### <a id="ds-tls-in-service"></a>DS-tls-in-service. The POSIX file service serves HTTPS itself

Follows from [DS-no-front-ends](#ds-no-front-ends): users' machines, including external
collaborators', connect to the file service directly, so it terminates TLS itself, given the host's
certificate and key (`GATEWAY_TLS_CERT`, `GATEWAY_TLS_KEY`). Found missing in the first run on a real
machine (2026-10-31). Built on `posix/stack` ("feat(posix): the file service serves HTTPS itself when
given a certificate").

### <a id="dt-py-bundler"></a>DT-PY-BUNDLER. Retire the Python bundler

Decided by Patrick, 2026-10-31, after a review of both bundlers. The Python bundler duplicated the
Java one's job lifecycle, and its de-duplication of identical requests would give two users one
bundle, which clashes with one owner per bundle (INN-272). The Java bundler is the only one, and the
`BUNDLER_PROVIDER` switch is gone. Built in `chore/retire-python-bundler`.

### <a id="r-specific"></a>R-SPECIFIC. What "the specific solution" means for this year's machines

Open with the technical team (RDT), from the planning meeting of 2026-10-27. This year's machines have
administrator access. The question is whether "the specific solution" for them still has a file
service on the machine with signed links (the current design), or has the portal read the files
itself with no file service (a different design, which would need a rewrite for partners' machines).

### <a id="px-imagetech-upload"></a>PX-IMAGETECH-UPLOAD. How ImageTech uploads reach the POSIX machine

Seen on site by Patrick, 2026-10-31. A technician uploads from a desktop connected to the imaging
machine, where scans land. It has internet access over HTTPS, possibly through a VPN. The POSIX
machine for identifiable data is in SFU's data centre, so uploads leave the hospital network. Routing
into the POSIX machine is for the system administrators.

## POSIX storage

### <a id="ds-namespace"></a>DS-namespace. One namespace per POSIX instance

Proposed by Patrick, 2026-10-22; not yet confirmed (R-NAMESPACE). Each POSIX instance has one
namespace, used like a bucket name in paths, policies and the file tree.

### <a id="ds-link-reuse"></a>DS-link-reuse. Links are reusable until they expire

Decided by Patrick, 2026-10-22. A link can be used again until it expires, so a download can resume
([PX-5](../requirements/posix-storage.md#px-5)); expiry is checked when a download starts or resumes.
Built in `posix/base`.

### <a id="ds-admin-where-needed"></a>DS-admin-where-needed. Administrator access only where a requirement needs it

Proposed by Patrick, 2026-10-28 ([PX-8](../requirements/posix-storage.md#px-8)). One build runs
without administrator access (the file service runs as one account that holds the data, and the
portal's links alone decide access) or with it (temporary IDs, DS-temp-ids). Scouting
(`posix/scout`).

### <a id="ds-temp-ids"></a>DS-temp-ids. With administrator access, the operating system enforces each grant

Decided by Patrick, 2026-10-23. The web-facing service can't open data files; a root access broker
opens each requested file as a temporary user ID with one ACL entry on that file, so the operating
system enforces each grant. Uploads are staged outside the data tree and placed by the broker;
symbolic links are never followed. Scouting (`posix/scout`).

### <a id="ds-grant-per-approval"></a>DS-grant-per-approval. One temporary ID per approval, not per link

Decided by Patrick, 2026-10-27, replacing one per link. The links of one approved request share an
approval ID, so a 10,000-file download uses one temporary ID. The approval lasts until its latest link
expires; the ID is then cleared and quarantined before reuse. Scouting (`posix/scout`).

### <a id="ds-default-access-mode"></a>DS-default-access-mode. A machine runs user-per-approval unless set otherwise

Decided by Patrick, 2026-11-04. `GATEWAY_ACCESS` chooses the mode per machine: `user-per-approval`
(the default; DS-temp-ids) or `shared-account` (one account holds the data). Scouting
(`posix/scout`).

### <a id="ds-os-audit"></a>DS-os-audit. The machine's own records trace each temporary ID to a person

Proposed by Patrick, 2026-10-23 ([PX-10](../requirements/posix-storage.md#px-10)). With administrator
access, the access broker writes one line per operation (link, temporary ID, portal user, path,
approval), so the operating system's audit records trace to a person. File names in these lines may
identify participants ([D7](../questions/use-cases.md#d7)). Scouting (`posix/scout`).

### <a id="ds-data-owner"></a>DS-data-owner. The exposed area keeps owners and groups, closed to everyone else

Decided by Patrick, 2026-10-31, replacing the data-owner layout of 2026-10-23. Administrators grant
direct access with groups or ACL entries ([PX-9](../requirements/posix-storage.md#px-9)); the
portal never changes owners or groups and adds only temporary-ID entries. New files and uploads take
the folder's group and default entries. The layout tool (`python -m app.layout`) reports and fixes
what differs. Scouting (`posix/scout`).
