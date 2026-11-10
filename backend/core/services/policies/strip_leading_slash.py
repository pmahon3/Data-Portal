"""
Remove a leading "/" from stored policy paths. Policies saved with one grant nothing,
since requests are checked against "bucket/key". Run once per environment; it reports first and
changes nothing unless asked.

    python -m core.services.policies.strip_leading_slash           # report
    python -m core.services.policies.strip_leading_slash --apply   # rewrite
"""

import sys

from core.db import get_mongo_database


def main(apply: bool) -> None:
    rules = get_mongo_database()["casbin_rule"]
    for rule in rules.find({"ptype": "p", "v2": {"$regex": "^/"}}):
        path = rule["v2"]
        print(f"{'rewrote' if apply else 'would rewrite'} {path!r} -> {path.lstrip('/')!r}")
        if apply:
            rules.update_one({"_id": rule["_id"]}, {"$set": {"v2": path.lstrip("/")}})


if __name__ == "__main__":
    main("--apply" in sys.argv[1:])
