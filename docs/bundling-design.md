# Bundle identity, authorization, and caching

**Status:** proposal
**Scope:** the bundle request/redeem path (`/api/tree/bundle/*`) and the bundler service
**Date:** 2026-09-04

---

## 1. The defect

`GET /api/tree/bundle/{id}/status` and `GET /api/tree/bundle/{id}/download` authenticate
the caller but never check whether that caller may have the archive's contents. Any
logged-in user holding a bundle id can obtain a presigned download URL for it.

Verified end to end against a local stack with two users on disjoint grants
(`A → qa-bucket/user-a/.*`, `B → qa-bucket/user-b/.*`):

| step | result |
|---|---|
| B requests files 1, 2 individually | **403** each |
| A bundles files 1, 2 | ok |
| B reads that bundle's status | **200** |
| B requests that bundle's download URL | **200** + presigned URL |
| B fetches the URL and extracts | `user-a/a1.txt`, `user-a/a2.txt` |

Unauthenticated requests are correctly rejected with 401, so the endpoints do
authenticate. `download_url` (`s3_endpoints.py:353`) performs the missing check before
minting a URL; the bundle routes do not.

## 2. What the defect actually is

The bundler is a **proxy**. When a user requests multiple files the backend mints one
presigned URL per file — each already authorized at that moment — and the bundler
follows them and assembles a ZIP. Authorization has therefore already happened, per
file, at request time.

This matters for scoping the fix. A user forwarding a presigned URL is out of scope:
presigned URLs are bearer credentials by design, and what a user does with data they
were legitimately issued is governed by the data access agreement, not by the system.
The same is true of the resulting ZIP.

The bundle id is not that. It does not expire, is not scoped to a user, is not
revocable, and is not marked as secret — so it circulates through logs, tickets and chat
as an opaque reference. Yet possession alone is sufficient: a second user presents it on
their own authenticated request and the portal mints a **fresh** presigned URL for
contents that user cannot otherwise reach. That is not one user extending trust to
another; it is the system issuing a new credential on request.

The defect is the mismatch. Either bundle ids are identifiers, and these routes must
authorize the caller, or they are capabilities, and they need expiry, scoping and secret
handling everywhere they currently lack it. They are presently neither.

## 3. Decisions

### 3.1 Bundle identity is derived from content, not from the request

A bundle id is a function of what the archive contains. Two requests for the same
content produce the same id regardless of who asked or under what policy.

**Why:** it is the only identity scheme that permits cross-user reuse. Two researchers
entitled to the same data — from different machines, under different policy sets — must
be able to share one build if the requested content lies in the intersection of their
entitlements. Any id derived from the requester, or from the requester's grants, makes
that impossible by construction: a second user computes a different id and never finds
the existing artifact.

**Consequence:** the id carries no authority. Possession proves nothing, so the defect in
§1 cannot recur — not because a check was added to a capability, but because the artifact
stopped being one.

### 3.2 The content address is derived from the presigned URL

A presigned URL splits into a stable part and an ephemeral part:

```
http://minio:9000/qa-bucket/user-a/a1.txt ? X-Amz-Signature=... X-Amz-Date=... X-Amz-Expires=900
└──────────── stable: scheme + host + path ────────────┘ └──────── ephemeral: query ────────┘
```

Stripping the query yields an address that is identical across signings of the same
object and distinct between objects. Verified: two signings of one file produced
different URLs and the same address; a different file produced a different address.

**Why:** it generalizes. `scheme://host/path` is a URI, not an S3 concept — a POSIX
storage agent yielding `file:///mnt/store/proj/a.nii` produces an address the same way.
The bundler can compute it without knowing which backend produced the URL, so support for
generic stores does not require the bundler to learn about each one.

**Why not have the backend supply an identifier:** it would put storage-specific identity
derivation into the request contract, which is the thing that has to stay open.

### 3.3 Content addresses include the object's etag

Address on `(location, etag)` rather than location alone.

**Why:** the location is stable across *overwrites* as well as signings. Without the
etag, overwriting an object leaves the address unchanged and a cached archive would serve
stale bytes indefinitely. With it, the address changes when the content changes: the
stale entry becomes unreachable rather than wrong, and the next request is an ordinary
cache miss. No invalidation logic is required.

Verified: overwriting a test object changed its etag (`39284e43…` → `a45dd092…`) while
its path and presigned-URL location were unchanged.

**Cost:** the etag is a response header, not a URL component, so the bundler cannot derive
it from the URLs it is given. The backend already stores it on the `files` row (populated
at sync and on `upload_complete`) and can pass it alongside each URL at no cost.

