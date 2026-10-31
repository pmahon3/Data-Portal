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
    fd, _ = env["access"].open_read(token(f"{NS}/study/{name}", "read", ttl=3), f"{NS}/study/{name}", None)
    read_fd(fd)


def test_an_administrators_entries_survive_portal_grants_and_expiry(env):
    """PX-9. The portal adds and removes only its own entries."""
    f = env["data"] / "study" / "a.nii.gz"
    admin_grants(f, PERSON, acl.READ)
    portal_reads(env, "a.nii.gz")
    temporary = uid_of_only_link(env["helper"])
    assert can_read(PERSON, f, groups=[TRAVERSE]) and can_read(temporary, f, groups=[TRAVERSE])
    env["helper"].sweep(now=time.time() + 10)  # past the link's expiry
    assert can_read(PERSON, f, groups=[TRAVERSE]) and not can_read(temporary, f, groups=[TRAVERSE])


def test_a_restrictive_mask_is_widened_by_a_portal_grant(env):
    """PX-9. One mask covers every entry on a file, and each portal grant recomputes it, so a mask is no
    way to limit someone: give them only the permissions they should have in their own entry."""
    f = env["data"] / "study" / "a.nii.gz"
    admin_grants(f, PERSON, acl.READ | acl.WRITE, mask=acl.READ)  # rw entry held to read by the mask
    assert not can_write(PERSON, f, groups=[TRAVERSE])
    portal_reads(env, "a.nii.gz")
    assert can_write(PERSON, f, groups=[TRAVERSE])


LAB = 3000  # a research group that works on the files directly


def lab_area(env):
    """study/ as a lab's working area: the lab's group, the layout tool applied."""
    study = env["data"] / "study"
    os.chown(study, DATA_OWNER, LAB)
    os.chmod(study, 0o2770)
    layout.check(str(env["data"]), TRAVERSE, apply=True)
    return study


def test_a_portal_upload_takes_its_folders_group_and_default_entries(env):
    """PX-9. An upload reaches the lab and the people an administrator named on the folder, as a file
    made there would, but never everyone else, and never through a leftover temporary entry."""
    study = lab_area(env)
    fd = os.open(study, os.O_RDONLY | os.O_DIRECTORY)
    try:
        acl.write_default(fd, acl.read_default(fd) + [(acl.USER, acl.READ, PERSON), (acl.USER, acl.READ, 2_000_500)])
    finally:
        os.close(fd)
    upload(env, f"{NS}/study/new.csv", b"x")
    new = study / "new.csv"
    entries = acl.read(os.open(new, os.O_RDONLY))
    assert os.stat(new).st_gid == LAB
    assert can_read(PERSON, new, groups=[TRAVERSE]) and can_read(60000, new, groups=[LAB, TRAVERSE])
    assert next(p for t, p, _ in entries if t == acl.OTHER) == 0
    assert not any(t == acl.USER and i == 2_000_500 for t, _, i in entries)


def test_an_upload_into_a_folder_without_defaults_is_the_data_owners_alone(env):
    """PX-9. Where nobody set up the folder, an upload is as closed as before."""
    upload(env, f"{NS}/study/new.csv", b"x")
    st = os.stat(env["data"] / "study" / "new.csv")
    assert (st.st_uid, st.st_mode & 0o777) == (DATA_OWNER, 0o600)


def test_a_folder_an_upload_creates_inherits_and_stays_passable(env):
    """PX-9. New folders follow their parent, and the portal can still reach files in them."""
    study = lab_area(env)
    upload(env, f"{NS}/study/derived/run1/out.csv", b"o")
    for d in (study / "derived", study / "derived" / "run1"):
        assert os.stat(d).st_gid == LAB
    assert can_read(60000, study / "derived" / "run1" / "out.csv", groups=[LAB, TRAVERSE])
    fd, _ = env["access"].open_read(token(f"{NS}/study/derived/run1/out.csv", "read"),
                                    f"{NS}/study/derived/run1/out.csv", None)
    assert read_fd(fd) == b"o"


def test_after_the_layout_a_link_reads_a_researchers_file_and_nothing_else(env):
    """PX-9, AC-3. The lab keeps its files; the portal's temporary ID still reads only what it's granted."""
    study = lab_area(env)
    mine = study / "mine.csv"
    mine.write_bytes(b"m")
    os.chown(mine, PERSON, LAB)
    fd, _ = env["access"].open_read(token(f"{NS}/study/mine.csv", "read"), f"{NS}/study/mine.csv", None)
    assert read_fd(fd) == b"m"
    temporary = uid_of_only_link(env["helper"])
    assert not can_read(temporary, study / "b.nii.gz", groups=[TRAVERSE])
    assert not can_read(temporary, env["data"] / "study" / "a.nii.gz", groups=[TRAVERSE])
    from tests_os.test_isolation import as_user
    assert as_user(temporary, f"import os; os.listdir({str(study)!r})", groups=[TRAVERSE])[0] != 0
    assert os.stat(mine).st_uid == PERSON  # still theirs


def test_the_layout_tool_keeps_administrators_entries_working(env):
    """PX-9. Closing a file to everyone else mustn't switch off the access an administrator granted on it."""
    f = env["data"] / "study" / "a.nii.gz"
    os.chmod(f, 0o644)  # open to everyone: the tool will close it
    admin_grants(f, PERSON, acl.READ)
    layout.check(str(env["data"]), TRAVERSE, apply=True)
    assert can_read(PERSON, f, groups=[TRAVERSE])
