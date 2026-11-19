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


# Each table is (policies, request, expected), one per kind of policy or request; the ids say what
# each row checks. A policy the save check refuses grants nothing (see allowed()).

POLICY_SHAPES = [
    pytest.param(["bucket/a.txt"], "bucket/a.txt", True, id="a file covers itself"),
    pytest.param(["bucket/f/*"], "bucket/f/a.txt", True, id="a folder covers what is inside"),
    pytest.param(["*"], "other-bucket/x.txt", True, id="everything covers any bucket"),
    pytest.param(["bucket"], "bucket/a.txt", False, id="a bare bucket name covers nothing inside"),
    pytest.param(["bucket/f"], "bucket/f/a.txt", False, id="a folder without /* covers nothing inside"),
    pytest.param(["bucket/f/"], "bucket/f/a.txt", False, id="a folder ending in / covers nothing inside"),
    pytest.param(["bucket/a/b/c/"], "bucket/a/b/c/d.txt", False, id="nested folders, no file: nothing"),
    pytest.param(["bucket/study*"], "bucket/study-secret/x.txt", False, id="a star only after a slash"),
    pytest.param(["bucket/*/s.txt"], "bucket/x/s.txt", False, id="a star in the middle is not a wildcard"),
    pytest.param(["bucket/a*b.txt"], "bucket/aXYZb.txt", False, id="a star inside a name is not a wildcard"),
    pytest.param(["bucket/**"], "bucket/a/b.txt", False, id="a double star is not a wildcard"),
    pytest.param(["*/a.txt"], "bucket/a.txt", False, id="a leading star is not a wildcard"),
    pytest.param([""], "bucket/a.txt", False, id="an empty policy covers nothing"),
    pytest.param(["   "], "bucket/a.txt", False, id="a policy of spaces covers nothing"),
]

REQUEST_PLACES = [
    pytest.param(["bucket/f/*"], "bucket/f/a/b/c/d/e.txt", True, id="deep inside a granted folder"),
    pytest.param(["bucket/*"], "bucket/top.txt", True, id="at the top of a granted bucket"),
    pytest.param(["bucket/f/*"], "bucket/f/", True, id="the granted folder itself"),
    pytest.param(["bucket/f/*"], "bucket/f/empty/", True, id="an empty folder inside a granted folder"),
    pytest.param(["bucket/a/b/c.txt"], "bucket/a/", True, id="a folder above a granted file, to browse"),
    pytest.param(["bucket/a/b/c.txt"], "bucket/x/", False, id="a sibling of the path to a granted file"),
    pytest.param(["bucket/a.txt"], "bucket/a.txt/b", False, id="a path under a granted file"),
    pytest.param(["bucket/a.txt"], "bucket/a.txt.secret", False, id="a longer name that starts the same"),
    pytest.param(["bucket/a.txt.secret"], "bucket/a.txt", False, id="a shorter name that starts the same"),
    pytest.param(["bucket/fold"], "bucket/folder/x.txt", False, id="a folder whose name starts the same"),
    pytest.param(["bucket/f/*"], "bucket/f-old/x.txt", False, id="a folder starting the same"),
    pytest.param(["bucket/*"], "bucket2/x.txt", False, id="a bucket starting with a granted one's name"),
    pytest.param(["b1/f/*"], "b2/f/x.txt", False, id="the same folder in another bucket"),
    pytest.param(["bucket/f/*"], "/bucket/f/x.txt", False, id="a request with a leading /"),
    pytest.param(["bucket//f/*"], "bucket/f/x.txt", False, id="a policy with // names another folder"),
]

DOTS_AND_TILDES = [
    pytest.param(["bucket/f/*"], "bucket/f/.hidden", True, id="a hidden file inside a granted folder"),
    pytest.param(["bucket/.hidden"], "bucket/.hidden", True, id="a hidden file grant covers itself"),
    pytest.param(["bucket/.hidden"], "bucket/xhidden", False, id="a leading dot is a dot"),
    pytest.param(["bucket/a.txt"], "bucket/aXtxt", False, id="a dot inside a name is a dot"),
    pytest.param(["bucket/a..txt"], "bucket/a..txt", True, id="two dots inside a name"),
    pytest.param(["bucket/f/*"], "bucket/f/..hidden/x.txt", True, id="a folder named ..hidden"),
    pytest.param(["bucket/f/..."], "bucket/f/...", True, id="a name of three dots covers itself"),
    pytest.param(["bucket/f/..."], "bucket/f/abc", False, id="a name of three dots is not a pattern"),
    pytest.param(["bucket/f/*"], "bucket/f/../secret.txt", False, id="a .. in a request climbs nothing"),
    pytest.param(["bucket/f/*"], "bucket/f/../../b2/x.txt", False, id="a .. cannot reach another bucket"),
    pytest.param(["bucket/f/*"], "bucket/f/~/../../x.txt", False, id="a ~ then .. climbs nothing"),
    pytest.param(["bucket/f/../*"], "bucket/secret.txt", False, id="a .. in a folder policy names nothing"),
    pytest.param(["bucket/f/../a.txt"], "bucket/a.txt", False, id="a .. in a file policy names nothing"),
    pytest.param(["bucket/~/a.txt"], "bucket/~/a.txt", True, id="a folder named ~"),
    pytest.param(["bucket/f/*"], "bucket/f/~backup.txt", True, id="a name starting with ~"),
    pytest.param(["bucket/~/*"], "bucket/other/a.txt", False, id="~ is not a home directory"),
    pytest.param(["bucket/~alice/*"], "bucket/~bob/a.txt", False, id="~alice is not ~bob"),
    pytest.param(["bucket/f/*"], "~/a.txt", False, id="a request starting with ~"),
]

