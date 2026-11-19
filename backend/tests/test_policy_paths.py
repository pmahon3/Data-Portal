"""
Which policy paths and actions can be saved

A policy path is a file, a folder and everything in it ("bucket/folder/*"), or "*" for everything.
Anything Casbin's keyMatch would read differently from how it looks, or its storage adapter would
split, is refused with the reason, one case per kind here. What each refused path would have granted
is in test_policy_matcher.py.

Verifies: AC-5
"""

import re

import pytest

from core.utils.policy_paths import saved_policy_action, saved_policy_path


@pytest.mark.parametrize("path, saved", [
    pytest.param("bucket/study/scan.nii.gz", "bucket/study/scan.nii.gz", id="a file"),
    pytest.param("bucket/study/*", "bucket/study/*", id="a folder and everything in it"),
    pytest.param("*", "*", id="everything"),
    pytest.param("/bucket/study/*", "bucket/study/*", id="a leading / is dropped"),
    pytest.param("bucket/scan (1).nii", "bucket/scan (1).nii", id="matched brackets"),
])
def test_a_file_a_folder_and_everything_can_be_saved(path, saved):
    assert saved_policy_path(path) == saved


@pytest.mark.parametrize("path, reason", [
    pytest.param("bucket/study*", "'*' can only be used", id="a star anywhere but a last folder"),
    pytest.param("bucket/../*", "'..' parts", id="a . or .. part"),
    pytest.param("bucket/study/", "end in '/'", id="an empty part or a trailing /"),
    pytest.param("", "'*' can only be used", id="nothing"),
    pytest.param(" bucket/a.txt", "start or end with a space", id="a space around the path"),
    pytest.param("bucket/a, b.txt", "a comma", id="a comma"),
    pytest.param("bucket/a[b.bin", "an unmatched bracket", id="an unmatched bracket"),
    pytest.param("bucket/a\tb.txt", "control characters", id="a control character"),
])
def test_anything_else_is_refused_with_the_reason(path, reason):
    with pytest.raises(ValueError, match=re.escape(reason)) as refused:
        saved_policy_path(path)
    assert "A policy path is a file" in str(refused.value)


@pytest.mark.parametrize("action, ok", [
    pytest.param("read", True, id="one word"),
    pytest.param("*", True, id="every action"),
    pytest.param("read|write", False, id="anything else"),
    pytest.param("", False, id="nothing"),
])
def test_an_action_is_one_word_or_everything(action, ok):
    if ok:
        assert saved_policy_action(action) == action
    else:
        with pytest.raises(ValueError):
            saved_policy_action(action)