**Known limits:**
- Multipart uploads produce `<hash>-<partcount>`, which depends on part size rather than
  content alone. Still deterministic per object and still changes on write, so staleness
  detection holds; it cannot be used to detect that two different objects hold identical
  bytes.
- A stored etag can lag reality if an object is overwritten out-of-band and the storage
  event has not yet been processed. This narrows the staleness window rather than closing
  it. Closing it entirely requires revalidation at build time.

### 3.4 Entitlement is validated at redemption, against current policy

Every redemption re-checks the caller against the policies they hold **now**, for the
content the bundle draws from.

**Why:** with a content-derived id, the artifact carries no information about who may
have it, so a shared cache requires an admission check by construction. The moment one
user's build can serve another, entitlement must be established per redemption.

**Why not record the creator and compare:** that asserts a fact about the past — *this
person was entitled when the bundle was made*. Bundle retention is currently 168 hours,
so a revoked grant would leave an archive openable for up to a week. The system's purpose
is to instantiate the data access agreement faithfully; an artifact that outlives the
agreement it was created under has stopped doing that.

**Cost:** measured. Checking every file is prohibitive at scale (≈380 ms for 10⁴ files),
but policies are path-scoped, so files sharing a directory resolve identically.
Deduplicating by parent folder gives **≈3.3 ms for a 10⁴-file bundle drawn from 50
directories** — a 115× reduction, scaling with tree shape rather than file count.

The polled `status` endpoint and the one-shot `download` endpoint should be treated
differently: status leaks readiness, not data, and does not need the full check.

**Caveat:** the dedup gain assumes bundles span few directories relative to their file
count. Deployments with fine-grained per-file grants would see the cost return toward the
per-file figure. This should be checked against real policy data before relying on it.

### 3.5 Redemption failures return 404, not 403

A 403 confirms that a bundle id exists. Since these ids are not treated as secrets, that
is an existence oracle worth closing at the same time.

### 3.6 Bundle lifetime stays decoupled from the source URLs

Bundle ids are **not** expired in step with the presigned URLs used to build them.

**Why:** the bundler exists so that the archive does not depend on the credentials that
produced it. Source URLs are consumed once, during the build; tying the artifact's
lifetime to them re-couples it to an input it deliberately does not depend on, and would
cap the window for resuming a large download at the source URL TTL.

## 4. What this does not decide

- **Whether to build the cache.** The decisions above make caching possible and safe.
  They do not establish that it is worth building. Byte-identical requests are a weak hit
  condition, and whether real usage produces them is unknown.
- **Cache granularity.** Caching whole archives only helps when whole requests repeat.
  Caching per-file fetches helps in proportion to overlap and does not require requests to
  match — but only if fetching, rather than compression, is the dominant cost. The bundler
  already records `archiveDurationMillis` and `uploadDurationMillis`; this is measurable
  and should be measured before choosing.
- **Where the manifest lives.** A cache needs an index of what each artifact contains, and
  an admission check reads the same data. The bundler already stores this
  (`BundleJobEntity` / `BundleSourceFile`) but does not expose it — `BundleResponse` omits
  the file list. Exposing it avoids the backend keeping a parallel copy; that is a
  cross-service contract change and should be decided deliberately.
- **How data access agreements are modelled.** Not selected for development.

## 5. Relationship to planned DAA work

A data access agreement, once formally instantiated as a policy set, is the natural unit
for a warm cache: users bound by the same agreement make similar — though rarely
identical — requests under it.

This is recorded because it constrained the decisions above, not as a commitment to build
it. Specifically, it is why entitlement is not treated as a per-user property anywhere in
this design. Schemes that key identity or cache entries on the requester or the
requester's grants were rejected on that basis: they would have to be removed once
entitlement becomes an agreement-level concept.

Nothing here requires DAAs to exist, and nothing here specifies them.

## 6. Relationship to INN-268

`INN-268` ("The temporary bucket `bundle` is exposed by a permissive `.*` casbin policy")
is a policy-data problem: a stored rule grants too much. This is a missing check —
policy is not consulted on these routes at all, so tightening that rule does not affect
it. The two are independent.

## 7. Open questions

1. Is the dominant bundling cost fetching or compression? Decides cache granularity, and
   is measurable today from the bundler's existing timing fields.
2. What do real policy rows look like — coarse folder grants, or fine-grained per-file?
   Decides whether folder deduplication holds at scale.
3. Should the bundler expose its manifest, or should the backend keep its own?
4. Is 168-hour bundle retention deliberate, and what does it exist to support?
