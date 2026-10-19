"""
One-off conversion of stored policies from regular expressions to literal paths (INN-297).

Report first (changes nothing):
    python -m core.services.policies.convert_paths
Then, after the report has been reviewed, apply the automatic conversions:
    python -m core.services.policies.convert_paths --apply

Only rows whose meaning is clear are changed. Rows that would grant new access, or whose
meaning is ambiguous, are listed and left as they are for an administrator to fix by hand.
"""
import argparse
from collections import Counter
from typing import NamedTuple

from core.services.policies.rules import ALL

# Characters that made a stored path a pattern. "." is left out: in a file name it was meant
# literally, and reading it literally only narrows what the policy matched.
PATTERN_CHARACTERS = set("^$*+?()[]{}|\\")

CONVERT = "convert"      # applied by --apply
UNCHANGED = "unchanged"  # already literal; nothing to write
NARROWS = "narrows"      # stays as it is, but now matches less than before (no new access)
REVIEW = "review"        # left as it is; an administrator decides


class Conversion(NamedTuple):
    kind: str
    path: str
    action: str
    note: str


def convert(path: str, action: str) -> Conversion:
    """How one stored policy's path and action convert."""
    new_action, action_note = _convert_action(action)
    if new_action is None:
        return Conversion(REVIEW, path, action, action_note)

    if path == ".*":
        return Conversion(CONVERT, ALL, new_action, "everything on the instance")
    if path.startswith("/"):
        return Conversion(
            REVIEW, path, action,
            "starts with '/', so it grants nothing today; removing the '/' would grant new access",
        )
    if path.endswith("/.*") and not PATTERN_CHARACTERS & set(path[:-2]):
        return Conversion(CONVERT, path[:-2] + ALL, new_action, "folder and everything in it")
    if path.endswith(".*"):
        return Conversion(
            REVIEW, path, action,
            "matches every name starting with a partial name; choose a folder ('…/*') or files",
        )
    if PATTERN_CHARACTERS & set(path):
        return Conversion(REVIEW, path, action, "a pattern with no literal equivalent")
    if path.endswith("/"):
        return Conversion(
            REVIEW, path, action,
            "a folder path without '*': today it matches the folder and everything in it; "
            "use '…/*' if that's intended",
        )
    if new_action != action:
        return Conversion(CONVERT, path, new_action, "action")
    return Conversion(
        NARROWS, path, action,
        "now exactly this file; before, it also matched longer names starting with it",
    )


def _convert_action(action: str) -> tuple[str | None, str]:
    if action == ".*":
        return ALL, "every action"
    if PATTERN_CHARACTERS & set(action) or "." in action:
        return None, "the action is a pattern"
    return action, ""


def main() -> None:
    from core.db.mongodb.mongo_client import get_policy_rule_collection

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the automatic conversions")
    args = parser.parse_args()

    collection = get_policy_rule_collection()
    counts = Counter()
    for row in collection.find({"ptype": "p"}):
        result = convert(row.get("v2", ""), row.get("v3", ""))
        counts[result.kind] += 1
        print(f"{result.kind:9}  user {row.get('v0')}  instance {row.get('v1')}  "
              f"{row.get('v2')!r} {row.get('v3')!r} -> {result.path!r} {result.action!r}  ({result.note})")
        if args.apply and result.kind == CONVERT:
            duplicate = collection.find_one({
                "ptype": "p", "v0": row.get("v0"), "v1": row.get("v1"),
                "v2": result.path, "v3": result.action,
            })
            if duplicate:
                collection.delete_one({"_id": row["_id"]})
            else:
                collection.update_one({"_id": row["_id"]}, {"$set": {"v2": result.path, "v3": result.action}})

    print("\n" + ", ".join(f"{kind}: {n}" for kind, n in sorted(counts.items())))
    if not args.apply:
        print("Report only; nothing was changed. Re-run with --apply to write the 'convert' rows.")
    else:
        print("Applied the 'convert' rows. Restart the backend so Casbin's policy listings reload.")


if __name__ == "__main__":
    main()
