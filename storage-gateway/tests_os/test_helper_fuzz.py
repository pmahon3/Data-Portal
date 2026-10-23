"""
Fuzzing the privileged helper's socket protocol (TESTING-STRATEGY.md, layer 6, for the helper).

Random sequences of requests (every operation, valid and invalid tokens, hostile paths and staging
names) are sent over the real socket. Whatever happens:
- the helper answers every request and never crashes;
- nothing outside the data root is granted, opened, written or removed;
- after a final sweep, every file in the tree has no ACL and its original mode, and every ID is
  quarantined or retired, never still held.
Linux and root only (see test_isolation.py).
"""
import json
import os
import socket
import sys
import time
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("needs Linux and root", allow_module_level=True)

from app import acl  # noqa: E402
from tests_os.test_isolation import NS, close_env, make_env, token  # noqa: E402

PATHS = st.sampled_from([
    f"{NS}/study/a.nii.gz", f"{NS}/study/b.nii.gz", f"{NS}/study/missing.txt", f"{NS}/study/link",
    f"{NS}/new/up.csv", f"{NS}/study", f"{NS}/../outside/secret.txt", f"{NS}/study/../../outside/secret.txt",
    "other/x", f"{NS}/", f"{NS}/study/a.nii.gz/inner", f"{NS}/\x00", "",
])
OPS = st.sampled_from(["open", "stat", "begin_write", "commit", "abort", "delete", "bogus"])
OP_FOR = {"open": "read", "stat": "stat", "begin_write": "write", "commit": "write", "abort": "write", "delete": "delete"}
STAGING = st.sampled_from([".upload-x", "../../outside/secret.txt", ".upload-../../x", "plain", "", ".upload-"])


@st.composite
def requests(draw):
    op, path = draw(OPS), draw(PATHS)
    kind = draw(st.sampled_from(["valid", "valid", "other-op", "expired", "garbage", "other-path"]))
    if kind == "valid":
        tok = token(path, OP_FOR.get(op, "read"))
    elif kind == "other-op":
        tok = token(path, draw(st.sampled_from(["read", "write", "stat", "delete"])))
    elif kind == "expired":
        tok = token(path, OP_FOR.get(op, "read"), ttl=-5)
    elif kind == "other-path":
        tok = token(draw(PATHS), OP_FOR.get(op, "read"))
    else:
        tok = draw(st.text(max_size=40))
    request = {"op": op, "token": tok, "path": path}
    if op in ("commit", "abort"):
        request["staging"] = draw(STAGING)
    if draw(st.booleans()) and draw(st.booleans()):
        request.pop(draw(st.sampled_from(sorted(request))))  # malformed: a field missing
    return request


def send(socket_path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(socket_path)
        sock.sendall(json.dumps(request).encode() + b"\n")
        message, fds, _, _ = socket.recv_fds(sock, 1 << 16, 8)
    for fd in fds:
        os.close(fd)
    return json.loads(message)


@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
@given(batch=st.lists(requests(), min_size=1, max_size=15))
def test_any_request_sequence_leaves_the_tree_clean(batch):
    e = make_env(sweep_seconds=3600)
    try:
        (e["data"] / "study" / "link").symlink_to(e["outside"] / "secret.txt")
        before = {p: os.lstat(p).st_mode for p in e["data"].rglob("*") if not p.is_symlink()}
        for request in batch:
            reply = send(str(e["base"] / "helper.sock"), request)
            assert isinstance(reply, dict) and "ok" in reply
            assert reply.get("status") != 500 or request.get("op") in ("commit",), (request, reply)

        assert (e["outside"] / "secret.txt").read_bytes() == b"SECRET"
        with pytest.raises(OSError):
            os.getxattr(e["outside"] / "secret.txt", acl.XATTR)

        e["helper"].sweep(now=time.time() + 10_000)
        assert e["helper"].ids.state["links"] == {}
        for p in e["data"].rglob("*"):
            if p.is_symlink() or not p.is_file():
                continue
            with pytest.raises(OSError):
                os.getxattr(p, acl.XATTR)
            if p in before:
                assert os.lstat(p).st_mode == before[p]
        assert not list(e["staging"].iterdir())
    finally:
        close_env(e)
