#!/usr/bin/env python3
"""
Resumable manifest transfer client.

Reads a manifest of presigned URLs and downloads every entry, resuming any file
that is already partially on disk. Interrupt it and run it again: it picks up
where it stopped rather than starting over.

That property is the whole point. The platform never touches the bytes -- it
only issues the references -- so nothing needs to be installed inside the
network holding the data. A transfer that survives interruption is what makes
an unattended 100 GB move possible without a server in the middle.

Manifest format is the one produced by transfer-benchmark/setup/make_manifest.py:

    {"cell":..., "count":..., "totalBytes":..., "ttlSeconds":...,
     "entries": [{"url":..., "relativePath":..., "size":..., "etag":...}]}

Usage:
    python3 fetch.py <manifest.json> --dest <dir> [--workers 8] [--verbose]

Environment:
    XFER_MINIO_HOST   remap the hostname a presigned URL is signed against
                      (e.g. 127.0.0.1) without rewriting the URL, which would
                      break its S3v4 signature. Same trick as headtohead2.py.
"""
import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Read in 1 MiB blocks: large enough that syscall overhead is negligible against
# a 100 MB object, small enough that an interrupt loses almost nothing.
CHUNK = 1024 * 1024

CONNECT_TIMEOUT = 30
MAX_ATTEMPTS = 5
BACKOFF_BASE = 0.5

