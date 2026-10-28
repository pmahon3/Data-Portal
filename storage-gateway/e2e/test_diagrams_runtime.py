"""
The checked sequence and deployment diagrams against the running local stack
(docs/diagrams/posix-sequences.md, posix-deployment.md).

Sequences: each test performs one operation through the portal, then reads what the backend, the
file service and the helper logged during it (docker's timestamps order lines across containers),
and compares that with the diagram's solid arrows, in the order the calls finish.
Deployment: the running container's processes, accounts, paths and socket match the diagram's labels.
Setup: see conftest.py.
"""
import re
import subprocess
import time
from datetime import datetime

import pytest
import requests

import doccheck
from portal import (BACKEND, GATEWAY_CONTAINER, NAMESPACE, TIMEOUT, delete_file, download_url, root_id,
                    unique_name, upload)

BACKEND_CONTAINER = "ams-backend-posix"
AUDIT_OP = {"read": "open", "write": "begin_write", "placed": "commit", "stat": "stat", "delete": "delete"}
IGNORED_PATHS = re.compile(r"^/(api/health|api/storage-links/jwks\.json|v1/health)")


def _ts(stamp: str) -> tuple[int, int]:
    seconds, _, frac = stamp.rstrip("Z").partition(".")
    return int(datetime.fromisoformat(seconds).timestamp()), int((frac + "000000000")[:9])


def events_since(since: float) -> list[tuple[str, str, str | None, int | None]]:
    """(participant, verb, path, status) for each logged call since ``since``, oldest first."""
    found = []
    for container in (BACKEND_CONTAINER, GATEWAY_CONTAINER):
        out = subprocess.run(["docker", "logs", "--timestamps", "--since", f"{since:.3f}", container],
                             capture_output=True, text=True)
        for line in (out.stdout + out.stderr).splitlines():
            stamp, _, text = line.partition(" ")
            if m := re.search(r'uvicorn\.access.*"(\w+) (\S+) HTTP/[\d.]+" (\d{3})', text):
                event = ("Backend", m.group(1), m.group(2).split("?")[0], int(m.group(3)))
            elif m := re.search(r"INFO:storage-gateway:(\w+) (\S+) (\d{3}) link=", text):
                event = ("FileService", m.group(1), m.group(2), int(m.group(3)))
            elif m := re.search(r"storage-gateway\.audit:(\w+) link=", text):
                if m.group(1) not in AUDIT_OP:
                    continue
                event = ("Helper", AUDIT_OP[m.group(1)], None, None)
            else:
                continue
            if event[2] and IGNORED_PATHS.match(event[2]):
                continue
            found.append((_ts(stamp), event))
    return [e for _, e in sorted(found, key=lambda x: x[0])]


def assert_matches_diagram(name: str, since: float):
    time.sleep(0.5)  # let the last lines reach the log
    expected = doccheck.completion_order(doccheck.sequence_messages(doccheck.block("diagrams/posix-sequences.md", name)))
    observed = events_since(since)
    assert len(observed) == len(expected), f"{name}: expected {len(expected)} calls, saw {observed}"
    for message, (participant, verb, path, status) in zip(expected, observed):
        want_verb, path_pattern, want_status = doccheck.message_pattern(message.text)
        assert participant == message.receiver, (name, message, (participant, verb, path, status))
        assert verb == want_verb, (name, message, verb)
        if path_pattern is not None:
            assert path is not None and path_pattern.fullmatch(path), (name, message, path)
        if want_status is not None:
            assert status == want_status, (name, message, status)


def test_download_sequence(admin, instance):
    file_id, _ = upload(admin, instance, unique_name(), b"diagram download")
    since = time.time()
    url = download_url(admin, instance, file_id).json()["url"]
    assert requests.get(url, timeout=TIMEOUT).content == b"diagram download"
    assert_matches_diagram("download", since)
    delete_file(admin, instance, file_id)


