"""The one-off conversion of stored policies to literal paths (INN-297)."""
import pytest

from core.services.policies.convert_paths import (
    CONVERT,
    NARROWS,
    REVIEW,
    UNCHANGED,
    convert,
)


@pytest.mark.parametrize("path, action, kind, new_path, new_action", [
    (".*", ".*", CONVERT, "*", "*"),
    (".*", "read", CONVERT, "*", "read"),
    ("qa-bucket/fold/.*", "read", CONVERT, "qa-bucket/fold/*", "read"),
    ("qa-authz/study/p7/summary.csv", ".*", CONVERT, "qa-authz/study/p7/summary.csv", "*"),
    ("qa-authz/study/p7/summary.csv", "read", NARROWS, "qa-authz/study/p7/summary.csv", "read"),
    ("qa-bucket/fold", "read", NARROWS, "qa-bucket/fold", "read"),
    ("/qa-bucket/fold/.*", "read", REVIEW, "/qa-bucket/fold/.*", "read"),
    ("qa-bucket/fold.*", "read", REVIEW, "qa-bucket/fold.*", "read"),
    ("qa-bucket/fold/", "read", REVIEW, "qa-bucket/fold/", "read"),
    ("qa-bucket/sub-0[1-3]/.*", "read", REVIEW, "qa-bucket/sub-0[1-3]/.*", "read"),
    ("qa-bucket/fold/.*", "read|write", REVIEW, "qa-bucket/fold/.*", "read|write"),
    # Rows already converted stay as they are, so the script can be run again
    ("*", "*", UNCHANGED, "*", "*"),
    ("*", "read", UNCHANGED, "*", "read"),
    ("qa-bucket/fold/*", "read", UNCHANGED, "qa-bucket/fold/*", "read"),
])
def test_each_stored_shape_converts_as_planned(path, action, kind, new_path, new_action):
    result = convert(path, action)
    assert (result.kind, result.path, result.action) == (kind, new_path, new_action)


@pytest.mark.parametrize("path, action", [
    (".*", ".*"), ("qa-bucket/fold/.*", "read"), ("qa-authz/x.csv", ".*"), ("qa-bucket/fold", "read"),
])
def test_converting_twice_changes_nothing_more(path, action):
    once = convert(path, action)
    twice = convert(once.path, once.action)
    assert (twice.path, twice.action) == (once.path, once.action)
    assert twice.kind != REVIEW
