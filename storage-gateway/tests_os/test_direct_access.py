"""
Working on a machine directly alongside the portal (A1, 2026-10-31: system administrators and project
managers manage direct access by hand over SSH; the portal governs only access through itself).
What an administrator can rely on, and what to avoid, when both touch the same files.

Linux and root only (see test_isolation.py).

Verifies: PX-9.
"""
import os
import struct
import sys
import time

import pytest

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("operating-system boundary tests need Linux and root", allow_module_level=True)

from app import acl, layout  # noqa: E402
from tests_os.test_isolation import (  # noqa: E402
    DATA_OWNER, NS, TRAVERSE, can_read, close_env, make_env, read_fd, token, uid_of_only_link, upload,
)

PERSON = 50001  # someone an administrator gives direct access (an ordinary account, outside the temporary range)


@pytest.fixture
def env():
    e = make_env()
    yield e
    close_env(e)


def admin_grants(path, uid, perm, mask=None):
    """What `setfacl -m u:<uid>:<perm>` does (optionally with an explicit mask, `-m m::<mask>`)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        acl.grant_user(fd, uid, perm)
        if mask is not None:
            entries = [(t, mask if t == acl.MASK else p, i) for t, p, i in acl.read(fd)]
            os.setxattr(fd, acl.XATTR, struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *e) for e in entries))
    finally:
        os.close(fd)


def can_write(uid, path, groups=()):
    from tests_os.test_isolation import as_user
    return as_user(uid, f"open({str(path)!r}, 'r+b').close()", groups)[0] == 0


def portal_reads(env, name):
    fd, _ = env["access"].open_read(token(f"{NS}/study/{name}", "read", ttl=1), f"{NS}/study/{name}", None)
    read_fd(fd)


def test_an_administrators_entries_survive_portal_grants_and_expiry(env):
    """PX-9. The portal adds and removes only its own entries."""
    f = env["data"] / "study" / "a.nii.gz"
    admin_grants(f, PERSON, acl.READ)
    portal_reads(env, "a.nii.gz")
    temporary = uid_of_only_link(env["helper"])
    assert can_read(PERSON, f, groups=[TRAVERSE]) and can_read(temporary, f, groups=[TRAVERSE])
    time.sleep(1.5)
    env["helper"].sweep(now=time.time() + 10)
    assert can_read(PERSON, f, groups=[TRAVERSE]) and not can_read(temporary, f, groups=[TRAVERSE])


def test_a_restrictive_mask_is_widened_by_a_portal_grant(env):
    """PX-9. One mask covers every entry on a file, and each portal grant recomputes it, so a mask is no
    way to limit someone: give them only the permissions they should have in their own entry."""
    f = env["data"] / "study" / "a.nii.gz"
    admin_grants(f, PERSON, acl.READ | acl.WRITE, mask=acl.READ)  # rw entry held to read by the mask
    assert not can_write(PERSON, f, groups=[TRAVERSE])
    portal_reads(env, "a.nii.gz")
    assert can_write(PERSON, f, groups=[TRAVERSE])


def test_portal_uploads_dont_inherit_a_folders_default_entries(env):
    """PX-9. Uploads are moved in from staging, so a folder's default ACL doesn't reach them: people
    working directly need an administrator to grant each upload (or a regular re-grant)."""
    study = env["data"] / "study"
    fd = os.open(study, os.O_RDONLY | os.O_DIRECTORY)
    try:
        defaults = [(acl.USER_OBJ, 7, acl.UNDEFINED), (acl.USER, acl.READ, PERSON), (acl.GROUP_OBJ, 1, acl.UNDEFINED),
                    (acl.MASK, acl.READ, acl.UNDEFINED), (acl.OTHER, 0, acl.UNDEFINED)]
        os.setxattr(fd, "system.posix_acl_default", struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *e) for e in defaults))
    finally:
        os.close(fd)
    upload(env, f"{NS}/study/new.csv", b"x")
    direct = study / "made-here.csv"
    direct.write_bytes(b"y")  # created in place, as someone working on the machine would
    assert not can_read(PERSON, study / "new.csv", groups=[TRAVERSE])
    assert can_read(PERSON, direct, groups=[TRAVERSE])


@pytest.mark.xfail(strict=True, reason="layout --apply resets the mode with chmod, which on a file with an ACL "
                   "sets the mask to the group bits (none), switching off every named entry")
def test_the_layout_tool_keeps_administrators_entries_working(env):
    """PX-9. Resetting a file's mode mustn't switch off the access an administrator granted on it."""
    f = env["data"] / "study" / "a.nii.gz"
    os.chmod(f, 0o640)  # drifted from the layout
    admin_grants(f, PERSON, acl.READ)
    layout.check(str(env["data"]), (DATA_OWNER, DATA_OWNER), TRAVERSE, apply=True)
    assert can_read(PERSON, f, groups=[TRAVERSE])


def test_the_layout_tool_takes_ownership_of_files_created_directly(env):
    """PX-9. Files someone creates on the machine become the data owner's when the tool is applied; the
    person who made them keeps access only through an entry an administrator gives them."""
    f = env["data"] / "study" / "mine.csv"
    f.write_bytes(b"z")
    os.chown(f, PERSON, PERSON)
    os.chmod(f, 0o644)
    layout.check(str(env["data"]), (DATA_OWNER, DATA_OWNER), TRAVERSE, apply=True)
    st = os.stat(f)
    assert (st.st_uid, st.st_mode & 0o777) == (DATA_OWNER, 0o600)
    assert not can_read(PERSON, f, groups=[TRAVERSE])
