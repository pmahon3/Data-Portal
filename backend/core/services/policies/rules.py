"""
Decide what a user's stored policies allow.

A policy gives one user one action ("read", "write", "delete", or "*" for all) on one literal path:
``bucket/path/file.txt`` (that file), ``bucket/folder/*`` (the folder and everything in it) or ``*``
(the whole instance). It may end on a date (AC-8), and a folder policy may leave out paths inside it
(AC-10) or cover only some file endings or kinds of data (AC-6). These conditions are stored as JSON
in the policy's fifth field (``model.conf``); only this module reads them.

``rule_allows`` and ``rule_shows_folder`` define one policy. ``Checker`` applies all of a user's
policies at once, indexed by folder so a decision stays fast however many they hold (AC-11).

Requirements: AC-1, AC-2, AC-3, AC-5, AC-6, AC-8, AC-10, AC-11 (docs/requirements/access-control.md).
"""
from __future__ import annotations

import datetime
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from casbin.util.builtin_operators import key_match

from core.services.standards import kind_of, standard as find_standard

ALL = "*"


class Rule(NamedTuple):
    path: str
    action: str
    ends: datetime.date | None = None  # the last day it applies; None for no end
    excluded: tuple[str, ...] = ()  # paths inside a folder policy that it leaves out
    endings: tuple[str, ...] = ()  # if any, only files ending in one (lower case)
    kinds: tuple[str, ...] = ()  # if any, only files of these kinds of data,
    dataset: str = ""  # as the standard of the dataset rooted here ("bucket/folder/")
    standard: str = ""  # defines them (e.g. "BIDS")


def today() -> datetime.date:
    """Return the day policies are judged by, in UTC so every backend process agrees."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def in_force(rule: Rule, on: datetime.date | None = None) -> bool:
    """Return whether the rule applies on that day (today by default): no end, or not yet passed."""
    if rule.ends is None:
        return True
    return rule.ends >= (on or today())


def conditions_json(rule: Rule) -> str:
    """Return the rule's conditions as stored in the policy's fifth field; "" when it has none."""
    conditions = {}
    if rule.ends:
        conditions["ends"] = rule.ends.isoformat()
    if rule.excluded:
        conditions["except"] = list(rule.excluded)
    if rule.endings:
        conditions["endings"] = list(rule.endings)
    if rule.kinds:
        conditions["kinds"] = list(rule.kinds)
        conditions["dataset"] = rule.dataset
        conditions["standard"] = rule.standard
    if not conditions:
        return ""
    return json.dumps(conditions)


def rule_from_stored(path: str, action: str, conditions: str | None = "") -> Rule:
    """Build a rule from a stored policy row."""
    stored = json.loads(conditions) if conditions else {}
    ends = stored.get("ends")
    return Rule(
        path,
        action,
        ends=datetime.date.fromisoformat(ends) if ends else None,
        excluded=tuple(stored.get("except", ())),
        endings=tuple(stored.get("endings", ())),
        kinds=tuple(stored.get("kinds", ())),
        dataset=stored.get("dataset", ""),
        standard=stored.get("standard", ""),
    )


def excludes(rule: Rule, path: str) -> bool:
    """Return whether the rule leaves `path` out: it's an exclusion, or inside an excluded folder."""
    return any(key_match(path, excluded) for excluded in rule.excluded)


def matches_file_types(rule: Rule, path: str) -> bool:
    """
    Return whether `path` is of the rule's file types. A folder always is; a file must end in one of
    the rule's endings (in any case) and be one of its kinds of data, when it has any.
    """
    if path.endswith("/"):
        return True
    if rule.endings and not path.lower().endswith(rule.endings):
        return False
    if rule.kinds:
        if not path.startswith(rule.dataset):
            return False
        # Example: dataset "study/", path "study/sub-01/anat/x.nii" -> kind of "/sub-01/anat/x.nii"
        inside = "/" + path[len(rule.dataset):]
        if kind_of(rule.standard, inside) not in rule.kinds:
            return False
    return True


def covers(rule: Rule, path: str) -> bool:
    """
    Return whether the rule covers `path`: its path names it exactly or as a folder ending in "/*",
    it doesn't leave it out, and it's of the rule's file types.
    """
    return key_match(path, rule.path) and not excludes(rule, path) and matches_file_types(rule, path)


def rule_allows(rule: Rule, path: str, action: str) -> bool:
    """Return whether the rule is in force, is for `action`, and covers `path`."""
    return in_force(rule) and rule.action in (action, ALL) and covers(rule, path)


