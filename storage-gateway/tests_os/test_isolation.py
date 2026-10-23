"""
The operating-system boundary (decisions of 2026-10-23): each approved link gets a temporary user ID,
and only that ID can read the link's file; the web service can't read the data at all.

These tests need Linux, root, and a filesystem with POSIX ACLs. Run them in a container:

    docker run --rm -v "$PWD/storage-gateway:/svc" -w /svc python:3.12-slim sh -c \\
      "pip install -q -r requirements-test.txt && python -m pytest tests_os -q"

The first test checks the filesystem enforces permissions at all, so a mount that ignores them fails
loudly instead of letting every other test pass for the wrong reason.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("operating-system boundary tests need Linux and root", allow_module_level=True)

from app import acl  # noqa: E402
from app.broker import HelperAccess  # noqa: E402
from app.helper import CANARY, HelperSettings, serve  # noqa: E402

NS = "inn-posix"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
WEB, DATA_OWNER, TRAVERSE, STRANGER = 10001, 10002, 10010, 50000
SERVICE = str(Path(__file__).resolve().parents[1])


def token(path, op, ttl=300):
    now = int(time.time())
    return jwt.encode({"iss": "inn-portal", "aud": NS, "jti": uuid.uuid4().hex, "iat": now, "exp": now + ttl,
                       "op": op, "path": path}, KEY, algorithm="RS256")


def as_user(uid, code, groups=()):
    """Run Python as ``uid``; returns (returncode, stdout)."""
    r = subprocess.run([sys.executable, "-c", code], user=uid, group=uid, extra_groups=list(groups),
                       capture_output=True, text=True, cwd="/")
    return r.returncode, (r.stdout + r.stderr).strip()


def can_read(uid, path, groups=()):
    return as_user(uid, f"open({str(path)!r}, 'rb').read()", groups)[0] == 0


def make_env(**overrides):
    base = Path("/srv") / f"osb-{uuid.uuid4().hex[:8]}"
    data, staging, outside = base / "data", base / "staging", base / "outside"
    for d in (base, data, staging, outside, data / "study"):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o755)
    for d in (data, data / "study"):
        os.chown(d, DATA_OWNER, TRAVERSE)
        os.chmod(d, 0o710)
    os.chmod(staging, 0o711)
    for name in ("a.nii.gz", "b.nii.gz"):
        f = data / "study" / name
        f.write_bytes(name.encode() * 100)
        os.chown(f, DATA_OWNER, DATA_OWNER)
        os.chmod(f, 0o600)
    (outside / "secret.txt").write_bytes(b"SECRET")
    options = dict(socket_path=str(base / "helper.sock"), data_root=data, staging_root=staging,
                   state_file=base / "state.json", namespace=NS, jwks_url="unused",
                   client_uids={0, WEB}, id_start=2_000_000, id_count=1000, traverse_gid=TRAVERSE,
                   data_uid=DATA_OWNER, data_gid=DATA_OWNER, quarantine_seconds=3600, sweep_seconds=3600)
    s = HelperSettings(**(options | overrides))
    helper, server = serve(s, resolve_key=lambda t: KEY.public_key(), socket_mode=0o666)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return {"base": base, "data": data, "staging": staging, "outside": outside, "helper": helper,
            "access": HelperAccess(s.socket_path), "server": server}


def close_env(e):
    e["server"].shutdown()
    e["server"].server_close()
    shutil.rmtree(e["base"])


@pytest.fixture
def env():
    e = make_env()
    yield e
    close_env(e)


@pytest.fixture
def small_env():
    """Two IDs, no quarantine: an ID is reused as soon as it's released."""
    e = make_env(id_count=2, quarantine_seconds=0)
    yield e
    close_env(e)


def uid_of_only_link(helper):
    (link,) = helper.ids.state["links"].values()
    return link["uid"]


def read_fd(fd):
    data = os.read(fd, 1 << 20)
    os.close(fd)
    return data


# --- the ground the boundary stands on ---

