# Resumable transfer client

A transfer that survives being interrupted.

Reads a manifest of presigned URLs, downloads every entry, and resumes any file
already partially on disk. Kill it, run it again, and it picks up where it
stopped instead of starting over.

## Why this exists

The platform is already out of the data path — clients fetch objects directly
from storage, so the platform issues references rather than moving bytes. What
was missing is a client that survives interruption. Everything today downloads
whole files and restarts from zero on failure, which is why closing a laptop
kills a transfer.

That gap is what a server-side bundler was compensating for. But a bundler must
run *inside* the network holding the data and touch every byte — a server to
provision, patch, credential and security-review at every site. For a 100 GB
imaging study leaving a hospital, that administrative cost is the blocker, not
the bandwidth.

If the client can resume, the bundler has no job left to do.

## Run it

```bash
# 1. Mint a fresh manifest (presigned URLs expire; regenerate before each run)
cd workstreams/data-transfer/transfer-benchmark
.venv/bin/python setup/make_manifest.py A 7200

# 2. Start the transfer, then interrupt it mid-file with ^C
python3 protocol/client/fetch.py \
    workstreams/data-transfer/transfer-benchmark/client/manifest-A.json \
    --dest /tmp/xfer --verbose

# 3. Run the identical command again — it resumes
```

Run 2 leaves partial files. Run 3 reports a non-zero resume offset per file and
finishes. Final sizes match the manifest exactly.

Cell A (10 × 100 MB) is the fixture that matters: it is the only one where an
interrupt lands *mid-file*. Cells B/C/D have smaller files, so a kill lands
between them — that exercises manifest-level resume but not byte-level resume.

## Options

| flag | meaning |
|---|---|
| `--dest DIR` | destination directory (required) |
| `--workers N` | concurrent transfers, default 8 (matches the benchmark harness) |
| `--verbose` | per-file progress, including resume offsets |

| env | meaning |
|---|---|
| `XFER_MINIO_HOST` | remap the hostname the URL is signed against, e.g. `127.0.0.1` |
| `XFER_MINIO_NAME` | the name to remap, default `minio` |

A presigned URL's signature covers its hostname, so a URL signed against
`minio:9000` cannot be rewritten to reach storage from the host — that breaks the
signature. `XFER_MINIO_HOST` remaps the name at the socket layer instead, leaving
the URL byte-identical. Manifests from `make_manifest.py` are signed against
`localhost:9000` and need no remap; backend-minted ones do.

## How resume works

Partial files *are* the state. Resume offset comes from `os.path.getsize()`, so
there is no sidecar state file to corrupt or desync, and an interrupt at any
moment leaves something valid to continue from.

Per file:

1. If the file is already the size the manifest claims, skip it. A rerun costs
   only the unfinished tail.
2. Otherwise send `Range: bytes=<size-on-disk>-` and append the response.
3. `206 Partial Content` means the resume took. `200` means the server ignored
   the range, so the file is truncated and refetched rather than appending a
   second copy.
4. More bytes on disk than the manifest expects means the local file is not what
   the manifest describes — it is discarded and refetched.
5. Transient failures retry with exponential backoff, resuming from whatever
   reached disk. A dropped connection costs only the outstanding bytes.

MinIO honours `Range` on presigned GETs — verified: `206`, with
`Content-Range: bytes 100-199/104857600` and `Accept-Ranges: bytes`. No backend
change was needed for any of this.

## What "verify" means here

**Byte counts, not checksums.** Every file is checked against the size in the
manifest and against the total in `Content-Range`, and the run fails loudly on a
mismatch.

Checksum verification is deliberately *not* claimed. Cell A's etags carry a
multipart suffix (`2cf28998336b5f0e17536517824d1937-7`): an S3 multipart etag is
the MD5 of concatenated part MD5s, not the MD5 of the object, and the part size
used at upload is recorded nowhere. Hashing 100 MB and comparing would fail every
time on exactly the files that matter most. Cells B/C/D carry plain MD5s and
could be hashed, but a verification path that works on three fixtures out of four
is worse than an honest byte check.

This matches how `bundle-design/DESIGN.md` §3.3 actually uses etags — detecting
that content *changed*, not proving what it is. Real end-to-end checksums remain
an open question, not a blocker.

## Scope

Egress only. No uploads, no backend changes, no manifest format changes, no
authority field, no audit — those are the recorded direction in
`workstreams/data-transfer/STATUS.md`, not this build.

The manifest format is the one `make_manifest.py` already produces:

```json
{"cell": "A", "count": 10, "totalBytes": 1048576000, "ttlSeconds": 7200,
 "entries": [{"url": "...", "relativePath": "sub0/f0.bin",
              "size": 104857600, "etag": "2cf28998...-7"}]}
```
