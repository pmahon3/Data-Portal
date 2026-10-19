"""
What a stored policy allows.

A policy gives one user one action on one path of a storage instance. The path is literal:
  - "bucket/path/file.txt"  exactly that file
  - "bucket/folder/*"       that folder and everything in it
  - "*"                     everything on the instance
The action is a single action ("read", "write", "delete") or "*" for every action.

Two questions are asked of a user's policies:
  - allows(path, action): may the user do `action` on `path`?
  - shows_folder(folder, action): should `folder` appear when the user browses for `action`?
    Yes if the user may act on the folder, or on something inside it. Seeing a folder
    doesn't allow acting on it.

rule_allows and rule_shows_folder define the rule for one policy. Checker applies it to all of
a user's policies at once, indexed so each path costs a few set lookups however many policies
the user holds; tests check that the two agree.

Requirements AC-1, AC-2, AC-3 and AC-5 in docs/requirements/access-control.md.
"""
from collections import defaultdict
from typing import Iterable, NamedTuple

from casbin.util.builtin_operators import key_match

ALL = "*"


class Rule(NamedTuple):
    path: str
    action: str


def rule_allows(rule: Rule, path: str, action: str) -> bool:
    """The rule is for `action` and covers `path`: exactly, or as a folder ending in "/*"."""
    return rule.action in (action, ALL) and key_match(path, rule.path)


def rule_shows_folder(rule: Rule, folder: str, action: str) -> bool:
    """The rule is for `action`, and `folder` is covered by it or lies above what it covers."""
    if rule.action not in (action, ALL) or not folder.endswith("/"):
        return False
    return key_match(folder, rule.path) or rule.path.split(ALL, 1)[0].startswith(folder)


def normalize_rule_path(path: str) -> str:
    """
    The saved form of a policy path: no leading "/", no repeated "/".
    Raises ValueError unless "*" is used on its own or as the last part of a folder path, since
    anywhere else Casbin's key_match would ignore what follows it and silently widen the policy.
    """
    path = path.strip()
    while "//" in path:
        path = path.replace("//", "/")
    path = path.lstrip("/")
    if not path:
        raise ValueError("The resource path is empty.")
    if path != ALL and ALL in path and not (path.endswith("/*") and path.count(ALL) == 1):
        raise ValueError(
            "Use '*' on its own (everything) or as the last part of a folder path "
            "(e.g. 'bucket/folder/*'). Other paths name exactly one file."
        )
    return path


def validate_rule_action(action: str) -> str:
    """A single action name, or "*" for every action."""
    action = action.strip()
    if action != ALL and not (action.isalpha() and action.islower()):
        raise ValueError("The action must be a single action (e.g. 'read') or '*'.")
    return action


class Checker:
    """A user's rules on one storage instance, indexed by action."""

    def __init__(self, rules: Iterable[Rule]):
        self._everything: set[str] = set()                  # actions held on the whole instance
        self._exact: dict[str, set[str]] = defaultdict(set)    # action -> exact paths
        self._folders: dict[str, set[str]] = defaultdict(set)  # action -> "bucket/folder/"
        self._above: dict[str, set[str]] = defaultdict(set)    # action -> folders above a rule's path
        for rule in rules:
            if rule.path == ALL:
                self._everything.add(rule.action)
                continue
            if rule.path.endswith("/*"):
                head = rule.path[:-1]
                self._folders[rule.action].add(head)
            else:
                head = rule.path
                self._exact[rule.action].add(head)
            parts = head.split("/")
            for i in range(1, len(parts)):
                self._above[rule.action].add("/".join(parts[:i]) + "/")

    def allows(self, path: str, action: str) -> bool:
        for act in (action, ALL):
            if act in self._everything or path in self._exact.get(act, ()):
                return True
            folders = self._folders.get(act)
            if folders:
                i = path.find("/")
                while i != -1:
                    if path[: i + 1] in folders:
                        return True
                    i = path.find("/", i + 1)
        return False

    def shows_folder(self, folder: str, action: str) -> bool:
        if not folder.endswith("/"):
            return False
        return (
            self.allows(folder, action)
            or folder in self._above.get(action, ())
            or folder in self._above.get(ALL, ())
        )

    def split(self, paths: Iterable[str], action: str) -> tuple[list[str], list[str]]:
        """The paths the user may and may not act on, in the order given."""
        allowed, denied = [], []
        for path in paths:
            (allowed if self.allows(path, action) else denied).append(path)
        return allowed, denied
