"""
What a stored policy allows.

A policy gives one user one action on one path of a storage instance. The path is literal:
  - "bucket/path/file.txt"  exactly that file
  - "bucket/folder/*"       that folder and everything in it
  - "*"                     everything on the instance
The action is a single action ("read", "write", "delete") or "*" for every action.
A policy may also end: from the day after its end date it allows and shows nothing (AC-8). A folder
policy may leave out files or folders inside it, which it then neither allows nor shows; another
policy can still give them (AC-10). And a folder policy may be limited to files whose names end in
given endings, such as ".nii"; it still covers the folders inside, so they can be browsed and
uploaded into (AC-6), or to kinds of data as its dataset's standard defines them (BIDS: "anat",
"func"), worked out from each file's path inside the dataset (AC-6). These conditions are stored as JSON in the policy's fifth field
(model.conf); only this module reads them.

Two questions are asked of a user's policies:
  - allows(path, action): may the user do `action` on `path`?
  - shows_folder(folder, action): should `folder` appear when the user browses for `action`?
    Yes if the user may act on the folder, or on something inside it. Seeing a folder
    doesn't allow acting on it.

rule_allows and rule_shows_folder define the rule for one policy. Checker applies it to all of
a user's policies at once, indexed so each path costs a few set lookups however many policies
the user holds; tests check that the two agree.

Requirements AC-1, AC-2, AC-3, AC-5, AC-6, AC-8 and AC-10 in docs/requirements/access-control.md.
"""
import datetime
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from casbin.util.builtin_operators import key_match

ALL = "*"


class Rule(NamedTuple):
    path: str
    action: str
    ends: datetime.date | None = None  # the last day it applies; None for no end
    excluded: tuple[str, ...] = ()       # paths inside a folder policy that it leaves out
    endings: tuple[str, ...] = ()        # if any, a folder policy covers only files ending in one (lower case)
    kinds: tuple[str, ...] = ()          # if any, a folder policy covers only files of these kinds of data,
    dataset: str = ""                    # as the standard of the dataset rooted here ("bucket/folder/")
    standard: str = ""                   # defines them (e.g. "BIDS")


def today() -> datetime.date:
    """The day policies are judged by, in UTC, so every backend process agrees."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def in_force(rule: Rule, on: datetime.date | None = None) -> bool:
    """The rule applies on that day (today by default): it has no end, or its end date is today or later."""
    return rule.ends is None or rule.ends >= (on or today())


def conditions_json(rule: Rule) -> str:
    """The rule's conditions as stored in the policy's fifth field; "" when it has none."""
    conditions = {}
    if rule.ends:
        conditions["ends"] = rule.ends.isoformat()
    if rule.excluded:
        conditions["except"] = list(rule.excluded)
    if rule.endings:
        conditions["endings"] = list(rule.endings)
    if rule.kinds:
        conditions.update(kinds=list(rule.kinds), dataset=rule.dataset, standard=rule.standard)
    return json.dumps(conditions) if conditions else ""


def rule_from_stored(path: str, action: str, conditions: str | None = "") -> Rule:
    """A rule from a stored policy row."""
    stored = json.loads(conditions) if conditions else {}
    ends = stored.get("ends")
    return Rule(path, action, datetime.date.fromisoformat(ends) if ends else None, tuple(stored.get("except", ())),
                tuple(stored.get("endings", ())), tuple(stored.get("kinds", ())), stored.get("dataset", ""),
                stored.get("standard", ""))


def leaves_out(rule: Rule, path: str) -> bool:
    """`path` is one of the rule's exclusions, or inside an excluded folder."""
    return any(key_match(path, excluded) for excluded in rule.excluded)


def of_its_types(rule: Rule, path: str) -> bool:
    """`path` is a folder, or a file whose name ends in one of the rule's endings (any case, if it has
    any) and whose kind is one of the rule's kinds (if it has any)."""
    if path.endswith("/"):
        return True
    if rule.endings and not path.lower().endswith(rule.endings):
        return False
    if rule.kinds:
        from core.services.standards import kind_of

        if not path.startswith(rule.dataset) or kind_of(rule.standard, "/" + path[len(rule.dataset):]) not in rule.kinds:
            return False
    return True


def covers(rule: Rule, path: str) -> bool:
    """The rule's path covers `path`, exactly or as a folder ending in "/*", without leaving it out,
    and `path` is of the rule's file types."""
    return key_match(path, rule.path) and not leaves_out(rule, path) and of_its_types(rule, path)


def rule_allows(rule: Rule, path: str, action: str) -> bool:
    """The rule is in force, is for `action`, and covers `path`."""
    return in_force(rule) and rule.action in (action, ALL) and covers(rule, path)


def rule_shows_folder(rule: Rule, folder: str, action: str) -> bool:
    """The rule is in force and for `action`, and `folder` is covered by it or lies above what it covers."""
    if not in_force(rule) or rule.action not in (action, ALL) or not folder.endswith("/"):
        return False
    return covers(rule, folder) or rule.path.split(ALL, 1)[0].startswith(folder)