def test_the_filesystem_enforces_permissions(env):
    assert not can_read(STRANGER, env["data"] / "study" / "a.nii.gz")


def test_the_web_service_user_cannot_read_or_list_the_data(env):
    assert not can_read(WEB, env["data"] / "study" / "a.nii.gz")
    assert not can_read(WEB, env["data"] / CANARY)
    assert as_user(WEB, f"import os; os.listdir({str(env['data'])!r})")[0] != 0


def test_the_web_service_starts_only_when_it_cannot_read_the_data(env):
    code = (f"import sys; sys.path.insert(0, {SERVICE!r}); from pathlib import Path; "
            "from app.config import Settings; from app.main import create_app; "
            f"create_app(Settings(root=Path({str(env['data'])!r}), namespace='{NS}', jwks_url='unused', "
            f"helper_socket={str(env['base'] / 'helper.sock')!r}), resolve_key=lambda t: None); print('started')")
    assert as_user(WEB, code)[1].endswith("started")
    returncode, output = as_user(0, code)  # root can read the data: must refuse to start
    assert returncode != 0 and "refusing to start" in output


# --- reads: the link's ID, and only it, can read the file ---

def test_a_link_reads_its_file_through_the_helper(env):
    fd, _ = env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read"), f"{NS}/study/a.nii.gz", None)
    assert read_fd(fd) == b"a.nii.gz" * 100


def test_the_links_id_can_read_its_file_and_nothing_else(env):
    fd, _ = env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read"), f"{NS}/study/a.nii.gz", None)
    os.close(fd)
    uid = uid_of_only_link(env["helper"])
    assert can_read(uid, env["data"] / "study" / "a.nii.gz", groups=[TRAVERSE])
    assert not can_read(uid, env["data"] / "study" / "b.nii.gz", groups=[TRAVERSE])
    assert as_user(uid, f"import os; os.listdir({str(env['data'] / 'study')!r})", groups=[TRAVERSE])[0] != 0
    assert not can_read(uid, env["data"] / "study" / "a.nii.gz")  # without the traverse group, not even that


def test_two_links_get_two_ids(env):
    for _ in range(2):
        fd, _ = env["access"].open_read(token(f"{NS}/study/a.nii.gz", "read"), f"{NS}/study/a.nii.gz", None)
        os.close(fd)
    uids = {link["uid"] for link in env["helper"].ids.state["links"].values()}
    assert len(uids) == 2


@pytest.mark.parametrize("make_token,status", [
    (lambda: token(f"{NS}/study/b.nii.gz", "read"), 403),            # issued for another file
    (lambda: token(f"{NS}/study/a.nii.gz", "write"), 403),           # issued for another operation
    (lambda: token(f"{NS}/study/a.nii.gz", "read", ttl=-5), 401),    # expired
    (lambda: "not-a-token", 401),
])
def test_the_helper_checks_every_token_itself(env, make_token, status):
    with pytest.raises(HTTPException) as refused:
        env["access"].open_read(make_token(), f"{NS}/study/a.nii.gz", None)
    assert refused.value.status_code == status
    assert env["helper"].ids.state["links"] == {} or status == 403


def test_symlinks_are_never_granted(env):
    (env["data"] / "study" / "link").symlink_to(env["outside"] / "secret.txt")
    with pytest.raises(HTTPException) as refused:
        env["access"].open_read(token(f"{NS}/study/link", "read"), f"{NS}/study/link", None)
    assert refused.value.status_code == 400
    with pytest.raises(OSError):
        os.getxattr(env["outside"] / "secret.txt", acl.XATTR)


def test_clients_other_than_the_web_service_are_refused(env):
    code = (f"import sys; sys.path.insert(0, {SERVICE!r}); from app.broker import HelperAccess; "
            f"HelperAccess({str(env['base'] / 'helper.sock')!r}).call({{'op': 'stat', 'token': 'x', 'path': 'y'}})")
    returncode, output = as_user(STRANGER, code)
    assert returncode != 0 and "403" in output


