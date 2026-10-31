"""
A scanning session uploaded from the technician's browser to the POSIX machine, as the portal's
folder upload does it: one request plans the folder and signs a link per file, the browser sends 6
files at a time straight to the file service, and one request completes them all. A session is
usually thousands of small DICOM files, so the cost per file is what matters.

The gate runs a small session. For the full measurement, with the file service behind a link with
some latency (Toxiproxy; the hospital is off-site from the machine):

    SESSION_FILES=3000 SESSION_FILE_KB=512 SESSION_LATENCY_MS=5 SESSION_REPORT=session.json \\
      uv run --no-project --with pytest --with requests pytest e2e/test_upload_session.py -q -s

Verifies: PX-15. Accepts: UC-5.1.
"""
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from portal import BACKEND, NAMESPACE, TIMEOUT, data_read, root_id
from test_faults import proxy, toxic, via_proxy  # noqa: F401 - fixtures

FILES = int(os.getenv("SESSION_FILES", "200"))
FILE_KB = int(os.getenv("SESSION_FILE_KB", "64"))
LATENCY_MS = int(os.getenv("SESSION_LATENCY_MS", "0"))
BROWSER_CONCURRENCY = 6  # FOLDER_UPLOAD_CONCURRENCY in the frontend's asset_management/actions.js


def content(i: int) -> bytes:
    return (f"slice {i:05d} ".encode() * (FILE_KB * 1024 // 12 + 1))[:FILE_KB * 1024]


@pytest.fixture
def link(request):
    """How the browser reaches the file service: directly, or through added latency."""
    if not LATENCY_MS:
        return lambda url: url
    add = request.getfixturevalue("toxic")
    for stream in ("upstream", "downstream"):
        add("latency", stream=stream, latency=LATENCY_MS)
    return via_proxy


def test_a_scanning_session_uploads_as_a_folder(admin, instance, link):
    session = f"session-{uuid.uuid4().hex[:6]}"
    manifest = [{"relative_path": f"{session}/IM_{i:05d}.dcm", "content_type": "application/dicom",
                 "size": FILE_KB * 1024} for i in range(FILES)]
    timings = {}

    started = time.monotonic()
    init = requests.post(f"{BACKEND}/api/tree/folders/upload/init", headers=admin, timeout=300, json={
        "instance_name": instance, "bucket": NAMESPACE, "parent_id": root_id(admin, instance),
        "on_conflict": "error", "files": manifest})
    assert init.status_code == 200, init.text[:500]
    plan = init.json()["files"]
    assert len(plan) == FILES
    timings["plan_seconds"] = round(time.monotonic() - started, 2)

    def put(file_plan):
        i = int(file_plan["relative_path"].rsplit("_", 1)[1].split(".")[0])
        r = requests.put(link(file_plan["url"]), data=content(i), timeout=TIMEOUT)
        return r.status_code

    started = time.monotonic()
    with ThreadPoolExecutor(BROWSER_CONCURRENCY) as pool:
        codes = list(pool.map(put, plan))
    assert set(codes) <= {200, 201}, sorted(set(codes))
    timings["transfer_seconds"] = round(time.monotonic() - started, 2)

    started = time.monotonic()
    done = requests.post(f"{BACKEND}/api/tree/folders/upload/complete", headers=admin, timeout=300, json={
        "instance_name": instance, "file_ids": [f["file_id"] for f in plan]})
    assert done.status_code == 200, done.text[:500]
    assert not done.json().get("failed") and done.json()["completed"] == FILES
    timings["complete_seconds"] = round(time.monotonic() - started, 2)

    last = plan[-1]
    assert data_read(last["key"]) == content(int(last["relative_path"][-9:-4]))  # the bytes are on the machine

    total = sum(timings.values())
    report = {"files": FILES, "file_kb": FILE_KB, "latency_ms_each_way": LATENCY_MS, **timings,
              "total_seconds": round(total, 2), "ms_per_file": round(1000 * total / FILES, 1),
              "megabytes_per_second": round(FILES * FILE_KB / 1024 / timings["transfer_seconds"], 1)}
    if os.getenv("SESSION_REPORT"):
        with open(os.environ["SESSION_REPORT"], "w") as out:
            json.dump(report, out, indent=2)
    print("\nsession:", json.dumps(report))
