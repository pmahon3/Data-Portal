"""
Policy paths are literal: "bucket/path/file.txt" names one file, "bucket/folder/*" a folder and
everything in it, "*" everything on the storage instance. Casbin's keyMatch reads any other "*" as a
wildcard, so these checks keep every other kind of path out of the policy store, and keep requests
that could climb out of a folder out of decisions.
"""

from __future__ import annotations

ALL = "*"

# Casbin's MongoDB adapter joins a policy's fields with ", " and splits them again when it loads them,
# treating brackets as grouping. A path with a comma or an unmatched bracket would load as a different
# policy, or fail to load and stop every permission check. Matched brackets, as in "scan (1).nii", load.
PAIRS = {")": "(", "]": "["}


def has_matched_brackets(path: str) -> bool:
    """
    Return whether every bracket in the path is closed in order.

    Example: "scan (1).nii" -> True; "a[b.bin" -> False; "a)b.bin" -> False
    """
    open_brackets = []
    for character in path:
        if character in "([":
            open_brackets.append(character)
        elif character in PAIRS:
            if not open_brackets or open_brackets.pop() != PAIRS[character]:
                return False
    return not open_brackets


SHAPE = (
    "A policy path is a file (bucket/path/file.txt), a folder and everything in it (bucket/folder/*), "
    "or * for everything."
)


def saved_policy_path(path: str) -> str:
    """
    Return the path to store for a new policy. Raises ValueError, with the reason, for any other path.

    Example: "/bucket/study/*" -> "bucket/study/*"; "bucket/study*" -> ValueError
    """
    if path != path.strip():
        raise ValueError(f"{SHAPE} It can't start or end with a space.")
    # Requests are checked against "bucket/key", so a leading "/" would match nothing
    path = path.lstrip("/")
    if path == ALL:
        return path
    if path.endswith("/*"):
        body = path[:-2]
    else:
        body = path
    if not body or ALL in body:
        raise ValueError(f"{SHAPE} '*' can only be used on its own or as the last part of a folder.")
    for segment in body.split("/"):
        if segment in ("", ".", ".."):
            raise ValueError(f"{SHAPE} It can't contain empty, '.' or '..' parts, or end in '/'.")
    if "," in path or not has_matched_brackets(path) or any(ord(character) < 32 for character in path):
        raise ValueError(
            f"{SHAPE} It can't contain a comma, an unmatched bracket or control characters; "
            "a file named that way can be granted through its folder."
        )
    return path


def saved_policy_action(action: str) -> str:
    """Return the action to store for a new policy: one lower-case word, or "*" for every action."""
    if action == ALL or (action.isalpha() and action.islower()):
        return action
    raise ValueError("A policy's action is one word (e.g. 'read'), or * for every action.")


def is_safe_request_path(path: str) -> bool:
    """
    Return whether a requested path can be decided at all: it has no ".." part, which on POSIX
    storage would climb out of the folder it names.

    Example: "bucket/shared/../secret.txt" -> False
    """
    return ".." not in path.split("/")
