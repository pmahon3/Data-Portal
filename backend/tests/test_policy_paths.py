"""
Which policy paths and actions can be saved

A policy path is a file, a folder and everything in it ("bucket/folder/*"), or "*" for everything.
Anything Casbin's keyMatch would read differently from how it looks, or its storage adapter would
split, is refused with the reason. Requests with a ".." part are never decided.
"""

import pytest

from core.utils.policy_paths import is_safe_request_path, saved_policy_action, saved_policy_path


@pytest.mark.parametrize("path, saved", [
    ("bucket/study/scan.nii.gz", "bucket/study/scan.nii.gz"),
    ("bucket/study/*", "bucket/study/*"),
    ("*", "*"),
    ("bucket/notes..txt", "bucket/notes..txt"),
    ("/bucket/study/*", "bucket/study/*"),
    ("bucket/scan (1).nii", "bucket/scan (1).nii"),
    ("bucket/a[b].bin", "bucket/a[b].bin"),
])
def test_a_file_a_folder_and_everything_can_be_saved(path, saved):
    assert saved_policy_path(path) == saved


@pytest.mark.parametrize("path", [
    "bucket/study*",
    "bucket/*/secret.txt",
    "bucket/a*b.txt",
    "bucket/.*",
    "bucket/../*",
    "bucket/shared/../secret.txt",
    "bucket/./notes.txt",
    "bucket//notes.txt",
    "bucket/study/",
    "",
    " bucket/notes.txt",
    "bucket/notes.txt ",
    "bucket/notes, draft.txt",
    "bucket/a[b.bin",
    "bucket/a]b.bin",
    "bucket/a)b.bin",
    "bucket/a(b.bin",
    "bucket/a\tb.txt",
])
def test_anything_else_is_refused(path):
    with pytest.raises(ValueError):
        saved_policy_path(path)


@pytest.mark.parametrize("action, ok", [
    ("read", True),
    ("*", True),
    ("READ", False),
    (".*", False),
    ("read|write", False),
    ("", False),
])
def test_an_action_is_one_word_or_everything(action, ok):
    if ok:
        assert saved_policy_action(action) == action
    else:
        with pytest.raises(ValueError):
            saved_policy_action(action)


def test_a_request_with_dot_dot_is_never_decided():
    assert not is_safe_request_path("bucket/shared/../secret.txt")
    assert is_safe_request_path("bucket/shared/..hidden/x.txt")
