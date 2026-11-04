"""
Read and write POSIX access lists (ACLs) through an open file descriptor.

Only the access broker uses this. Working on a descriptor obtained from the no-follow walk,
never on a path, keeps a swapped-in symlink from redirecting a grant. Linux stores the list in the
``system.posix_acl_access`` extended attribute: a version word, then (tag, permissions, id) entries.
"""
from __future__ import annotations

import errno
import os
import stat as stat_module
import struct

XATTR = "system.posix_acl_access"
DEFAULT_XATTR = "system.posix_acl_default"
_VERSION = 2
# What reading or removing a missing attribute raises: ENODATA on Linux, ENOATTR where it exists.
_NO_ATTRIBUTE = (errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA))

USER_OBJ, USER, GROUP_OBJ, GROUP, MASK, OTHER = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
UNDEFINED = 0xFFFFFFFF
READ, WRITE, EXECUTE = 4, 2, 1

Entry = tuple[int, int, int]  # tag, permissions, id


def _sort_key(entry: Entry) -> tuple[int, int]:
    """Return the order entries are stored in: by tag, then by id."""
    return entry[0], entry[2]


def _unpack(data: bytes) -> list[Entry]:
    """
    Return the entries of an ACL attribute, after its version word.

    Example: version 2, then one (USER_OBJ, 6, UNDEFINED) record -> ``[(0x01, 6, 0xFFFFFFFF)]``
    """
    return [struct.unpack_from("<HHI", data, 4 + 8 * i) for i in range((len(data) - 4) // 8)]


def _pack(entries: list[Entry]) -> bytes:
    """Return the ACL attribute holding ``entries``: the version word, then one record per entry."""
    records = [struct.pack("<HHI", *entry) for entry in entries]
    return struct.pack("<I", _VERSION) + b"".join(records)


def _mask_for(group_obj: int, named: list[Entry]) -> int:
    """Return the mask: the owning group's permissions and every named entry's."""
    mask = group_obj
    for _, perm, _ in named:
        mask |= perm
    return mask


def _without_user(entries: list[Entry], uid: int) -> list[Entry]:
    """Return ``entries`` without ``uid``'s entry and without the mask (``write`` recomputes it)."""
    kept = []
    for entry in entries:
        if entry[0] == MASK:
            continue
        if entry[0] == USER and entry[2] == uid:
            continue
        kept.append(entry)
    return kept


def read(fd: int) -> list[Entry]:
    """
    Return the file's ACL; if it has none, the equivalent of its mode bits.

    Example: mode 0o640, no ACL ->
    ``[(USER_OBJ, 6, UNDEFINED), (GROUP_OBJ, 4, UNDEFINED), (OTHER, 0, UNDEFINED)]``
    """
    try:
        data = os.getxattr(fd, XATTR)
    except OSError as e:
        if e.errno not in _NO_ATTRIBUTE:
            raise
        mode = os.fstat(fd).st_mode
        return [
            (USER_OBJ, (mode >> 6) & 7, UNDEFINED),
            (GROUP_OBJ, (mode >> 3) & 7, UNDEFINED),
            (OTHER, mode & 7, UNDEFINED),
        ]
    (version,) = struct.unpack_from("<I", data)
    if version != _VERSION:
        raise ValueError(f"unknown ACL version {version}")
    return _unpack(data)


def write(fd: int, entries: list[Entry]) -> None:
    """
    Write an ACL, recomputing the mask from the named entries.

    With no named entries left, the ACL is removed and the mode bits restored, so the file ends up
    exactly as it was before any grant.
    """
    base = {tag: perm for tag, perm, _ in entries if tag in (USER_OBJ, GROUP_OBJ, OTHER)}
    named = [e for e in entries if e[0] in (USER, GROUP)]
    if not named:
        try:
            os.removexattr(fd, XATTR)
        except OSError as e:
            if e.errno not in _NO_ATTRIBUTE:
                raise
        special = stat_module.S_IMODE(os.fstat(fd).st_mode) & 0o7000
        os.fchmod(fd, special | (base[USER_OBJ] << 6) | (base[GROUP_OBJ] << 3) | base[OTHER])
        return
    full = [
        (USER_OBJ, base[USER_OBJ], UNDEFINED),
        (GROUP_OBJ, base[GROUP_OBJ], UNDEFINED),
        (OTHER, base[OTHER], UNDEFINED),
        (MASK, _mask_for(base[GROUP_OBJ], named), UNDEFINED),
        *named,
    ]
    full.sort(key=_sort_key)
    os.setxattr(fd, XATTR, _pack(full))


def read_default(fd: int) -> list[Entry]:
    """Return a folder's default ACL (what new files and folders in it start with); [] if it has none."""
    try:
        data = os.getxattr(fd, DEFAULT_XATTR)
    except OSError as e:
        if e.errno not in _NO_ATTRIBUTE:
            raise
        return []
    return _unpack(data)


def write_default(fd: int, entries: list[Entry]) -> None:
    """Write a folder's default ACL, recomputing the mask from the named entries."""
    base = {tag: perm for tag, perm, _ in entries if tag in (USER_OBJ, GROUP_OBJ, OTHER)}
    # One entry per named user or group; a later entry for the same one replaces an earlier one.
    by_name: dict[tuple[int, int], Entry] = {}
    for tag, perm, ident in entries:
        if tag in (USER, GROUP):
            by_name[(tag, ident)] = (tag, perm, ident)
    named = sorted(by_name.values(), key=_sort_key)
    full = [
        (USER_OBJ, base[USER_OBJ], UNDEFINED),
        (GROUP_OBJ, base[GROUP_OBJ], UNDEFINED),
        (OTHER, base[OTHER], UNDEFINED),
    ]
    if named:
        full += [(MASK, _mask_for(base[GROUP_OBJ], named), UNDEFINED), *named]
    full.sort(key=_sort_key)
    os.setxattr(fd, DEFAULT_XATTR, _pack(full))


def grant_user(fd: int, uid: int, perm: int) -> None:
    """
    Give ``uid`` exactly ``perm`` on the file, replacing any entry it had.

    Granting what's already there changes nothing, not even the file's change time, which download
    validators include.
    """
    entries = read(fd)
    if (USER, perm, uid) in entries:
        return
    write(fd, [*_without_user(entries, uid), (USER, perm, uid)])


def revoke_user(fd: int, uid: int) -> None:
    """Remove ``uid``'s entry, if any."""
    entries = read(fd)
    remaining = _without_user(entries, uid)
    if len(remaining) != len([e for e in entries if e[0] != MASK]):
        write(fd, remaining)