def test_an_unreachable_helper_fails_closed(env):
    with pytest.raises(HTTPException) as refused:
        HelperAccess(str(env["base"] / "missing.sock")).open_read("t", f"{NS}/study/a.nii.gz", None)
    assert refused.value.status_code == 503


# --- expiry ---

def test_expiry_revokes_access_and_restores_the_file_exactly(env):
    f = env["data"] / "study" / "a.nii.gz"
    before = os.stat(f)
    t = token(f"{NS}/study/a.nii.gz", "read", ttl=60)
    fd, _ = env["access"].open_read(t, f"{NS}/study/a.nii.gz", None)
    uid = uid_of_only_link(env["helper"])
    assert can_read(uid, f, groups=[TRAVERSE])

    assert env["helper"].sweep(now=time.time() + 120) == 1
    assert not can_read(uid, f, groups=[TRAVERSE])
    with pytest.raises(OSError):
        os.getxattr(f, acl.XATTR)
    assert os.stat(f).st_mode == before.st_mode
    assert str(uid) in env["helper"].ids.state["quarantine"]
    assert read_fd(fd) == b"a.nii.gz" * 100  # a download already running finishes


# --- uploads: staged as the link's ID, placed by the helper ---

def upload(env, path, content):
    t = token(path, "write")
    pending = env["access"].begin_write(t, path, None)
    pending.write(content)
    return pending.commit(), pending


def test_an_upload_is_placed_and_given_to_the_data_owner(env):
    upload(env, f"{NS}/new/deep/result.csv", b"a,b\n1,2\n")
    f = env["data"] / "new" / "deep" / "result.csv"
    st_ = os.stat(f)
    assert f.read_bytes() == b"a,b\n1,2\n"
    assert (st_.st_uid, st_.st_mode & 0o777) == (DATA_OWNER, 0o600)
    for d in (env["data"] / "new", env["data"] / "new" / "deep"):
        assert (os.stat(d).st_uid, os.stat(d).st_gid, os.stat(d).st_mode & 0o777) == (DATA_OWNER, TRAVERSE, 0o710)
    assert not any(env["staging"].rglob(".upload-*"))


def test_an_uploading_id_cannot_write_delete_or_replace_in_the_data_tree(env):
    t = token(f"{NS}/study/c.csv", "write")
    pending = env["access"].begin_write(t, f"{NS}/study/c.csv", None)
    uid = next(iter(env["helper"].ids.state["links"].values()))["uid"]
    study = env["data"] / "study"
    assert as_user(uid, f"open({str(study / 'planted.txt')!r}, 'w')", groups=[TRAVERSE])[0] != 0
    assert as_user(uid, f"import os; os.unlink({str(study / 'b.nii.gz')!r})", groups=[TRAVERSE])[0] != 0
    assert as_user(uid, f"open({str(study / 'b.nii.gz')!r}, 'w')", groups=[TRAVERSE])[0] != 0
    pending.abort()


def test_an_upload_cannot_replace_a_symlink(env):
    (env["data"] / "study" / "trap.csv").symlink_to(env["outside"] / "secret.txt")
    with pytest.raises(HTTPException) as refused:
        upload(env, f"{NS}/study/trap.csv", b"x")
    assert refused.value.status_code == 400
    assert (env["outside"] / "secret.txt").read_bytes() == b"SECRET"


def test_nothing_in_the_data_tree_is_owned_by_a_temporary_id(env):
    for i in range(3):
        upload(env, f"{NS}/batch/f{i}.bin", os.urandom(100))
    for p in env["data"].rglob("*"):
        assert not 2_000_000 <= os.lstat(p).st_uid < 3_000_000, p


# --- deletes: by the helper after its own check ---

def test_delete_needs_a_delete_token(env):
    path = f"{NS}/study/b.nii.gz"
    with pytest.raises(HTTPException) as refused:
        env["access"].delete(token(path, "read"), path, None)
    assert refused.value.status_code == 403
    env["access"].delete(token(path, "delete"), path, None)
    assert not (env["data"] / "study" / "b.nii.gz").exists()


