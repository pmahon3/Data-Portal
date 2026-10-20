"""
Steps for features/access_rules.feature, plus property tests for the decision layer.

Every check runs through both the definition (rule_allows, rule_shows_folder) and the indexed
Checker, so the scenarios also test that the two agree.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios, then, when

from core.services.policies.rules import (
    Checker,
    Rule,
    normalize_rule_path,
    rule_allows,
    rule_shows_folder,
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


@bdd_given(parsers.parse('the user holds "{action}" on "{path}"'))
def user_holds(rules, action, path):
    rules.append(Rule(path, action))


@then(parsers.re(r'the user (?P<may>may|may not) "(?P<action>[^"]*)" "(?P<path>[^"]*)"'))
def user_may(rules, may, action, path):
    assert allows(rules, path, action) == (may == "may")


@then(parsers.re(r'the folder "(?P<folder>[^"]*)" is (?P<shown>shown|not shown) when browsing to "(?P<action>[^"]*)"'))
def folder_shown(rules, folder, shown, action):
    assert shows_folder(rules, folder, action) == (shown == "shown")


@when(parsers.parse('an administrator saves a policy on "{entered}"'), target_fixture="saved")
def save_policy(entered):
    try:
        return normalize_rule_path(entered)
    except ValueError as error:
        return error


@then(parsers.parse('it is saved as "{expected}"'))
def saved_as(saved, expected):
    assert saved == expected


@then("it is refused")
def refused(saved):
    assert isinstance(saved, ValueError)


# Property tests: the indexed Checker gives the same answers as the definition for any valid
# rules and any path, and saving is stable.

SEGMENTS = st.sampled_from(["a", "b", "study", "p7", "sub-07", "x.nii", "y.csv", "a[b", "(c)"])
ACTIONS = st.sampled_from(["read", "write", "delete"])


def joined(min_size, max_size):
    return st.lists(SEGMENTS, min_size=min_size, max_size=max_size).map("/".join)


VALID_RULES = st.lists(
    st.builds(
        Rule,
        st.one_of(st.just("*"), joined(1, 3).map(lambda p: p + "/*"), joined(1, 4)),
        st.one_of(ACTIONS, st.just("*")),
    ),
    max_size=6,
)
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


@given(entered=st.text(alphabet="ab/*.[", max_size=12))
def test_saving_is_stable(entered):
    try:
        saved = normalize_rule_path(entered)
    except ValueError:
        return
    assert normalize_rule_path(saved) == saved
