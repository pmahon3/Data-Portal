"""
Steps for features/access_rules.feature, plus property tests for the decision layer.

Every check runs through both the definition (rule_allows, rule_shows_folder) and the indexed
Checker, so the scenarios also test that the two agree.

Verifies: AC-5, AC-6, AC-8, AC-10.
"""
import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios, then, when

from core.services.policies.rules import (
    Checker,
    Rule,
    conditions_json,
    covering,
    normalize_rule_path,
    rule_allows,
    rule_from_stored,
    rule_shows_folder,
    today,
    validate_endings,
    validate_kinds,
    validate_excluded,
    validate_rule_action,
)

scenarios("features/access_rules.feature")


def allows(rules, path, action):
    expected = any(rule_allows(rule, path, action) for rule in rules)
    assert Checker(rules).allows(path, action) == expected, "Checker disagrees with rule_allows"
    return expected


def shows_folder(rules, folder, action):
    expected = any(rule_shows_folder(rule, folder, action) for rule in rules)
    assert Checker(rules).shows_folder(folder, action) == expected, "Checker disagrees with rule_shows_folder"
    return expected


@pytest.fixture
def rules():
    return []


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)"$'))
def user_holds(rules, action, path):
    rules.append(Rule(path, action))


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)" until "(?P<ends>[^"]*)"$'))
def user_holds_until(rules, action, path, ends):
    rules.append(Rule(path, action, today() if ends == "today" else datetime.date.fromisoformat(ends)))


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)" leaving out "(?P<excluded>[^"]*)"$'))
def user_holds_leaving_out(rules, action, path, excluded):
    rules.append(Rule(path, action, None, tuple(e.strip() for e in excluded.split(","))))


def endings_of(text):
    return tuple(e.strip() for e in text.split(","))


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)" for files ending in "(?P<endings>[^"]*)" leaving out "(?P<excluded>[^"]*)"$'))
def user_holds_endings_leaving_out(rules, action, path, endings, excluded):
    rules.append(Rule(path, action, None, tuple(e.strip() for e in excluded.split(",")), endings_of(endings)))


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)" for files ending in "(?P<endings>[^"]*)"$'))
def user_holds_endings(rules, action, path, endings):
    rules.append(Rule(path, action, None, (), endings_of(endings)))


@bdd_given(parsers.re(r'the user holds "(?P<action>[^"]*)" on "(?P<path>[^"]*)" for kinds "(?P<kinds>[^"]*)" of the (?P<standard>\S+) dataset at "(?P<dataset>[^"]*)"$'))
def user_holds_kinds(rules, action, path, kinds, standard, dataset):
    rules.append(Rule(path, action, kinds=endings_of(kinds), dataset=dataset, standard=standard))


@then(parsers.re(r'the user (?P<may>may|may not) "(?P<action>[^"]*)" "(?P<path>[^"]*)"'))
def user_may(rules, may, action, path):
    assert allows(rules, path, action) == (may == "may")


@then(parsers.re(r'the folder "(?P<folder>[^"]*)" is (?P<shown>shown|not shown) when browsing to "(?P<action>[^"]*)"'))
def folder_shown(rules, folder, shown, action):
    assert shows_folder(rules, folder, action) == (shown == "shown")


@when(parsers.re(r'an administrator saves a policy on "(?P<entered>[^"]*)"$'), target_fixture="saved")
def save_policy(entered):
    try:
        return normalize_rule_path(entered)
    except ValueError as error:
        return error


@when(parsers.re(r'an administrator saves a policy on "(?P<policy>[^"]*)" leaving out "(?P<excluded>[^"]*)"$'), target_fixture="saved")
def save_policy_leaving_out(policy, excluded):
    try:
        return validate_excluded(policy, [excluded])
    except ValueError as error:
        return error


@when(parsers.re(r'an administrator saves a policy on "(?P<policy>[^"]*)" for files ending in "(?P<endings>[^"]*)"$'), target_fixture="saved")
def save_policy_endings(policy, endings):
    try:
        return validate_endings(policy, endings_of(endings))
    except ValueError as error:
        return error


@when(parsers.re(r'an administrator saves a policy on "(?P<policy>[^"]*)" for kinds "(?P<kinds>[^"]*)" of the (?P<standard>\S+) dataset at "(?P<dataset>[^"]*)"$'), target_fixture="saved")
def save_policy_kinds(policy, kinds, standard, dataset):
    try:
        return validate_kinds(policy, endings_of(kinds), dataset or None, standard)
    except ValueError as error:
        return error


@then(parsers.parse("it is saved for kinds {expected}"))
def saved_for_kinds(saved, expected):
    assert saved == endings_of(expected)


@then(parsers.parse("it is saved for endings {expected}"))
def saved_for_endings(saved, expected):
    assert saved == endings_of(expected)


@then(parsers.parse("it is saved leaving out {expected}"))
def saved_leaving_out(saved, expected):
    assert saved == (expected,)


@then(parsers.parse('it is saved as "{expected}"'))
def saved_as(saved, expected):
    assert saved == expected


@then("it is refused")
def refused(saved):
    assert isinstance(saved, ValueError)


# Property tests: the indexed Checker gives the same answers as the definition for any valid
# rules and any path, and saving is stable.

SEGMENTS = st.sampled_from(["a", "b", "study", "p7", "sub-07", "anat", "x.nii", "y.csv", "Z.NII", "a[b", "(c)"])
ACTIONS = st.sampled_from(["read", "write", "delete"])


def joined(min_size, max_size):
    return st.lists(SEGMENTS, min_size=min_size, max_size=max_size).map("/".join)


ENDS = st.one_of(st.none(), st.sampled_from([datetime.date(2000, 1, 1), datetime.date(2999, 12, 31)]))


@st.composite
def valid_rule(draw):
    """Any valid rule: a file, a folder (possibly leaving things out inside it) or everything."""
    path = draw(st.one_of(st.just("*"), joined(1, 3).map(lambda p: p + "/*"), joined(1, 4)))
    excluded = ()
    if path.endswith("*"):
        inside = path[:-1]
        excluded = tuple(draw(st.lists(st.one_of(joined(1, 2).map(lambda p: inside + p + "/*"),
                                                  joined(1, 2).map(lambda p: inside + p)), max_size=2)))
    endings = draw(st.sampled_from([(), (".nii",), (".csv", ".nii")])) if path.endswith("*") else ()
    kinds = draw(st.sampled_from([(), ("anat",)])) if path.endswith("*") else ()
    return Rule(path, draw(st.one_of(ACTIONS, st.just("*"))), draw(ENDS), excluded, endings, kinds,
                path[:-1] if kinds else "", "BIDS" if kinds else "")


VALID_RULES = st.lists(valid_rule(), max_size=6)
PATHS = st.tuples(joined(1, 4), st.sampled_from(["", "/"])).map("".join)


@settings(max_examples=2000)
@given(rules=VALID_RULES, path=PATHS, action=ACTIONS)
def test_checker_agrees_with_the_definition(rules, path, action):
    allows(rules, path, action)
    shows_folder(rules, path, action)


@given(rules=VALID_RULES, paths=st.lists(PATHS, max_size=20), action=ACTIONS)
def test_split_partitions_paths_by_allows(rules, paths, action):
    checker = Checker(rules)
    allowed, denied = checker.split(paths, action)
    assert allowed == [p for p in paths if checker.allows(p, action)]
    assert denied == [p for p in paths if not checker.allows(p, action)]


@given(rules=VALID_RULES, path=PATHS, action=ACTIONS)
def test_acting_on_a_folder_implies_it_is_shown(rules, path, action):
    checker = Checker(rules)
    if path.endswith("/") and checker.allows(path, action):
        assert checker.shows_folder(path, action)


@given(rules=VALID_RULES, path=PATHS, action=ACTIONS)
def test_the_rules_covering_a_path_are_exactly_the_reason_it_is_allowed(rules, path, action):
    """AC-3. What check-access reports: some rule covers the path exactly when the user may act on it."""
    assert bool(covering(rules, path, action)) == Checker(rules).allows(path, action)


@given(entered=st.text(alphabet="ab/*.[", max_size=12))
def test_saving_is_stable(entered):
    try:
        saved = normalize_rule_path(entered)
    except ValueError:
        return
    assert normalize_rule_path(saved) == saved


def test_no_decision_goes_through_casbins_own_matcher():
    """AC-3, AC-8. Casbin stores policies; rules.py decides. Casbin's matcher ignores a policy's
    conditions (its end date), so a call to enforce() would grant what an ended policy no longer
    does. Declaring the conditions field in model.conf makes enforce() fail rather than grant."""
    backend = Path(__file__).resolve().parents[1]
    callers = [str(f.relative_to(backend)) for d in ("api", "core") for f in (backend / d).rglob("*.py")
               if ".enforce(" in f.read_text()]
    assert callers == []


def test_stored_policies_read_back_with_and_without_conditions():
    """AC-6, AC-8, AC-10. Rows saved before policies had conditions have four fields; newer ones may have five."""
    from core.services.policies.casbin.CasbinPolicyManager import policy_from_row
    user, instance = "3ad5aedb-dd63-418a-ae55-a67a455e2e4b", "ded55682-2208-4584-a324-ef15d47c4601"
    assert policy_from_row([user, instance, "b/x", "read"]).ends is None
    ended = policy_from_row([user, instance, "b/y/*", "read", '{"ends": "2027-06-30"}'])
    assert (ended.resource, ended.ends) == ("b/y/*", datetime.date(2027, 6, 30))
    leaving = policy_from_row([user, instance, "b/y/*", "read", '{"except": ["b/y/z/*"], "endings": [".nii"]}'])
    assert (leaving.ends, leaving.excluded, leaving.endings) == (None, ["b/y/z/*"], [".nii"])


def test_a_file_one_policy_skips_for_its_ending_is_still_checked_against_a_policy_further_in():
    """AC-6, AC-10. Policies with conditions at two depths: a file outside the outer one's endings is
    still allowed by the inner one."""
    rules = [Rule("study/*", "read", endings=(".nii",)),
             Rule("study/sub/*", "read", excluded=("study/sub/private.csv",))]
    assert allows(rules, "study/sub/scan.csv", "read")
    assert not allows(rules, "study/sub/private.csv", "read")
    assert not allows(rules, "study/notes.csv", "read")


def test_a_policy_names_one_action_or_every_action():
    """AC-1, AC-5. An action is one word in lower case, or "*" for every action; a pattern such as
    ".*" (what stored policies used before INN-297) or a list of actions is refused."""
    assert validate_rule_action(" read ") == "read"
    assert validate_rule_action("*") == "*"
    for refused in (".*", "read,write", "Read", "re ad", ""):
        with pytest.raises(ValueError):
            validate_rule_action(refused)


def test_a_policys_conditions_read_back_as_they_were_saved():
    """AC-6, AC-8, AC-10. The conditions stored with a policy read back as the same rule."""
    full = Rule("study/*", "read", datetime.date(2027, 6, 30), ("study/private/*",), (".nii",), ("anat",),
                "study/", "BIDS")
    plain = Rule("study/*", "read")
    for rule in (full, plain, full._replace(kinds=(), dataset="", standard=""), full._replace(ends=None)):
        assert rule_from_stored(rule.path, rule.action, conditions_json(rule)) == rule
    assert conditions_json(plain) == ""  # a policy without conditions keeps its four fields


def test_a_folder_named_like_the_policys_folder_is_not_inside_it():
    """AC-10. "study-2/x" starts like "study/*" but isn't inside it, so it can't be left out of it."""
    assert validate_excluded("study/*", ["study/x"]) == ("study/x",)
    with pytest.raises(ValueError):
        validate_excluded("study/*", ["study-2/x"])


def test_a_file_ending_is_a_dot_and_at_least_one_character():
    """AC-6. ".r" is an ending and "." alone isn't; endings are kept in lower case, without blanks or repeats."""
    assert validate_endings("study/*", [".R", " .r ", "", ".nii"]) == (".r", ".nii")
    with pytest.raises(ValueError):
        validate_endings("study/*", ["."])