# --- access lists always return to where they started ---

@settings(max_examples=60, deadline=None)
@given(ops=st.lists(st.tuples(st.booleans(), st.integers(2_000_000, 2_000_004), st.sampled_from([4, 5, 6])),
                    max_size=12),
       mode=st.sampled_from([0o600, 0o640, 0o644, 0o700]))
def test_any_grants_then_revoking_all_restore_the_file(ops, mode):
    path = Path("/srv") / f"acl-{uuid.uuid4().hex[:8]}"
    path.write_bytes(b"x")
    os.chmod(path, mode)
    fd = os.open(path, os.O_RDONLY)
    try:
        for grant, uid, perm in ops:
            (acl.grant_user(fd, uid, perm) if grant else acl.revoke_user(fd, uid))
        for _, uid, _ in ops:
            acl.revoke_user(fd, uid)
        assert os.fstat(fd).st_mode & 0o7777 == mode
        with pytest.raises(OSError):
            os.getxattr(fd, acl.XATTR)
    finally:
        os.close(fd)
        path.unlink()


# --- expiry when files move, and when one link can't be revoked ---

def test_a_file_moved_on_the_machine_never_reaches_a_reused_id(small_env):
    e = small_env
    fd, _ = e["access"].open_read(token(f"{NS}/study/a.nii.gz", "read", ttl=60), f"{NS}/study/a.nii.gz", None)
    os.close(fd)
    first = uid_of_only_link(e["helper"])
    os.rename(e["data"] / "study" / "a.nii.gz", e["data"] / "study" / "moved.nii.gz")  # scrubbing moves it

    e["helper"].sweep(now=time.time() + 120)
    for _ in range(2):  # use up the pool: the ID that may still hold access must never come back
        fd, _ = e["access"].open_read(token(f"{NS}/study/b.nii.gz", "read"), f"{NS}/study/b.nii.gz", None)
        os.close(fd)
        e["helper"].sweep(now=time.time() + 600)
    issued = {link["uid"] for link in e["helper"].ids.state["links"].values()}
    assert first not in issued
    assert str(first) in e["helper"].ids.state["retired"]


def test_one_link_that_cannot_be_revoked_does_not_block_the_others(env, monkeypatch):
    for name in ("a.nii.gz", "b.nii.gz"):
        fd, _ = env["access"].open_read(token(f"{NS}/study/{name}", "read", ttl=60), f"{NS}/study/{name}", None)
        os.close(fd)
    links = env["helper"].ids.state["links"]
    stuck = next(link["uid"] for link in links.values() if link["files"][0][0] == ["study", "a.nii.gz"])
    real_revoke = acl.revoke_user

    def failing_revoke(fd, uid):
        if uid == stuck:
            raise OSError("simulated failure")
        real_revoke(fd, uid)

    monkeypatch.setattr(acl, "revoke_user", failing_revoke)
    assert env["helper"].sweep(now=time.time() + 120) == 1
    remaining = {link["uid"] for link in env["helper"].ids.state["links"].values()}
    assert remaining == {stuck}  # kept, to retry; its ID is not released
    assert str(stuck) not in env["helper"].ids.state["quarantine"]
    assert not can_read(next(iter(set(range(2_000_000, 2_000_002)) - {stuck})),
                        env["data"] / "study" / "b.nii.gz", groups=[TRAVERSE])


def test_an_upload_replaced_after_placement_is_refused(env, monkeypatch):
    import app.helper as helper_module

    real_replace = helper_module.os.replace

    def replace_then_swap(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        os.unlink(dst, dir_fd=dst_dir_fd)
        os.close(os.open(dst, os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=dst_dir_fd))  # someone else's file

    monkeypatch.setattr(helper_module.os, "replace", replace_then_swap)
    with pytest.raises(HTTPException) as refused:
        upload(env, f"{NS}/study/swapped.csv", b"x")
    assert refused.value.status_code == 500