# 408 and 429 are explicitly retryable; 5xx are transient by definition. Every
# other 4xx means the request itself is wrong (expired signature, denied, gone),
# so retrying it just burns the clock.
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def install_host_remap():
    """Point a hostname at another address for this process only.

    A presigned URL's signature covers the host, so the URL cannot be rewritten
    to reach storage from somewhere its hostname does not resolve. Remapping the
    name at the socket layer leaves the URL byte-identical. Adapted from
    transfer-benchmark/server/headtohead2.py.

    Set XFER_MINIO_HOST=<addr>, optionally XFER_MINIO_NAME=<name> (default
    "minio").
    """
    target = os.getenv("XFER_MINIO_HOST")
    if not target:
        return False
    name = os.getenv("XFER_MINIO_NAME", "minio")
    original = socket.getaddrinfo

    def getaddrinfo(host, port, *args, **kwargs):
        if host == name:
            host = target
        return original(host, port, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    log(f"host remap: {name} -> {target}")
    return True


class PermanentError(Exception):
    """Retrying will not help: the request is wrong, not unlucky."""


def _open(url, offset):
    """GET url, starting at offset. Returns (response, total_size, resumed).

    total_size is the object's full length, taken from Content-Range when the
    server honours the range and Content-Length when it does not.
    """
    req = urllib.request.Request(url)
    if offset:
        req.add_header("Range", f"bytes={offset}-")

    try:
        resp = urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code in RETRYABLE_STATUS:
            raise IOError(f"HTTP {e.code}")
        raise PermanentError(f"HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise IOError(f"{type(e.reason).__name__}: {e.reason}")

    status = resp.status

    if offset and status == 206:
        # bytes <start>-<end>/<total>
        cr = resp.headers.get("Content-Range", "")
        total = int(cr.rsplit("/", 1)[1]) if "/" in cr else None
        return resp, total, True

    if offset and status == 200:
        # Server ignored the Range header and is sending the whole object.
        # Truncate and take it from the top rather than appending a second copy.
        cl = resp.headers.get("Content-Length")
        return resp, int(cl) if cl else None, False

    cl = resp.headers.get("Content-Length")
    return resp, int(cl) if cl else None, False


def fetch_one(entry, dest, verbose=False):
    """Download one entry, resuming if a partial file is already present.

    Returns a dict describing what happened. Raises on unrecoverable failure.
    """
    rel = entry["relativePath"]
    expected = entry.get("size")
    path = Path(dest) / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    # A complete file is left alone. This is what makes a rerun cheap: only the
    # unfinished tail of the transfer costs anything.
    if expected is not None and path.exists() and path.stat().st_size == expected:
        if verbose:
            log(f"  skip     {rel} (complete)")
        return {"path": rel, "status": "skipped", "bytes": 0, "resumed_at": None}

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        offset = path.stat().st_size if path.exists() else 0

        # More bytes on disk than the manifest claims means the local file is
        # not what the manifest describes. Start it over rather than appending
        # to something unknown.
        if expected is not None and offset > expected:
            log(f"  reset    {rel} (local {offset} > expected {expected})")
            path.unlink()
            offset = 0

        try:
            resp, total, resumed = _open(entry["url"], offset)
        except PermanentError:
            raise
        except IOError as e:
            last_error = e
            if attempt < MAX_ATTEMPTS:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                log(f"  retry {attempt}/{MAX_ATTEMPTS - 1} {rel}: {e} (in {delay:.1f}s)")
                time.sleep(delay)
                continue
            raise

        if not resumed:
            offset = 0

        if total is not None and expected is not None and total != expected:
            resp.close()
            raise PermanentError(
                f"size mismatch: server says {total}, manifest says {expected}"
            )

        mode = "ab" if resumed else "wb"
        if resumed and verbose:
            pct = (offset / expected * 100) if expected else 0
            log(f"  resume   {rel} at {offset:,} bytes ({pct:.1f}%)")
        elif offset and not resumed:
            log(f"  restart  {rel} (server ignored Range)")

        written = 0
        try:
            with open(path, mode) as fh, resp:
                while True:
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    written += len(block)
        except (IOError, urllib.error.URLError) as e:
            # Whatever landed on disk stays there; the next attempt resumes from
            # it. A dropped connection costs only the bytes still outstanding.
            last_error = e
            if attempt < MAX_ATTEMPTS:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                log(f"  retry {attempt}/{MAX_ATTEMPTS - 1} {rel}: {e} (in {delay:.1f}s)")
                time.sleep(delay)
                continue
            raise

        final = path.stat().st_size
        if expected is not None and final != expected:
            last_error = IOError(f"short read: {final} of {expected}")
            if attempt < MAX_ATTEMPTS:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                log(f"  retry {attempt}/{MAX_ATTEMPTS - 1} {rel}: {last_error} (in {delay:.1f}s)")
                time.sleep(delay)
                continue
            raise last_error

        return {
            "path": rel,
            "status": "resumed" if resumed else "fetched",
            "bytes": written,
            "resumed_at": offset if resumed else None,
        }

    raise last_error or IOError("exhausted attempts")


def main():
    ap = argparse.ArgumentParser(
        description="Resumable manifest transfer client.",
        epilog="Interrupt with ^C and run again; it resumes where it stopped.",
    )
    ap.add_argument("manifest", help="manifest JSON produced by make_manifest.py")
    ap.add_argument("--dest", required=True, help="destination directory")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent transfers (default 8, matching the benchmark harness)")
    ap.add_argument("--verbose", action="store_true", help="per-file progress")
    args = ap.parse_args()

    install_host_remap()

    manifest = json.loads(Path(args.manifest).read_text())
    entries = manifest.get("entries", [])
    if not entries:
        print("manifest has no entries", file=sys.stderr)
        return 2

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    total_bytes = manifest.get("totalBytes") or sum(e.get("size") or 0 for e in entries)

    # Bytes already on disk, so the run reports what it actually transferred
    # rather than what the manifest describes.
    already = 0
    for e in entries:
        p = dest / e["relativePath"]
        if p.exists():
            already += min(p.stat().st_size, e.get("size") or p.stat().st_size)

    log(f"manifest {args.manifest}: {len(entries)} entries, {total_bytes / 1048576:.0f} MB")
    log(f"dest {dest}  workers {args.workers}")
    if already:
        log(f"already on disk: {already / 1048576:.0f} MB ({already / total_bytes * 100:.1f}%)")

    t0 = time.perf_counter()
    results, failures = [], []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, e, dest, args.verbose): e for e in entries}
        try:
            for fut in as_completed(futures):
                entry = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as exc:
                    failures.append((entry["relativePath"], exc))
                    log(f"  FAILED   {entry['relativePath']}: {exc}")
        except KeyboardInterrupt:
            # Cancel what has not started; in-flight writes keep whatever they
            # have already flushed, which is exactly what the next run resumes
            # from. Partial files are the state -- there is nothing else to save.
            log("\ninterrupted -- partial files kept; run again to resume")
            for f in futures:
                f.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            return 130

    elapsed = time.perf_counter() - t0
    moved = sum(r["bytes"] for r in results)
    resumed = [r for r in results if r["status"] == "resumed"]
    skipped = [r for r in results if r["status"] == "skipped"]

    log("")
    log(f"transferred {moved / 1048576:.0f} MB in {elapsed:.1f}s"
        + (f" ({moved / 1048576 / elapsed:.0f} MB/s)" if elapsed > 0 and moved else ""))
    log(f"  fetched {len(results) - len(resumed) - len(skipped)}"
        f"  resumed {len(resumed)}  already-complete {len(skipped)}  failed {len(failures)}")

    if resumed:
        for r in resumed[:5]:
            log(f"  resumed {r['path']} from {r['resumed_at']:,} bytes")
        if len(resumed) > 5:
            log(f"  ... and {len(resumed) - 5} more")

    # Verify against the manifest rather than trusting the loop above.
    incomplete = []
    for e in entries:
        p = dest / e["relativePath"]
        want = e.get("size")
        if want is None:
            continue
        got = p.stat().st_size if p.exists() else 0
        if got != want:
            incomplete.append((e["relativePath"], got, want))

    if incomplete:
        log(f"\nINCOMPLETE: {len(incomplete)} file(s) do not match the manifest")
        for rel, got, want in incomplete[:10]:
            log(f"  {rel}: {got:,} of {want:,}")
        return 1

    log(f"\nall {len(entries)} files match the manifest exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
