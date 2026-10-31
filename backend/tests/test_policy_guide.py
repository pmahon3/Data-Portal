"""
The policy guide's "Does this policy allow it?" table (docs/user-guide/policies.md) is what the
portal decides: each row is evaluated with the decision layer itself, so the table people read and
the rules the portal applies can't drift apart.

Verifies: AC-1, AC-2, AC-5.
"""
import re
from pathlib import Path

import pytest

from core.services.policies.rules import Rule, normalize_rule_path, rule_allows, rule_shows_folder, \
    validate_rule_action

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "user-guide" / "policies.md"


KNOWN_FAILING = {"study-a/patient-7/": "policy-folder-path: a folder path without '/*' is saved, though it "
                                       "names no files"}


def rows():
    if not GUIDE.exists():  # e.g. inside the backend container, which mounts backend/ only
        return [pytest.param(*[""] * 5, marks=pytest.mark.skip(reason=f"needs the repository's docs/ ({GUIDE})"))]
    text = GUIDE.read_text()
    table = text.split("<!-- check: policy-examples", 1)[1].split("\n\n", 1)[0]
    found = []
    for line in table.splitlines()[3:]:
        cells = [re.sub(r"^`|`$", "", c.strip()) for c in line.strip().strip("|").split("|")]
        marks = [pytest.mark.xfail(strict=True, reason=KNOWN_FAILING[cells[0]])] if cells[0] in KNOWN_FAILING else []
        found.append(pytest.param(*cells, marks=marks))
    assert found, "the guide's example table is empty"
    return found


def decide(path, action, asked, about):
    rule = Rule(normalize_rule_path(path), validate_rule_action(action))
    if asked == "browse":
        return rule_shows_folder(rule, about, "read")
    return rule_allows(rule, about, asked)


@pytest.mark.parametrize("path, action, asked, about, answer", rows())
def test_the_guide_says_what_the_portal_decides(path, action, asked, about, answer):
    if answer == "refused":
        with pytest.raises(ValueError):
            normalize_rule_path(path)
        return
    assert decide(path, action, asked, about) == (answer == "yes")
