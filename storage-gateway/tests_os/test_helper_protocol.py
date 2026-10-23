"""
The helper's operations and protocol in detail: gaps found by mutation testing of app/helper.py,
app/broker.py and app/acl.py (TESTING-STRATEGY.md, layer 10). Linux and root only.
"""
import json
import os
import socket
import stat as stat_module
import struct
import sys
import time

import pytest
from fastapi import HTTPException

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("needs Linux and root", allow_module_level=True)

from app import acl  # noqa: E402
from tests_os.test_isolation import DATA_OWNER, NS, TRAVERSE, can_read, env, token, uid_of_only_link  # noqa: E402,F401


def raw(e, payload: bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(e["base"] / "helper.sock"))
        sock.sendall(payload)
        return json.loads(sock.recv(65536))


# --- protocol ---

@pytest.mark.parametrize("payload", [
    b"not json\n", b"[1, 2]\n", b'{"op": "nope", "token": "t", "path": "p"}\n',
    b'{"op": "open", "path": "p"}\n', b'{"op": "open", "token": 5, "path": "p"}\n',
    b'{"op": "commit", "token": "t", "path": "p"}\n',
])
def test_malformed_requests_get_400(env, payload):
    assert raw(env, payload) == {"ok": False, "status": 400}


@pytest.mark.parametrize("code", [400, 401, 403, 409])
def test_the_client_passes_the_helpers_status_through(env, code):
    path = {400: f"{NS}/study/../x", 409: f"{NS}/study"}.get(code, f"{NS}/study/a.nii.gz")
    tok = {401: "garbage", 403: token(f"{NS}/study/b.nii.gz", "write")}.get(code, token(path, "write"))
    with pytest.raises(HTTPException) as refused:
        pending = env["access"].begin_write(tok, path, None)
        pending.write(b"x")
        pending.commit()
    assert refused.value.status_code == code


# --- stat (the portal's metadata calls) ---

def test_stat_reports_the_file_without_granting_anything(env):
    f = env["data"] / "study" / "a.nii.gz"
    st = env["access"].stat(token(f"{NS}/study/a.nii.gz", "stat"), f"{NS}/study/a.nii.gz", None)
    real = os.stat(f)
    assert (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino) == (real.st_size, real.st_mtime_ns,
                                                                       real.st_ctime_ns, real.st_ino)
    assert env["helper"].ids.state["links"] == {}
    with pytest.raises(OSError):
        os.getxattr(f, acl.XATTR)


@pytest.mark.parametrize("path,op,status", [
    (f"{NS}/study/a.nii.gz", "read", 403),
    (f"{NS}/study/missing.bin", "stat", 404),
    (f"{NS}/study/link", "stat", 400),
])
def test_stat_refusals(env, path, op, status):
    (env["data"] / "study" / "link").symlink_to(env["outside"] / "secret.txt")
    with pytest.raises(HTTPException) as refused:
        env["access"].stat(token(path, op), path, None)
    assert refused.value.status_code == status


# --- uploads: commit and abort ---

def test_overwriting_reports_that_the_file_existed(env):
    path = f"{NS}/study/a.nii.gz"
    pending = env["access"].begin_write(token(path, "write"), path, None)
    pending.write(b"new")
    pending.commit()
    assert pending.existed is True
    assert (env["data"] / "study" / "a.nii.gz").read_bytes() == b"new"


def test_abort_removes_the_staging_file(env):
    path = f"{NS}/study/c.csv"
    t = token(path, "write")
    pending = env["access"].begin_write(t, path, None)
    uid = uid_of_only_link(env["helper"])
    staged = env["staging"] / str(uid) / pending.staging
    assert staged.exists() and os.stat(staged).st_uid == uid
    pending.abort()
    assert not staged.exists()
    assert not (env["data"] / "study" / "c.csv").exists()


@pytest.mark.parametrize("name,status", [("not-an-upload", 400), ("../../x", 400), (".upload-missing", 404)])
def test_commit_and_abort_only_touch_the_links_own_staging_files(env, name, status):
    path = f"{NS}/study/c.csv"
    t = token(path, "write")
    env["access"].begin_write(t, path, None)  # creates this link's staging folder
    for op in ("commit", "abort"):
        with pytest.raises(HTTPException) as refused:
            env["access"].call({"op": op, "token": t, "path": path, "staging": name})
        assert refused.value.status_code == status