def rule_shows_folder(rule: Rule, folder: str, action: str) -> bool:
    """
    Return whether `folder` appears when browsing for `action`: the rule is in force and for that
    action, and covers the folder or something inside it. Seeing a folder doesn't allow acting on it.
    """
    if not in_force(rule) or rule.action not in (action, ALL) or not folder.endswith("/"):
        return False
    if covers(rule, folder):
        return True
    # Example: rule "b/x/y/*" shows "b/", "b/x/" and "b/x/y/"
    head = rule.path.split(ALL, 1)[0]
    return head.startswith(folder)


def covering(rules: Iterable[Rule], path: str, action: str) -> list[Rule]:
    """
    Return the rules that allow `action` on `path`, in the order given: why a user may do it. Empty
    when none does; policies only add up, so nothing else decides it.

    Example: rules "b/x/*" (read) and "b/x/f.txt" (*) both cover reading "b/x/f.txt"
    """
    found = []
    for rule in rules:
        if rule_allows(rule, path, action):
            found.append(rule)
    return found


def validate_excluded(path: str, excluded: Iterable[str]) -> tuple[str, ...]:
    """
    Return the saved form of what a policy on `path` leaves out. Each is a policy path strictly inside
    the policy's folder, and only a folder policy ("folder/*") or "*" can leave anything out.

    Raises ValueError otherwise.
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
    Return the saved form of a policy path: no leading "/", no repeated "/".

    Raises ValueError unless "*" is used on its own or as the last part of a folder path, since
    anywhere else Casbin's key_match would ignore what follows it and silently widen the policy; and
    for a path ending in "/", which names no file (a folder is "folder/*").
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
    """Return a single action name, or "*" for every action. Raises ValueError otherwise."""
    action = action.strip()
    if action != ALL and not (action.isalpha() and action.islower()):
        raise ValueError("The action must be a single action (e.g. 'read') or '*'.")
    return action


def _distinct_lower(values: Iterable[str]) -> tuple[str, ...]:
    """Return the non-blank values, stripped and in lower case, without repeats, in their order."""
    distinct = []
    for value in values:
        value = value.strip().lower()
        if value and value not in distinct:
            distinct.append(value)
    return tuple(distinct)


def validate_endings(path: str, endings: Iterable[str]) -> tuple[str, ...]:
    """
    Return the saved form of the file endings a policy on `path` is limited to: each starts with "."
    and has no "/" or "*", kept in lower case. Only a folder policy ("folder/*") or "*" can have them.

    Raises ValueError otherwise.
    """
    saved = _distinct_lower(endings)
    if saved and not path.endswith(ALL):
        raise ValueError("Only a folder policy (ending in '/*') or '*' can be limited to file endings.")
    for e in saved:
        if not e.startswith(".") or len(e) < 2 or "/" in e or ALL in e:
            raise ValueError(f"'{e}' isn't a file ending: write it like '.nii' or '.nii.gz'.")
    return saved


def validate_kinds(path: str, kinds: Iterable[str], dataset: str | None, standard: str) -> tuple[str, ...]:
    """
    Return the saved form of the kinds of data a policy on `path` is limited to. The policy must be a
    folder policy at or inside `dataset`, the root ("bucket/folder/") of a dataset declaring
    `standard`, and each kind one that standard defines.

    Raises ValueError otherwise.
    """
    saved = _distinct_lower(kinds)
    if not saved:
        return saved
    if not path.endswith("/" + ALL):
        raise ValueError("Only a folder policy (ending in '/*') can be limited to kinds of data.")
    if not dataset or not path[:-1].startswith(dataset):
        raise ValueError(
            f"'{path}' isn't inside a dataset that declares a standard, so it has no kinds of data."
        )
    defined = find_standard(standard)
    unknown = [k for k in saved if defined is None or k not in defined.kinds]
    if unknown:
        raise ValueError(f"{standard} doesn't define {', '.join(unknown)} as a kind of data.")
    return saved


# --- the indexed checker ---


class _Conditioned(NamedTuple):
    """A rule with conditions, its exclusions split into files and folders for lookup."""

    rule: Rule
    excluded_files: frozenset[str]
    excluded_folders: frozenset[str]  # "bucket/folder/"

    @classmethod
    def of(cls, rule: Rule) -> _Conditioned:
        files = frozenset(e for e in rule.excluded if not e.endswith("/*"))
        folders = frozenset(e[:-1] for e in rule.excluded if e.endswith("/*"))
        return cls(rule, files, folders)

    def covers(self, path: str, folders: list[str]) -> bool:
        """Return covers(rule, path) for a path inside the rule's folder, given the folders it's in."""
        if not matches_file_types(self.rule, path):
            return False
        if path in self.excluded_files:
            return False
        return self.excluded_folders.isdisjoint(folders)


def _endings_any(group: list[_Conditioned]) -> tuple[str, ...] | None:
    """Return every ending the group's rules accept, or None if one of them accepts any name."""
    endings = set()
    for conditioned in group:
        if not conditioned.rule.endings:
            return None
        endings.update(conditioned.rule.endings)
    return tuple(endings)


