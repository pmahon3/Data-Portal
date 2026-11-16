# backend/tests/test_policy_matcher.py
"""
Policy matcher tests

Checks the Casbin matcher in core/services/policies/casbin/model.conf directly, with policies held in
memory: no database, Keycloak or storage needed.

Verifies: AC-5

A policy path should name exactly what it covers: a file, or a folder and everything in it
("bucket/folder/*"), or "*" for everything.
"""

from pathlib import Path

import casbin
import pytest

from core.utils.policy_paths import is_safe_request_path, saved_policy_action, saved_policy_path

MODEL = Path(__file__).resolve().parents[1] / "core" / "services" / "policies" / "casbin" / "model.conf"
USER, INSTANCE = "user-1", "instance-1"


def allowed(policies: list[str], path: str, action: str = "read", policy_action: str = "read") -> bool:
    """
    Is `action` on `path` allowed, given `policy_action` policies on `policies`? Each policy goes
    through the checks a new policy is saved with: one they refuse can't exist, so it grants nothing.
    """
    enforcer = casbin.Enforcer(str(MODEL))
    for resource in policies:
        try:
            path_saved, action_saved = saved_policy_path(resource), saved_policy_action(policy_action)
        except ValueError:
            continue
        enforcer.add_policy(USER, INSTANCE, path_saved, action_saved)
    return is_safe_request_path(path) and enforcer.enforce(USER, INSTANCE, path, action)


def test_a_policy_on_everything_does_not_crash():
    assert allowed(["*"], "bucket/notes.txt")


def test_a_file_name_with_a_bracket_does_not_crash():
    # A single file named with an unmatched bracket is granted through its folder
    assert allowed(["bucket/brackets/*"], "bucket/brackets/a[b.bin")
    assert allowed(["bucket/brackets/scan (1).nii"], "bucket/brackets/scan (1).nii")
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


# --- Dangerous names and policies ---


def test_a_star_inside_a_name_never_widens_a_policy():
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
    assert not allowed(["bucket/shared/*"], "bucket/shared/~/../../secret.txt")


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


def test_two_dots_inside_a_name_are_part_of_the_name():
    assert allowed(["bucket/notes..txt"], "bucket/notes..txt")
    assert allowed(["bucket/shared/*"], "bucket/shared/..hidden/x.txt")


def test_a_tilde_is_part_of_the_name_not_a_home_directory():
    assert allowed(["bucket/~/notes.txt"], "bucket/~/notes.txt")
    assert allowed(["bucket/shared/*"], "bucket/shared/~backup.txt")
    assert not allowed(["bucket/~/*"], "bucket/other/notes.txt")
    assert not allowed(["bucket/~alice/*"], "bucket/~bob/notes.txt")
    assert not allowed(["bucket/shared/*"], "~/notes.txt")


# --- Edge cases, by kind of policy or request ---
# Each table is (policies, request, expected). One test per kind; the ids say what each row checks.

POLICY_SHAPES = [
    pytest.param(["bucket/a.txt"], "bucket/a.txt", True, id="a file covers itself"),
    pytest.param(["bucket/f/*"], "bucket/f/x/y.txt", True, id="a folder covers what is inside"),
    pytest.param(["*"], "other-bucket/x.txt", True, id="everything covers any bucket"),
    pytest.param(["bucket"], "bucket/a.txt", False, id="a bare bucket name covers nothing inside"),
    pytest.param(["bucket/f"], "bucket/f/a.txt", False, id="a folder without /* covers nothing inside"),
    pytest.param(["bucket/f/"], "bucket/f/a.txt", False, id="a folder ending in / covers nothing inside"),
    pytest.param(
        ["bucket/a/b/c/"], "bucket/a/b/c/d.txt", False,
        id="nested folders with no file name nothing"
    ),
    pytest.param(["bucket/**"], "bucket/a/b.txt", False, id="a double star is not a wildcard"),
    pytest.param(["*/a.txt"], "bucket/a.txt", False, id="a leading star is not a wildcard"),
    pytest.param(["   "], "bucket/a.txt", False, id="a policy of spaces covers nothing"),
]

