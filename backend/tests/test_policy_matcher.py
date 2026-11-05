# backend/tests/test_policy_matcher.py
"""
Policy matcher tests (INN-297)

Checks the Casbin matcher in core/services/policies/casbin/model.conf directly, with policies held in
memory: no database, Keycloak or storage needed.

A policy path should name exactly what it covers: a file, or a folder and everything in it
("bucket/folder/*"), or "*" for everything (INN-297).
"""

from pathlib import Path

import casbin

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
USER, INSTANCE = "user-1", "instance-1"


def allowed(policies: list[str], path: str, action: str = "read") -> bool:
    """Is `action` on `path` allowed, given read policies on `policies`?"""
    enforcer = casbin.Enforcer(str(MODEL))
    for resource in policies:
        enforcer.add_policy(USER, INSTANCE, resource, "read")
    return enforcer.enforce(USER, INSTANCE, path, action)


def test_a_policy_on_everything_does_not_crash():
    assert allowed(["*"], "bucket/notes.txt")


def test_a_file_name_with_a_bracket_does_not_crash():
    assert allowed(["bucket/brackets/a[b.bin"], "bucket/brackets/a[b.bin")
    assert not allowed(["bucket/brackets/ok.txt"], "bucket/brackets/a[b.bin")


def test_a_file_policy_does_not_cover_names_that_start_the_same():
    assert not allowed(["bucket/shared/notes.txt"], "bucket/shared/notes.txt.secret")
    assert not allowed(["bucket/fold"], "bucket/folder-secret/x.txt")


def test_a_dot_in_a_policy_is_a_dot():
    assert not allowed(["bucket/shared/notes.txt"], "bucket/shared/notesXtxt")


def test_a_folder_policy_covers_everything_in_it():
    assert allowed(["bucket/study/*"], "bucket/study/sub-01/anat/scan.nii.gz")


def test_the_folders_above_a_granted_file_can_be_browsed():
    assert allowed(["bucket/study/sub-01/scan.nii.gz"], "bucket/study/")
    assert not allowed(["bucket/study/sub-01/scan.nii.gz"], "bucket/other/")


def test_a_grant_on_a_longer_name_does_not_cover_a_shorter_one():
    assert not allowed(["bucket/shared/notes.txt.secret"], "bucket/shared/notes.txt")