def _folders_of(path: str) -> list[str]:
    """
    Return the folders `path` is in, outermost first, ending with `path` itself if it's a folder.

    Example: "a/b/c" -> ["a/", "a/b/"]; "a/b/" -> ["a/", "a/b/"]
    """
    found = []
    i = path.find("/")
    while i != -1:
        found.append(path[: i + 1])
        i = path.find("/", i + 1)
    return found


def _head(rule: Rule) -> str:
    """
    Return the key a rule is indexed under: "" for everything, the folder for a folder policy, else
    the file's path.

    Example: "*" -> ""; "b/x/*" -> "b/x/"; "b/x/f.txt" -> "b/x/f.txt"
    """
    if rule.path == ALL:
        return ""
    if rule.path.endswith("/*"):
        return rule.path[:-1]
    return rule.path


class Checker:
    """
    Decide for all of a user's rules on one storage instance that are in force today.

    Rules are indexed by action and by the folder each covers, so a path costs one lookup per folder
    it's in however many rules the user holds. Rules with conditions are indexed the same way and
    checked only for paths inside their folder (AC-11).
    """

    def __init__(self, rules: Iterable[Rule]):
        self._everything: set[str] = set()  # actions held on the whole instance
        self._exact: dict[str, set[str]] = defaultdict(set)  # action -> exact paths
        self._folders: dict[str, set[str]] = defaultdict(set)  # action -> "bucket/folder/"
        self._above: dict[str, set[str]] = defaultdict(set)  # action -> folders above a rule's path
        conditioned: dict[str, dict[str, list[_Conditioned]]] = defaultdict(lambda: defaultdict(list))
        on = today()
        for rule in rules:
            if not in_force(rule, on):
                continue
            head = _head(rule)
            if rule.excluded or rule.endings or rule.kinds:
                conditioned[rule.action][head].append(_Conditioned.of(rule))
            elif rule.path == ALL:
                self._everything.add(rule.action)
            elif rule.path.endswith("/*"):
                self._folders[rule.action].add(head)
            else:
                self._exact[rule.action].add(head)
            self._above[rule.action].update(_folders_of(head))
        # action -> head -> (the endings one of its rules needs, or None if one takes any name; the
        # rules), so a file matching none of a folder's endings skips all its rules at once
        self._conditioned: dict[str, dict[str, tuple[tuple[str, ...] | None, list[_Conditioned]]]] = {}
        for action, by_head in conditioned.items():
            self._conditioned[action] = {}
            for head, group in by_head.items():
                self._conditioned[action][head] = (_endings_any(group), group)

    def allows(self, path: str, action: str) -> bool:
        """Return whether the user may do `action` on `path`."""
        folders = _folders_of(path)
        for act in (action, ALL):
            if act in self._everything or path in self._exact.get(act, ()):
                return True
            held = self._folders.get(act)
            if held and not held.isdisjoint(folders):
                return True
        return self._conditioned_allows(path, action, folders)

    def _conditioned_allows(self, path: str, action: str, folders: list[str]) -> bool:
        is_folder = path.endswith("/")
        heads = ["", *folders] if is_folder else ["", *folders, path]
        lower = path.lower()
        for act in (action, ALL):
            by_head = self._conditioned.get(act)
            if not by_head:
                continue
            for head in heads:
                endings, group = by_head.get(head, (None, ()))
                if endings and not is_folder and not lower.endswith(endings):
                    continue
                for conditioned in group:
                    if conditioned.covers(path, folders):
                        return True
        return False

    def shows_folder(self, folder: str, action: str) -> bool:
        """Return whether `folder` appears when the user browses for `action`."""
        if not folder.endswith("/"):
            return False
        return (
            self.allows(folder, action)
            or folder in self._above.get(action, ())
            or folder in self._above.get(ALL, ())
        )

    def split(self, paths: Iterable[str], action: str) -> tuple[list[str], list[str]]:
        """Return the paths the user may and may not act on, in the order given."""
        allowed = []
        denied = []
        for path in paths:
            if self.allows(path, action):
                allowed.append(path)
            else:
                denied.append(path)
        return allowed, denied
