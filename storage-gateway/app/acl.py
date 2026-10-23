"""
POSIX access lists (ACLs), read and written through an open file descriptor.

Only the privileged helper uses this. Working on a descriptor obtained from the no-follow walk,
never on a path, keeps a swapped-in symlink from redirecting a grant. Linux stores the list in the
``system.posix_acl_access`` extended attribute: a version word, then (tag, permissions, id) entries.
"""
import errno
import os
import stat as stat_module
import struct

XATTR = "system.posix_acl_access"
_VERSION = 2
USER_OBJ, USER, GROUP_OBJ, GROUP, MASK, OTHER = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
UNDEFINED = 0xFFFFFFFF
READ, WRITE, EXECUTE = 4, 2, 1

Entry = tuple[int, int, int]  # tag, permissions, id


def read(fd: int) -> list[Entry]:
    """The file's ACL; if it has none, the equivalent of its mode bits."""
    try:
        data = os.getxattr(fd, XATTR)
    except OSError as e:
        if e.errno not in (errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)):
            raise
        mode = os.fstat(fd).st_mode
        return [(USER_OBJ, (mode >> 6) & 7, UNDEFINED), (GROUP_OBJ, (mode >> 3) & 7, UNDEFINED),
                (OTHER, mode & 7, UNDEFINED)]
    (version,) = struct.unpack_from("<I", data)
    if version != _VERSION:
        raise ValueError(f"unknown ACL version {version}")
    return [struct.unpack_from("<HHI", data, 4 + 8 * i) for i in range((len(data) - 4) // 8)]


def write(fd: int, entries: list[Entry]) -> None:
    """
    Write an ACL. The mask is recomputed from the named entries; with none left, the ACL is removed
    and the mode bits restored, so the file ends up exactly as it was before any grant.
    """
    base = {tag: perm for tag, perm, _ in entries if tag in (USER_OBJ, GROUP_OBJ, OTHER)}
    named = [e for e in entries if e[0] in (USER, GROUP)]
    if not named:
        try:
            os.removexattr(fd, XATTR)
        except OSError as e:
            if e.errno not in (errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)):
                raise
        special = stat_module.S_IMODE(os.fstat(fd).st_mode) & 0o7000
        os.fchmod(fd, special | (base[USER_OBJ] << 6) | (base[GROUP_OBJ] << 3) | base[OTHER])
        return
    mask = base[GROUP_OBJ]
    for _, perm, _ in named:
        mask |= perm
    full = [(USER_OBJ, base[USER_OBJ], UNDEFINED), (GROUP_OBJ, base[GROUP_OBJ], UNDEFINED),
            (OTHER, base[OTHER], UNDEFINED), (MASK, mask, UNDEFINED), *named]
    full.sort(key=lambda e: (e[0], e[2]))
    os.setxattr(fd, XATTR, struct.pack("<I", _VERSION) + b"".join(struct.pack("<HHI", *e) for e in full))


def grant_user(fd: int, uid: int, perm: int) -> None:
    """Give ``uid`` exactly ``perm`` on the file (replacing any entry it had)."""
    entries = [e for e in read(fd) if not (e[0] == USER and e[2] == uid) and e[0] != MASK]
    write(fd, [*entries, (USER, perm, uid)])


def revoke_user(fd: int, uid: int) -> None:
    """Remove ``uid``'s entry, if any."""
    entries = read(fd)
    remaining = [e for e in entries if not (e[0] == USER and e[2] == uid) and e[0] != MASK]
    if len(remaining) != len([e for e in entries if e[0] != MASK]):
        write(fd, remaining)
