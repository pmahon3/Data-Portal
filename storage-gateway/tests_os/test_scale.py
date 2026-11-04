"""
Load on the POSIX machine with an access broker (administrator access): many small files in one multi-file
download, where each file is granted and then opened by a new process running as the approval's
temporary ID, and several such downloads at once. The steps are the ones the file service takes for
``/v1/bundles`` (register the list, then stat and open each file through the broker, streaming the
ZIP as it goes, checking and opening files a batch at a time); only HTTP is left out.

The gate runs a few hundred files. For the full measurement:

    docker run --rm -v "$PWD/storage-gateway:/svc" -w /svc \\
      -e SCALE_FILES=10000 -e SCALE_CONCURRENCY=1,4,8,16 -e SCALE_REPORT=/svc/scale.json \\
      python:3.12-slim sh -c "pip install -q -r requirements-test.txt && python -m pytest tests_os/test_scale.py -q -s"

Verifies: PX-8, PX-14.
"""
import hashlib
import io
import json
import os
import sys
import threading
import time
import zipfile

import pytest

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("operating-system boundary tests need Linux and root", allow_module_level=True)

from app.file_access import BatchOpener  # noqa: E402
from app.config import OPEN_BATCH  # noqa: E402
from app.zipstream import Entry, ZipStream  # noqa: E402
from tests_os.test_isolation import DATA_OWNER, TRAVERSE, close_env, make_env, token  # noqa: E402
from tests.tokens import NS  # noqa: E402

FILES = int(os.getenv("SCALE_FILES", "300"))
CONCURRENCY = [int(n) for n in os.getenv("SCALE_CONCURRENCY", "1,8").split(",")]
SIZE = 1024  # a small file: the cost measured is per file, not per byte
RESULTS: dict = {"files": FILES, "file_size": SIZE}


def content(i: int) -> bytes:
    return (f"{i:08d}".encode() * (SIZE // 8))[:SIZE]


@pytest.fixture(scope="module")
def env():
    e = make_env(id_count=100)
    folder = e["data"] / "many"
    folder.mkdir()
    os.chown(folder, DATA_OWNER, TRAVERSE)
    os.chmod(folder, 0o710)
    for i in range(FILES):
        f = folder / f"{i:05d}.dat"
        f.write_bytes(content(i))
        os.chown(f, DATA_OWNER, DATA_OWNER)
        os.chmod(f, 0o600)
    yield e
    close_env(e)
    if os.getenv("SCALE_REPORT"):
        with open(os.environ["SCALE_REPORT"], "w") as out:
            json.dump(RESULTS, out, indent=2)
    print("\nscale:", json.dumps(RESULTS))


def download(env, grant: str, paths: list[str]) -> bytes:
    """One multi-file download, as ``download_bundle`` does it, returning the whole ZIP."""
    access, bundle = env["access"], f"{NS}/{grant}"
    listing = json.dumps({"folder_name": "", "paths": paths})
    tok = token(bundle, "bundle", ttl=3600, grant=grant, listing=hashlib.sha256(listing.encode()).hexdigest())
    access.register_bundle(tok, bundle, listing)
    stats = [st for i in range(0, len(paths), OPEN_BATCH) for st in access.stat_many(tok, paths[i:i + OPEN_BATCH], bundle)]
    opener = BatchOpener(access, tok, bundle, paths)
    entries = [Entry(path, st.st_size, st.st_mtime, lambda path=path: opener.open(path)) for path, st in zip(paths, stats)]
    with opener:
        return b"".join(ZipStream(entries).iter_bytes())


def paths(n: int) -> list[str]:
    return [f"{NS}/many/{i:05d}.dat" for i in range(n)]


def open_fds() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_many_small_files_in_one_download(env):
    """PX-14. Every file arrives intact, under one temporary ID, and nothing is left open."""
    before = open_fds()
    started = time.monotonic()
    archive = download(env, "scale-one", paths(FILES))
    elapsed = time.monotonic() - started
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = z.namelist()
        assert len(names) == FILES
        assert all(z.read(name) == content(i) for i, name in enumerate(names))
    assert len({link["uid"] for key, link in env["broker"].ids.state["links"].items() if "scale-one" in key}) == 1
    assert open_fds() <= before + 2  # the access broker's socket may be in use; no file stays open
    RESULTS["one_download"] = {"seconds": round(elapsed, 2), "files_per_second": round(FILES / elapsed, 1),
                               "ms_per_file": round(1000 * elapsed / FILES, 2)}


@pytest.mark.parametrize("downloads", CONCURRENCY)
def test_downloads_at_once(env, downloads):
    """PX-14. Several downloads at once all complete intact; record how throughput scales."""
    per_download = max(1, FILES // max(CONCURRENCY))
    results, errors = {}, []

    def run(k):
        try:
            results[k] = download(env, f"scale-{downloads}-{k}", paths(per_download))
        except Exception as e:  # noqa: BLE001 - reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(k,)) for k in range(downloads)]
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started
    assert not errors, errors[:3]
    for archive in results.values():
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert len(z.namelist()) == per_download and z.testzip() is None
    total = downloads * per_download
    RESULTS.setdefault("at_once", {})[downloads] = {
        "files_each": per_download, "seconds": round(elapsed, 2), "files_per_second": round(total / elapsed, 1)}


def test_a_burst_of_requests_is_queued_not_refused(env):
    """PX-14. Many requests reaching the access broker at once wait their turn; none fails as unavailable."""
    grant, files = "scale-burst", paths(64)
    listing = json.dumps({"folder_name": "", "paths": files})
    bundle = f"{NS}/{grant}"
    tok = token(bundle, "bundle", ttl=3600, grant=grant, listing=hashlib.sha256(listing.encode()).hexdigest())
    env["access"].register_bundle(tok, bundle, listing)
    errors, start = [], threading.Barrier(len(files))

    def read(path):
        start.wait()
        try:
            fd, _ = env["access"].open_read(tok, path, path.split("/")[1:], bundle=bundle)
            os.close(fd)
        except Exception as e:  # noqa: BLE001 - reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=read, args=(p,)) for p in files]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"{len(errors)} of {len(files)} refused: {errors[0]}"
