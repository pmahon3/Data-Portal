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
