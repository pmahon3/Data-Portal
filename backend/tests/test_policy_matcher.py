# backend/tests/test_policy_matcher.py
"""
Policy matcher tests

Checks the Casbin matcher in core/services/policies/casbin/model.conf directly, with policies held in
memory: no database, Keycloak or storage needed.

A policy path should name exactly what it covers: a file, or a folder and everything in it
("bucket/folder/*"), or "*" for everything. Today paths are matched as regular expressions, so these
tests are known-failing until the bug is fixed.
"""

from pathlib import Path

import casbin
import pytest

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
USER, INSTANCE = "user-1", "instance-1"

REGEX_PATHS_BUG = pytest.mark.xfail(strict=True, reason="policy paths are matched as regular expressions")


def allowed(policies: list[str], path: str, action: str = "read", policy_action: str = "read") -> bool:
    """Is `action` on `path` allowed, given `policy_action` policies on `policies`?"""
    enforcer = casbin.Enforcer(str(MODEL))
    for resource in policies:
        enforcer.add_policy(USER, INSTANCE, resource, policy_action)
    return enforcer.enforce(USER, INSTANCE, path, action)


@REGEX_PATHS_BUG
def test_a_policy_on_everything_does_not_crash():
    assert allowed(["*"], "bucket/notes.txt")


@REGEX_PATHS_BUG
def test_a_file_name_with_a_bracket_does_not_crash():
    assert allowed(["bucket/brackets/a[b.bin"], "bucket/brackets/a[b.bin")
    assert not allowed(["bucket/brackets/ok.txt"], "bucket/brackets/a[b.bin")


@REGEX_PATHS_BUG
def test_a_file_policy_does_not_cover_names_that_start_the_same():
    assert not allowed(["bucket/shared/notes.txt"], "bucket/shared/notes.txt.secret")
    assert not allowed(["bucket/fold"], "bucket/folder-secret/x.txt")


@REGEX_PATHS_BUG
def test_a_dot_in_a_policy_is_a_dot():
    assert not allowed(["bucket/shared/notes.txt"], "bucket/shared/notesXtxt")


def test_a_folder_policy_covers_everything_in_it():
    """Already true today, and must stay true."""
    assert allowed(["bucket/study/*"], "bucket/study/sub-01/anat/scan.nii.gz")


# --- Dangerous names and policies ---


def test_a_star_in_a_file_name_is_a_star():
    assert allowed(["bucket/a*b.txt"], "bucket/a*b.txt")
    assert not allowed(["bucket/a*b.txt"], "bucket/aXYZb.txt")


def test_a_star_covers_a_folder_only_after_its_slash():
    assert not allowed(["bucket/study*"], "bucket/study-secret/x.txt")


def test_a_star_in_the_middle_of_a_policy_is_not_a_wildcard():
    assert not allowed(["bucket/*/secret.txt"], "bucket/anything/secret.txt")


def test_a_request_for_a_path_with_a_star_is_not_a_wildcard():
    assert not allowed(["bucket/a.txt"], "bucket/*")
    assert not allowed(["bucket/shared/a.txt"], "bucket/sha*")


def test_dot_dot_in_a_request_does_not_climb_out_of_a_folder():
    assert not allowed(["bucket/shared/*"], "bucket/shared/../secret.txt")
    assert not allowed(["bucket/shared/*"], "bucket/shared/../../other-bucket/x.txt")


def test_dot_dot_in_a_policy_does_not_reach_another_folder():
    assert not allowed(["bucket/shared/../*"], "bucket/secret.txt")
    assert not allowed(["bucket/shared/../secret.txt"], "bucket/secret.txt")


def test_regular_expression_characters_in_a_policy_mean_themselves():
    assert not allowed(["bucket/notes?.txt"], "bucket/note.txt")
    assert not allowed(["bucket/a+.txt"], "bucket/aaa.txt")
    assert not allowed(["bucket/(a|b).txt"], "bucket/a.txt")
    assert not allowed(["bucket/a.txt|bucket/secret.txt"], "bucket/secret.txt")
    assert not allowed(["bucket/^secret$"], "bucket/secret")


def test_an_empty_policy_covers_nothing():
    assert not allowed([""], "bucket/notes.txt")


def test_a_folder_policy_does_not_cover_a_folder_that_starts_the_same():
    assert not allowed(["bucket/study/*"], "bucket/study-old/x.txt")
    assert not allowed(["bucket/*"], "bucket2/x.txt")


