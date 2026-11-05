"""
Rewrite stored policy paths from regular expressions to literal paths (INN-297). Run once per
environment before deploying the literal matcher; it reports first and changes nothing unless asked.

    python -m core.services.policies.convert_paths           # report
    python -m core.services.policies.convert_paths --apply   # rewrite what can be rewritten

A path that only uses regular expressions the way the policy form suggested (".*" for everything,
"folder/.*" for a folder) is rewritten ("*", "folder/*"). Anything else that looks like a pattern is
listed for a person to rewrite by hand.
"""

import sys

from core.db import get_mongo_database

PATTERN_CHARACTERS = set("*+?[](){}|^$\\")


def literal(path: str) -> str | None:
    """The literal form of a stored policy path, or None if a person has to rewrite it.

    Example: ".*" -> "*"; "bucket/folder/.*" -> "bucket/folder/*"; "bucket/a.txt" -> "bucket/a.txt"
    """
    if path == ".*":
        return "*"
    stem, wildcard = (path[:-2], "*") if path.endswith("/.*") else (path, "")
    if PATTERN_CHARACTERS & set(stem):
        return None
    return stem + wildcard


def main(apply: bool) -> int:
    rules = get_mongo_database()["casbin_rule"]
    review = 0
    for rule in rules.find({"ptype": "p"}):
        path = rule.get("v2", "")
        new = literal(path)
        if new is None:
            review += 1
            print(f"review by hand: user {rule.get('v0')} instance {rule.get('v1')} path {path!r}")
        elif new != path:
            print(f"{'rewrote' if apply else 'would rewrite'} {path!r} -> {new!r}")
            if apply:
                rules.update_one({"_id": rule["_id"]}, {"$set": {"v2": new}})
    print(f"{review} path(s) to review by hand")
    return 1 if review else 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv[1:]))
