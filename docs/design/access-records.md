# Access records: what is recorded, how changes are detected, how it scales (design, reviewed: false)

2026-11-02. Implements AC-9 (C2: administrators and data owners read the records, and any change to
them can be detected; D7: records name files and people as they are). Later sources: PX-10 (direct
activity on the machines). Must allow AC-7's removal of identifying log entries (D8).
Registry: `DS-access-records` and the questions under it.

## What the portal can see

Every data action goes through the backend, which decides it (`Checker`) and then either acts or
hands the browser a short-lived link. The bytes move between the browser and storage:

| Action | What the backend sees | What storage could add |
|---|---|---|
| Download a file | it decided, and issued a link valid 15 minutes | Object storage: a read, if Ceph's ops log records it (AR-CEPH-GET). POSIX: the file service already logs each read with the link's ID (`storage-gateway.audit`). |
| Download several (bundle) | it decided each file and handed the list to the bundler | the bundler's reads, as above |
| Upload | it decided, issued upload links, and later sees the upload complete | Ceph's "created" event, already received |
| Delete | it decided and deleted each file itself | Ceph's "removed" event |
| Browse a folder | it decided and returned the names | — |

So a record says what the portal did, named for what it is: **"link issued to Y for X, valid until
T"**, not "Y read X". Each record carries the link's ID, so a storage-side record of the actual read
(the file service's lines now, Ceph's ops log if available, PX-10's machine records later) joins to
it. Refusals of data actions are recorded too (who tried what); refused listings aren't.

## What is recorded (AR-SCOPE)

Reading, writing and deleting data are recorded, always. Two further kinds wait on a decision, each
a setting so either answer needs no rework:

- **Browsing** (`ACCESS_RECORDS_LISTINGS`): a listing shows file names, which may contain participant
  IDs (D7). Recording it multiplies the volume (see Scale).
- **Changes to access** (`ACCESS_RECORDS_POLICY_CHANGES`): who gave or removed which policy. Cheap.

## A record

One **request record** per request, and one **file row** per file it touched.

- Request: time, user, action (`download-link`, `bundle`, `upload-link`, `upload-complete`,
  `delete`, `refused`, and the optional kinds above), storage instance, link ID, outcome, request
  ID, and the digest of its file rows.
- File row: request, path (bucket and key), size if known.

Records name files and people as they are (D7). Paths are what make a record identify a participant.

## Detecting changes (C2)

A **hash chain**: each request record has a digest, and the chain value of record *n* is
`SHA-256(chain[n-1] || digest[n])`. Changing, adding, removing or reordering any record changes every
chain value after it.

**What each digest covers, so records can be erased (D8):** a plain chain over the content would make
removing a log entry indistinguishable from tampering. So each file row has a random 16-byte salt and
a digest `SHA-256(salt || canonical row)`; the request's digest covers its own salted content and the
digests of its file rows, in order. To erase (AC-7: "log entries that identify them"), the content
and salt are deleted and the digests kept. The chain still verifies, the gap is visible as
"erased", and the erasure is itself a recorded request (who, when, under which withdrawal, how many
rows; never the erased paths). The salt also stops anyone guessing a path (`sub-001/...`) from a
kept digest. Robust to D6 and AC-7: whatever counts as a copy, a record can be erased in this way.

**Against whom:** a chain kept only in the database can be rewritten whole by someone who can write
to the database. So the chain's latest value is **anchored** outside it at a set interval
(`ACCESS_RECORDS_ANCHOR_EVERY`, default an hour), through a pluggable sink: an object-storage
bucket with object lock, a file on another machine, or a message to administrators. Which one, and
whether it is out of the database administrators' reach, is a question for the sysadmins
(AR-ANCHOR). Records written since the last anchor are protected only by the database's own
permissions.

**In the database:** the backend's database role may insert and read the record tables, not update
or delete them; erasure goes through one function owned by another role. A verification job
recomputes the chain daily and compares it with the anchors; a mismatch notifies administrators.

**Format version:** each record carries a format version; the digest covers canonical JSON (sorted
keys). New fields come with a new version, so the format can grow. What is one-way is the hashing
scheme itself: once records exist under it, changing it means verifying old records under the old
one forever.

## Who reads them (C2)

- Administrators: all records, filtered by person, path prefix, action and time.
- Data owners, for their own data: *assumed* to be the managers of each project that includes the
  storage instance, as end-date reminders already use (`end_reminders.recipients`). There is no
  per-folder owner yet; if owners turn out to be per dataset, the filter changes, the records don't.
- Reading records is itself recorded.

## Writing them on the request path

The record is written after the backend decides and signs, and before it answers. If the record
can't be written, the request fails (503) and no link is returned: fail closed, so no access goes
unrecorded. Production runs two backend replicas, so the chain is extended under a row lock on the
chain head, in the same transaction as the insert.

## Scale

Sizes from the repo: a 100,000-file folder (AC-11) and the 34,000-file MEG derivatives
(the POSIX testing strategy). Usage rates below are **assumptions** until RDT gives real ones.

- **Per file:** a file row is about 150 bytes (8 id, 8 request, ~70 path, 16 salt, 32 digest, row
  overhead), about 250 bytes with its indexes. A 100,000-file download or delete: 100,000 rows,
  about 25 MB; the MEG case about 8.5 MB.
- **Per request:** the chain grows by one value per request, not per file, so a large request costs
  one lock and one hash of 100,000 digests (SHA-256 over 3.2 MB, a few milliseconds).
- **Writing:** file rows go in with one `COPY` per request. Target: recording a 100,000-file request
  adds under 1 s, the same budget as deciding it (AC-11); a timing test checks it, as
  `test_access_scaling.py` does.
- **Throughput:** the chain lock serializes requests across replicas: about one to two milliseconds
  each, so several hundred recorded requests a second. Enough for interactive use; bulk machine
  activity (PX-10) goes in batches, one request record per batch.
- **Growth (assumption):** 1 million file rows a month is about 250 MB a month, 3 GB a year.
  Recording listings (AR-SCOPE) would add a row per name shown: a user browsing a 10,000-entry
  folder adds 10,000 rows. That's why it's a setting.
- **Reading:** indexes on (time), (user, time), (instance, time) and the path (`text_pattern_ops`, for
  prefix queries); owners' queries are filtered by instance. Paged, newest first.
- **Retention (AR-RETAIN):** tables are partitioned by month. Dropping an old partition keeps its
  last chain value as a checkpoint, so verification starts there. How long to keep records is a
  setting (`ACCESS_RECORDS_KEEP_MONTHS`, default: keep).

## Questions for others

| ID | Question | Owner | Until answered |
|---|---|---|---|
| <a id="ar-scope"></a>AR-SCOPE | Besides reading and changing data, are browsing (names seen) and changes to access recorded? | leadership | both are settings, off and on respectively |
| <a id="ar-retain"></a>AR-RETAIN | How long are access records kept? | privacy | kept |
| <a id="ar-anchor"></a>AR-ANCHOR | Where can the chain's latest value be kept out of reach of whoever administers the database? | sysadmins | a message to administrators |
| <a id="ar-ceph-get"></a>AR-CEPH-GET | Can Ceph's ops log record each read, with the signed link's ID? | sysadmins | portal records only (links issued) |

## Choices made here (reversible, testable)

- Records in the portal's PostgreSQL, in their own tables; one request record plus file rows.
- Fail closed when a record can't be written.
- Refused data actions recorded; refused listings not.
- Chain per portal (not per instance), anchored hourly by default.

## Order of work

1. Record tables, the chained writer and verification, with the timing test (no UI).
2. Recording at each data endpoint (download link, bundle, upload, delete, refusals), test-first
   per endpoint, each test naming AC-9.
3. Reading: an administrators' page and an owners' view, with the guide page.
4. Erasure (with AC-7), anchoring sinks (with AR-ANCHOR), the file service's reads joined by link
   ID (with PX-10).
