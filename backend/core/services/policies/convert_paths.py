"""
Rewrite stored policy paths from regular expressions to literal paths. Run once per
environment before deploying the literal matcher; it reports first and changes nothing unless asked.

    python -m core.services.policies.convert_paths           # report
    python -m core.services.policies.convert_paths --apply   # rewrite what can be rewritten

A path that only uses regular expressions the way the policy form suggested (".*" for everything,
"folder/.*" for a folder) is rewritten ("*", "folder/*"), without the leading "/" the form also
suggested. Anything else that looks like a pattern is listed for a person to rewrite by hand.
"""

import sys

from core.db import get_mongo_database
from core.utils.policy_paths import saved_policy_action, saved_policy_path

PATTERN_CHARACTERS = set("*+?[](){}|^$\\")


def literal(path: str) -> str | None:
    """The literal form of a stored policy path, or None if a person has to rewrite it.

    Example: ".*" -> "*"; "/bucket/folder/.*" -> "bucket/folder/*"; "bucket/a.txt" -> "bucket/a.txt"
    """
    # The policy form used to suggest a leading "/", which made a policy match nothing
    path = path.lstrip("/")
    if path == ".*":
        return "*"
    stem, wildcard = (path[:-2], "*") if path.endswith("/.*") else (path, "")
    if PATTERN_CHARACTERS & set(stem):
        return None
    try:
        # A converted path must be one a new policy could be saved with
        return saved_policy_path(stem + wildcard)
    except ValueError:
        return None


def literal_action(action: str) -> str | None:
    """The stored form of a policy action, or None if a person has to rewrite it.

    Example: ".*" -> "*"; "read" -> "read"; "read|write" -> None
    """
    if action == ".*":
        return "*"
    try:
        return saved_policy_action(action)
    except ValueError:
        return None


def main(apply: bool) -> int:
    rules = get_mongo_database()["casbin_rule"]
    review = 0
    for rule in rules.find({"ptype": "p"}):
        path, action = rule.get("v2", ""), rule.get("v3", "")
        new_path, new_action = literal(path), literal_action(action)
        if new_path is None or new_action is None:
            review += 1
            print(
                f"review by hand: user {rule.get('v0')} instance {rule.get('v1')} "
                f"path {path!r} action {action!r}"
            )
        elif (new_path, new_action) != (path, action):
            verb = "rewrote" if apply else "would rewrite"
            print(f"{verb} {path!r} {action!r} -> {new_path!r} {new_action!r}")
            if apply:
                rules.update_one({"_id": rule["_id"]}, {"$set": {"v2": new_path, "v3": new_action}})
    print(f"{review} path(s) to review by hand")
    return 1 if review else 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv[1:]))