REQUEST_PLACES = [
    pytest.param(["bucket/f/*"], "bucket/f/a/b/c/d/e.txt", True, id="deep inside a granted folder"),
    pytest.param(["bucket/*"], "bucket/top.txt", True, id="at the top of a granted bucket"),
    pytest.param(["bucket/f/*"], "bucket/f/", True, id="the granted folder itself"),
    pytest.param(["bucket/f/*"], "bucket/f/empty/", True, id="an empty folder inside a granted folder"),
    pytest.param(["bucket/a/b/c.txt"], "bucket/", True, id="the bucket above a granted file, to browse"),
    pytest.param(["bucket/a/b/c.txt"], "bucket/a/x/", False, id="a sibling of the path to a granted file"),
    pytest.param(["bucket/a.txt"], "bucket/a.txt/b", False, id="a path under a granted file"),
    pytest.param(["bucket/f/*"], "/bucket/f/x.txt", False, id="a request with a leading /"),
    pytest.param(["b1/f/*"], "b2/f/x.txt", False, id="the same folder in another bucket"),
    pytest.param(["bucket//f/*"], "bucket/f/x.txt", False, id="a policy with // names another folder"),
]

PATH_SPECIALS = [
    pytest.param(["bucket/f/*"], "bucket/f/.hidden", True, id="a hidden file inside a granted folder"),
    pytest.param(["bucket/.hidden"], "bucket/.hidden", True, id="a hidden file grant covers itself"),
    pytest.param(["bucket/.hidden"], "bucket/xhidden", False, id="a leading dot is a dot"),
    pytest.param(["bucket/f/..."], "bucket/f/...", True, id="a name of three dots covers itself"),
    pytest.param(["bucket/f/..."], "bucket/f/abc", False, id="a name of three dots is not a pattern"),
    pytest.param(["bucket/f/*"], "bucket/f/../g/x.txt", False, id="a .. climbs out of nothing"),
]

# Characters that mean something to regular expressions or to Casbin's keyMatch
PATTERN_CHARACTERS = list(".?+{}|^$\\")

TEXT = [
    pytest.param(["bucket/my file.txt"], "bucket/my file.txt", True, id="a space inside a name"),
    pytest.param(["bucket/my file.txt"], "bucket/myfile.txt", False, id="a space is not optional"),
    pytest.param(["bucket/données/*"], "bucket/données/x.txt", True, id="accented letters"),
    pytest.param(["bucket/研究/*"], "bucket/研究/x.txt", True, id="non-Latin letters"),
    pytest.param(["bucket/f/*"], "bucket/f%2Fx.txt", False, id="an encoded / is not a /"),
    pytest.param(["bucket/f/*"], "bucket/f/a,b.txt", True, id="a comma inside a granted folder"),
    pytest.param(["bucket/f/*"], "bucket/f/a\tb.txt", True, id="a tab inside a granted folder"),
]

ACTIONS = [
    pytest.param("read", "read", True, id="the same action"),
    pytest.param("*", "write", True, id="every action covers write"),
    pytest.param("read", "readwrite", False, id="an action is a whole word"),
    pytest.param("write", "read", False, id="another action"),
]


@pytest.mark.parametrize("policies, request_path, expected", POLICY_SHAPES)
def test_a_policy_of_each_shape_covers_exactly_what_it_names(policies, request_path, expected):
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policies, request_path, expected", REQUEST_PLACES)
def test_a_request_is_judged_by_where_it_sits_in_the_tree(policies, request_path, expected):
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policies, request_path, expected", PATH_SPECIALS)
def test_dots_in_names_are_part_of_the_name(policies, request_path, expected):
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("character", PATTERN_CHARACTERS)
def test_a_pattern_character_in_a_policy_means_itself(character):
    policy = f"bucket/a{character}b.txt"
    assert allowed([policy], policy)
    assert not allowed([policy], "bucket/aXb.txt")
    assert not allowed([policy], "bucket/ab.txt")


@pytest.mark.parametrize("policies, request_path, expected", TEXT)
def test_names_are_compared_as_written(policies, request_path, expected):
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policy_action, request_action, expected", ACTIONS)
def test_an_action_covers_only_itself_or_everything(policy_action, request_action, expected):
    assert allowed(["bucket/a.txt"], "bucket/a.txt", request_action, policy_action) is expected