def validate_excluded(path: str, excluded: Iterable[str]) -> tuple[str, ...]:
    """
    The saved form of what a policy on `path` leaves out. Each is a policy path (normalized like
    one) strictly inside the policy's folder; only a folder policy ("folder/*") or "*" can leave
    anything out. Raises ValueError otherwise.
    """
    saved = tuple(normalize_rule_path(e) for e in excluded)
    if saved and not path.endswith(ALL):
        raise ValueError("Only a folder policy (ending in '/*') or '*' can leave things out.")
    inside = path[:-1]
    for e in saved:
        if e == path or not e.startswith(inside) or e == ALL:
            raise ValueError(f"'{e}' isn't inside '{path}', so it can't be left out of it.")
    return saved


def normalize_rule_path(path: str) -> str:
    """
    The saved form of a policy path: no leading "/", no repeated "/".
    Raises ValueError unless "*" is used on its own or as the last part of a folder path, since
    anywhere else Casbin's key_match would ignore what follows it and silently widen the policy;
    and for a path ending in "/", which names no file (a folder is "folder/*").
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
    if path.endswith("/"):
        raise ValueError(f"A folder path ends in '/*' (e.g. '{path}*'); '{path}' names no file.")
    return path


def validate_rule_action(action: str) -> str:
    """A single action name, or "*" for every action."""
    action = action.strip()
    if action != ALL and not (action.isalpha() and action.islower()):
        raise ValueError("The action must be a single action (e.g. 'read') or '*'.")
    return action


def validate_endings(path: str, endings: Iterable[str]) -> tuple[str, ...]:
    """
    The saved form of the file endings a policy on `path` is limited to: each starts with "." and
    has no "/" or "*", kept in lower case. Only a folder policy ("folder/*") or "*" can have them.
    Raises ValueError otherwise.
    """
    saved = tuple(dict.fromkeys(e.strip().lower() for e in endings if e.strip()))
    if saved and not path.endswith(ALL):
        raise ValueError("Only a folder policy (ending in '/*') or '*' can be limited to file endings.")
    for e in saved:
        if not e.startswith(".") or len(e) < 2 or "/" in e or ALL in e:
            raise ValueError(f"'{e}' isn't a file ending: write it like '.nii' or '.nii.gz'.")
    return saved


def validate_kinds(path: str, kinds: Iterable[str], dataset: str | None, standard: str) -> tuple[str, ...]:
    """
    The saved form of the kinds of data a policy on `path` is limited to. The policy must be a folder
    policy at or inside `dataset`, the root ("bucket/folder/") of a dataset declaring `standard`, and
    each kind one that standard defines. Raises ValueError otherwise.
    """
    from core.services.standards import standard as find_standard

    saved = tuple(dict.fromkeys(k.strip().lower() for k in kinds if k.strip()))
    if not saved:
        return saved
    if not path.endswith("/" + ALL):
        raise ValueError("Only a folder policy (ending in '/*') can be limited to kinds of data.")
    if not dataset or not path[:-1].startswith(dataset):
        raise ValueError(f"'{path}' isn't inside a dataset that declares a standard, so it has no kinds of data.")
    defined = find_standard(standard)
    unknown = [k for k in saved if defined is None or k not in defined.kinds]
    if unknown:
        raise ValueError(f"{standard} doesn't define {', '.join(unknown)} as a kind of data.")
    return saved


class Checker:
    """A user's rules on one storage instance that are in force today, indexed by action."""

    def __init__(self, rules: Iterable[Rule]):
        self._everything: set[str] = set()                  # actions held on the whole instance
        self._exact: dict[str, set[str]] = defaultdict(set)    # action -> exact paths
        self._folders: dict[str, set[str]] = defaultdict(set)  # action -> "bucket/folder/"
        self._above: dict[str, set[str]] = defaultdict(set)    # action -> folders above a rule's path
        self._leaving_out: list[Rule] = []                      # rules with exclusions or endings, checked one by one
        on = today()
        for rule in rules:
            if not in_force(rule, on):
                continue
            if rule.excluded or rule.endings or rule.kinds:
                self._leaving_out.append(rule)
                continue
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
        if any(rule_allows(rule, path, action) for rule in self._leaving_out):
            return True
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
            any(rule_shows_folder(rule, folder, action) for rule in self._leaving_out)
            or self.allows(folder, action)
            or folder in self._above.get(action, ())
            or folder in self._above.get(ALL, ())
        )

    def split(self, paths: Iterable[str], action: str) -> tuple[list[str], list[str]]:
        """The paths the user may and may not act on, in the order given."""
        allowed, denied = [], []
        for path in paths:
            (allowed if self.allows(path, action) else denied).append(path)
        return allowed, denied
