"""
The layout tool (app/layout.py) for the area a machine exposes to the portal. Owners, groups and
administrators' entries are left alone (A1: administrators manage direct access); the tool only
removes access for everyone else and lets temporary IDs pass through folders, so the portal's grants
stay the only way in for them, and new files and folders start that way too. Linux and root only.

Verifies: PX-9.
"""
import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("needs Linux and root", allow_module_level=True)

from app import acl  # noqa: E402
from app.layout import check  # noqa: E402

TRAVERSE = 10010
LAB = 3000  # a research group that works on the files directly


@pytest.fixture
def messy():
    base = Path("/srv") / f"layout-{uuid.uuid4().hex[:8]}"
    root, outside = base / "data", base / "outside"
    (root / "lab" / "raw").mkdir(parents=True)
    outside.mkdir()
    (root / "lab" / "raw" / "scan.nii.gz").write_bytes(b"scan")
    (root / "lab" / "notes.txt").write_text("notes")
    os.chmod(root / "lab" / "notes.txt", 0o644)
    os.chown(root / "lab" / "notes.txt", 1000, 1000)          # a researcher's own file
    (outside / "secret.txt").write_text("secret")
    (root / "lab" / "link").symlink_to(outside / "secret.txt")
    os.mkfifo(root / "lab" / "pipe")
    os.link(root / "lab" / "raw" / "scan.nii.gz", root / "lab" / "scan-hardlink.nii.gz")
    fd = os.open(root / "lab" / "notes.txt", os.O_RDONLY)
    acl.grant_user(fd, 2_000_123, acl.READ)                    # left behind by a crash
    os.close(fd)
    yield root, outside
    shutil.rmtree(base)


def test_report_only_changes_nothing(messy):
    root, _ = messy
    before = {p: os.lstat(p) for p in root.rglob("*")}
    report = check(str(root), TRAVERSE)
    assert {c["path"] for c in report.changed} >= {".", "lab", "lab/raw", "lab/notes.txt", "lab/raw/scan.nii.gz"}
    after = {p: os.lstat(p) for p in root.rglob("*")}
    assert all((before[p].st_uid, before[p].st_mode) == (after[p].st_uid, after[p].st_mode) for p in before)


def entries_of(path, default=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        return acl.read_default(fd) if default else acl.read(fd)
    finally:
        os.close(fd)


def perm(entries, tag, ident=acl.UNDEFINED):
    return next((p for t, p, i in entries if t == tag and i == ident), None)


def test_apply_closes_the_area_to_everyone_else_and_keeps_owners(messy):
    root, _ = messy
    owners = {p: (os.stat(p).st_uid, os.stat(p).st_gid) for p in (root / "lab", root / "lab" / "notes.txt")}
    check(str(root), TRAVERSE, apply=True)
    assert {p: (os.stat(p).st_uid, os.stat(p).st_gid) for p in owners} == owners  # owners and groups kept
    for f in (root / "lab" / "notes.txt", root / "lab" / "raw" / "scan.nii.gz"):
        assert perm(entries_of(f), acl.OTHER) == 0
        assert perm(entries_of(f), acl.USER_OBJ) == 6  # the owner keeps what they had
    for d in (root, root / "lab", root / "lab" / "raw"):
        assert perm(entries_of(d), acl.OTHER) == 0
        assert perm(entries_of(d), acl.GROUP, TRAVERSE) == acl.EXECUTE  # pass through, never list
        assert perm(entries_of(d, default=True), acl.OTHER) == 0          # new files start closed
        assert perm(entries_of(d, default=True), acl.GROUP, TRAVERSE) == acl.EXECUTE
    assert (root / "lab" / "notes.txt").read_text() == "notes"


def test_a_second_run_changes_nothing(messy):
    root, _ = messy
    check(str(root), TRAVERSE, apply=True)
    assert check(str(root), TRAVERSE, apply=True).changed == []


def test_administrators_entries_are_kept(messy):
    root, _ = messy
    f = root / "lab" / "notes.txt"
    fd = os.open(f, os.O_RDONLY)
    acl.grant_user(fd, 50001, acl.READ)
    os.close(fd)
    check(str(root), TRAVERSE, apply=True)
    assert perm(entries_of(f), acl.USER, 50001) == acl.READ


def test_files_made_later_start_closed_to_everyone_else(messy):
    root, _ = messy
    os.chown(root / "lab", 0, LAB)
    os.chmod(root / "lab", 0o2770)
    check(str(root), TRAVERSE, apply=True)
    made = root / "lab" / "derivative.nii.gz"
    old = os.umask(0o022)
    try:
        made.write_bytes(b"d")  # a pipeline writing a derivative, with a typical umask
    finally:
        os.umask(old)
    assert perm(entries_of(made), acl.OTHER) == 0
    assert perm(entries_of(made), acl.GROUP_OBJ) & acl.READ  # the lab group still reads it


def test_what_it_wont_decide_is_reported_and_left_alone(messy):
    root, outside = messy
    report = check(str(root), TRAVERSE, apply=True)
    issues = {(i["path"], i["issue"].split(" (")[0]) for i in report.for_admin}
    assert ("lab/link", "symlink") in issues
    assert ("lab/pipe", "special file") in issues
    assert any(p.startswith("lab/") and "hard links" in issue for p, issue in issues)
    assert ("lab/notes.txt", "ACL entries for temporary IDs") in issues
    # the symlink's target outside the tree is untouched
    st = os.stat(outside / "secret.txt")
    assert st.st_uid == 0 and st.st_mode & 0o777 != 0o600
    assert os.path.islink(root / "lab" / "link")