def test_resume_sequence(admin, instance):
    file_id, _ = upload(admin, instance, unique_name(), b"0123456789" * 100)
    url = download_url(admin, instance, file_id).json()["url"]
    since = time.time()
    first = requests.get(url, timeout=TIMEOUT)
    rest = requests.get(url, headers={"Range": "bytes=500-", "If-Range": first.headers["etag"]}, timeout=TIMEOUT)
    assert rest.status_code == 206
    assert_matches_diagram("resume", since)
    delete_file(admin, instance, file_id)


def test_upload_sequence(admin, instance):
    folder = root_id(admin, instance)
    since = time.time()
    init = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=admin, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": NAMESPACE, "folder_id": folder,
        "filename": unique_name(".csv"), "content_type": "text/csv"}).json()
    assert requests.put(init["url"], data=b"a,b\n", timeout=TIMEOUT).status_code == 201
    assert requests.post(f"{BACKEND}/api/tree/files/upload/complete", headers=admin, timeout=TIMEOUT,
                         json={"instance_name": instance, "file_id": init["file_id"]}).status_code == 200
    assert_matches_diagram("upload", since)
    delete_file(admin, instance, init["file_id"])


def test_delete_sequence(admin, instance):
    file_id, _ = upload(admin, instance, unique_name(), b"to delete")
    since = time.time()
    assert delete_file(admin, instance, file_id).status_code == 200
    assert_matches_diagram("delete", since)


# --- deployment ---

def _in_container(*command):
    return subprocess.run(["docker", "exec", GATEWAY_CONTAINER, *command], capture_output=True, text=True).stdout


def processes():
    """[(cmdline, real uid, effective uid, supplementary groups)] in the file service container."""
    script = ('for p in /proc/[0-9]*; do c=$(tr "\\0" " " < $p/cmdline 2>/dev/null); [ -n "$c" ] || continue; '
              'echo "$(awk \'/^Uid:/{print $2, $3}\' $p/status)|$(awk \'/^Groups:/{$1=""; print}\' $p/status)|$c"; done')
    rows = []
    for line in _in_container("sh", "-c", script).splitlines():
        uids, groups, cmd = line.split("|", 2)
        real, effective = (int(x) for x in uids.split())
        rows.append((cmd, real, effective, groups.split()))
    return rows


def test_deployment_matches_the_running_container():
    labels = doccheck.flowchart_nodes(doccheck.block("diagrams/posix-deployment.md", "deployment")).values()
    running = processes()
    checked = 0
    for label in labels:
        if m := re.search(r"process (\S+) · uid (\d+)", label):
            name, uid = m.group(1), int(m.group(2))
            matches = [p for p in running if name in p[0] and "sh -c" not in p[0]]
            assert matches, f"no process {name!r} running"
            for cmd, real, effective, groups in matches:
                assert (real, effective) == (uid, uid), (cmd, real, effective)
                if "groups none" in label:
                    assert groups == [], (cmd, groups)
            checked += 1
        if m := re.search(r"(?:path|socket) (\S+) · mode (\d{4}) · owner (\d+):(\d+)", label):
            path, mode, uid, gid = m.groups()
            actual = _in_container("stat", "-c", "%a %u %g", path).split()
            assert actual == [mode.lstrip("0") or "0", uid, gid], (path, actual)
            checked += 1
        if m := re.search(r"port (\d+)", label):
            assert requests.get(f"http://localhost:{m.group(1)}/v1/health", timeout=TIMEOUT).ok
    assert checked >= 6


def test_temporary_ids_come_from_the_documented_range(admin, instance):
    file_id, _ = upload(admin, instance, unique_name(), b"x")
    requests.get(download_url(admin, instance, file_id).json()["url"], timeout=TIMEOUT)
    label = next(l for l in doccheck.flowchart_nodes(doccheck.block("diagrams/posix-deployment.md", "deployment")).values()
                 if l.startswith("Opener"))
    start = int(re.search(r"uid from (\d+)", label).group(1))
    state = _in_container("cat", "/srv/posix/.helper/state.json")
    uids = [int(u) for u in re.findall(r'"uid": (\d+)', state)]
    assert uids and all(u >= start for u in uids)
    delete_file(admin, instance, file_id)