# Characters that mean something to regular expressions or to Casbin's keyMatch
PATTERN_CHARACTERS = list(".?+{}|^$\\")

TEXT = [
    pytest.param(["bucket/my file.txt"], "bucket/my file.txt", True, id="a space inside a name"),
    pytest.param(["bucket/my file.txt"], "bucket/myfile.txt", False, id="a space is not optional"),
    pytest.param(["bucket/a.txt"], "bucket/a.txt ", False, id="a trailing space in a request"),
    pytest.param(["bucket/a.txt "], "bucket/a.txt", False, id="a trailing space in a policy"),
    pytest.param(["bucket/Shared/a.txt"], "bucket/shared/a.txt", False, id="case in a policy"),
    pytest.param(["bucket/shared/*"], "bucket/SHARED/a.txt", False, id="case in a request"),
    pytest.param(["bucket/a.txt"], "BUCKET/a.txt", False, id="case in a bucket name"),
    pytest.param(["bucket/données/*"], "bucket/données/x.txt", True, id="accented letters"),
    pytest.param(["bucket/研究/*"], "bucket/研究/x.txt", True, id="non-Latin letters"),
    pytest.param(["bucket/f/*"], "bucket/f%2Fx.txt", False, id="an encoded / is not a /"),
    pytest.param(["bucket/f/*"], "bucket/f/a,b.txt", True, id="a comma inside a granted folder"),
    pytest.param(["bucket/f/*"], "bucket/f/a\tb.txt", True, id="a tab inside a granted folder"),
    pytest.param(["bucket/f/*"], "bucket/f/a[b.bin", True, id="an open bracket in a granted folder"),
    pytest.param(["bucket/scan (1).nii"], "bucket/scan (1).nii", True, id="matched brackets in a file"),
    pytest.param(["bucket/ok.txt"], "bucket/a[b.bin", False, id="a bracket does not break another grant"),
    pytest.param(["bucket/(a|b).txt"], "bucket/a.txt", False, id="a group is not a pattern"),
    pytest.param(["bucket/a.txt|bucket/s.txt"], "bucket/s.txt", False, id="a bar does not join two paths"),
    pytest.param(["bucket/a.txt"], "bucket/*", False, id="a star in a request is not a wildcard"),
    pytest.param(["bucket/shared/a.txt"], "bucket/sha*", False, id="a star ending a request"),
]

ACTIONS = [
    pytest.param("read", "read", True, id="the same action"),
    pytest.param("*", "write", True, id="every action covers write"),
    pytest.param("write", "read", False, id="another action"),
    pytest.param("read", "readwrite", False, id="an action is a whole word"),
    pytest.param("r", "read", False, id="part of an action is not the action"),
    pytest.param("read", "READ", False, id="case in an action"),
    pytest.param(".*", "write", False, id="a pattern is not every action"),
    pytest.param("read|write", "write", False, id="a bar does not join two actions"),
]


@pytest.mark.parametrize("policies, request_path, expected", POLICY_SHAPES)
def test_a_policy_of_each_shape_covers_exactly_what_it_names(policies, request_path, expected):
    """AC-5. A file, a folder ending in /*, or everything; any other shape names nothing."""
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policies, request_path, expected", REQUEST_PLACES)
def test_a_request_is_judged_by_where_it_sits_in_the_tree(policies, request_path, expected):
    """AC-5, AC-1. Covered if inside the grant; the folders above a granted file can be browsed."""
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policies, request_path, expected", DOTS_AND_TILDES)
def test_dots_and_tildes_are_part_of_the_name(policies, request_path, expected):
    """AC-5. A dot or ~ is a character in the name: .. never climbs and ~ is no home directory."""
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("character", PATTERN_CHARACTERS)
def test_a_pattern_character_in_a_policy_means_itself(character):
    """AC-5. No character in a policy path is a pattern."""
    policy = f"bucket/a{character}b.txt"
    assert allowed([policy], policy)
    assert not allowed([policy], "bucket/aXb.txt")
    assert not allowed([policy], "bucket/ab.txt")


@pytest.mark.parametrize("policies, request_path, expected", TEXT)
def test_names_are_compared_as_written(policies, request_path, expected):
    """AC-5. Names match exactly as written: spaces, case, letters and punctuation."""
    assert allowed(policies, request_path) is expected


@pytest.mark.parametrize("policy_action, request_action, expected", ACTIONS)
def test_an_action_covers_only_itself_or_everything(policy_action, request_action, expected):
    """AC-3. A permission for one action allows only that action, or every action if it is *."""
    assert allowed(["bucket/a.txt"], "bucket/a.txt", request_action, policy_action) is expected