def test_one_link_cannot_commit_another_links_upload(env):
    path = f"{NS}/study/c.csv"
    first = env["access"].begin_write(token(path, "write"), path, None)
    first.write(b"mine")
    os.fsync(first.fd)
    other = token(path, "write")  # a different link for the same path
    env["access"].begin_write(other, path, None)
    with pytest.raises(HTTPException) as refused:
        env["access"].call({"op": "commit", "token": other, "path": path, "staging": first.staging})
    assert refused.value.status_code == 404
    assert not (env["data"] / "study" / "c.csv").exists()


def test_a_staging_file_owned_by_someone_else_is_refused(env):
    path = f"{NS}/study/c.csv"
    t = token(path, "write")
    pending = env["access"].begin_write(t, path, None)
    uid = uid_of_only_link(env["helper"])
    planted = env["staging"] / str(uid) / ".upload-planted"
    planted.write_bytes(b"not from this link")  # owned by root, not the link's ID
    with pytest.raises(HTTPException) as refused:
        env["access"].call({"op": "commit", "token": t, "path": path, "staging": ".upload-planted"})
    assert refused.value.status_code == 400
    pending.abort()


def test_a_symlinked_staging_folder_is_refused(env):
    path = f"{NS}/study/c.csv"
    t = token(path, "write")
    pending = env["access"].begin_write(t, path, None)
    uid = uid_of_only_link(env["helper"])
    folder = env["staging"] / str(uid)
    os.rename(folder, env["staging"] / "moved")
    folder.symlink_to(env["outside"])
    with pytest.raises(HTTPException) as refused:
        env["access"].call({"op": "abort", "token": t, "path": path, "staging": pending.staging})
    assert refused.value.status_code == 400


# --- expiry details ---

def test_quarantine_lasts_exactly_the_configured_time(env):
    os.close(env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read", ttl=60), f"{NS}/study/a.nii.gz", None)[0])
    uid = uid_of_only_link(env["helper"])
    now = time.time() + 120
    env["helper"].sweep(now=now)
    assert env["helper"].ids.state["quarantine"][str(uid)] == pytest.approx(now + 3600)


def test_expiry_removes_an_uploading_links_staging_folder(env):
    path = f"{NS}/study/c.csv"
    env["access"].begin_write(token(path, "write", ttl=60), path, None)
    uid = uid_of_only_link(env["helper"])
    assert (env["staging"] / str(uid)).is_dir()
    env["helper"].sweep(now=time.time() + 120)
    assert not (env["staging"] / str(uid)).exists()


def test_links_that_havent_expired_are_left_alone(env):
    os.close(env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read", ttl=600), f"{NS}/study/a.nii.gz", None)[0])
    uid = uid_of_only_link(env["helper"])
    assert env["helper"].sweep(now=time.time() + 60) == 0
    assert can_read(uid, env["data"] / "study" / "a.nii.gz", groups=[TRAVERSE])


def test_state_survives_a_restart_so_grants_are_still_revoked(env):
    from app.helper import Helper

    os.close(env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read", ttl=60), f"{NS}/study/a.nii.gz", None)[0])
    uid = uid_of_only_link(env["helper"])
    restarted = Helper(env["helper"].s, resolve_key=lambda t: None)
    assert restarted.sweep(now=time.time() + 120) == 1
    assert not can_read(uid, env["data"] / "study" / "a.nii.gz", groups=[TRAVERSE])


# --- ACL details ---

def test_a_grant_is_exactly_read_for_that_id_with_a_matching_mask(env):
    f = env["data"] / "study" / "a.nii.gz"
    fd = os.open(f, os.O_RDONLY)
    try:
        acl.grant_user(fd, 2_000_500, acl.READ)
        entries = acl.read(fd)
        assert (acl.USER, acl.READ, 2_000_500) in entries
        mask = next(perm for tag, perm, _ in entries if tag == acl.MASK)
        assert mask & acl.READ and not mask & acl.WRITE
        assert stat_module.S_IMODE(os.fstat(fd).st_mode) & 0o007 == 0  # still nothing for others
        acl.grant_user(fd, 2_000_500, acl.READ)  # granting twice keeps one entry
        assert sum(1 for tag, _, i in acl.read(fd) if tag == acl.USER and i == 2_000_500) == 1
        raw_acl = os.getxattr(fd, acl.XATTR)
        tags = [struct.unpack_from("<HHI", raw_acl, 4 + 8 * i)[0] for i in range((len(raw_acl) - 4) // 8)]
        assert tags == sorted(tags)  # the kernel requires sorted entries
    finally:
        acl.revoke_user(fd, 2_000_500)
        os.close(fd)
    assert os.stat(f).st_uid == DATA_OWNER