def test_a_policy_action_is_a_word_not_a_pattern():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "read", policy_action="r")
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "write", policy_action=".*")
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "write", policy_action="read|write")


# --- Simple cases ---


def test_upper_and_lower_case_are_different_names():
    assert not allowed(["bucket/Shared/notes.txt"], "bucket/shared/notes.txt")
    assert not allowed(["bucket/shared/*"], "bucket/SHARED/notes.txt")
    assert not allowed(["bucket/shared/notes.txt"], "BUCKET/shared/notes.txt")


def test_upper_and_lower_case_actions_are_different():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "READ")


def test_a_trailing_space_is_part_of_the_name():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt ")
    assert not allowed(["bucket/notes.txt "], "bucket/notes.txt")


# --- Dangerous names and policies ---


@REGEX_PATHS_BUG
def test_a_star_in_a_file_name_is_a_star():
    assert allowed(["bucket/a*b.txt"], "bucket/a*b.txt")
    assert not allowed(["bucket/a*b.txt"], "bucket/aXYZb.txt")


@REGEX_PATHS_BUG
def test_a_star_covers_a_folder_only_after_its_slash():
    assert not allowed(["bucket/study*"], "bucket/study-secret/x.txt")


def test_a_star_in_the_middle_of_a_policy_is_not_a_wildcard():
    assert not allowed(["bucket/*/secret.txt"], "bucket/anything/secret.txt")


@REGEX_PATHS_BUG
def test_a_request_for_a_path_with_a_star_is_not_a_wildcard():
    assert not allowed(["bucket/a.txt"], "bucket/*")
    assert not allowed(["bucket/shared/a.txt"], "bucket/sha*")


@REGEX_PATHS_BUG
def test_dot_dot_in_a_request_does_not_climb_out_of_a_folder():
    assert not allowed(["bucket/shared/*"], "bucket/shared/../secret.txt")
    assert not allowed(["bucket/shared/*"], "bucket/shared/../../other-bucket/x.txt")


def test_dot_dot_in_a_policy_does_not_reach_another_folder():
    assert not allowed(["bucket/shared/../*"], "bucket/secret.txt")
    assert not allowed(["bucket/shared/../secret.txt"], "bucket/secret.txt")


@REGEX_PATHS_BUG
def test_regular_expression_characters_in_a_policy_mean_themselves():
    assert not allowed(["bucket/notes?.txt"], "bucket/note.txt")
    assert not allowed(["bucket/a+.txt"], "bucket/aaa.txt")
    assert not allowed(["bucket/(a|b).txt"], "bucket/a.txt")
    assert not allowed(["bucket/a.txt|bucket/secret.txt"], "bucket/secret.txt")
    assert not allowed(["bucket/^secret$"], "bucket/secret")


@REGEX_PATHS_BUG
def test_an_empty_policy_covers_nothing():
    assert not allowed([""], "bucket/notes.txt")


@REGEX_PATHS_BUG
def test_a_folder_policy_does_not_cover_a_folder_that_starts_the_same():
    assert not allowed(["bucket/study/*"], "bucket/study-old/x.txt")
    assert not allowed(["bucket/*"], "bucket2/x.txt")


@REGEX_PATHS_BUG
def test_a_policy_action_is_a_word_not_a_pattern():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "read", policy_action="r")
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "write", policy_action=".*")
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "write", policy_action="read|write")


# --- Simple cases ---


def test_upper_and_lower_case_are_different_names():
    assert not allowed(["bucket/Shared/notes.txt"], "bucket/shared/notes.txt")
    assert not allowed(["bucket/shared/*"], "bucket/SHARED/notes.txt")
    assert not allowed(["bucket/shared/notes.txt"], "BUCKET/shared/notes.txt")


def test_upper_and_lower_case_actions_are_different():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt", "READ")


@REGEX_PATHS_BUG
def test_a_trailing_space_is_part_of_the_name():
    assert not allowed(["bucket/notes.txt"], "bucket/notes.txt ")
    assert not allowed(["bucket/notes.txt "], "bucket/notes.txt")


def test_two_dots_inside_a_name_are_part_of_the_name():
    assert allowed(["bucket/notes..txt"], "bucket/notes..txt")
    assert allowed(["bucket/shared/*"], "bucket/shared/..hidden/x.txt")
