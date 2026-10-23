"""The data-layout conversion tool (app/layout.py). Linux and root only."""
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

OWNER, TRAVERSE = (10002, 10002), 10010


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
    report = check(str(root), OWNER, TRAVERSE)
    assert {c["path"] for c in report.changed} >= {".", "lab", "lab/raw", "lab/notes.txt", "lab/raw/scan.nii.gz"}
    after = {p: os.lstat(p) for p in root.rglob("*")}
    assert all((before[p].st_uid, before[p].st_mode) == (after[p].st_uid, after[p].st_mode) for p in before)


def test_apply_converts_and_a_second_run_changes_nothing(messy):
    root, _ = messy
    check(str(root), OWNER, TRAVERSE, apply=True)
    for d in (root, root / "lab", root / "lab" / "raw"):
        st = os.stat(d)
        assert (st.st_uid, st.st_gid, st.st_mode & 0o7777) == (10002, TRAVERSE, 0o710)
    for f in (root / "lab" / "notes.txt", root / "lab" / "raw" / "scan.nii.gz"):
        st = os.stat(f)
        assert (st.st_uid, st.st_gid, st.st_mode & 0o7777) == (*OWNER, 0o600)
    assert (root / "lab" / "notes.txt").read_text() == "notes"
    assert check(str(root), OWNER, TRAVERSE, apply=True).changed == []


def test_what_it_wont_decide_is_reported_and_left_alone(messy):
    root, outside = messy
    report = check(str(root), OWNER, TRAVERSE, apply=True)
    issues = {(i["path"], i["issue"].split(" (")[0]) for i in report.for_admin}
    assert ("lab/link", "symlink") in issues
    assert ("lab/pipe", "special file") in issues
    assert any(p.startswith("lab/") and "hard links" in issue for p, issue in issues)
    assert ("lab/notes.txt", "ACL entries for temporary IDs") in issues
    # the symlink's target outside the tree is untouched
    st = os.stat(outside / "secret.txt")
    assert st.st_uid == 0 and st.st_mode & 0o777 != 0o600
    assert os.path.islink(root / "lab" / "link")
