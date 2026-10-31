"""
Check, and optionally apply, the layout the file service needs in the area a machine exposes to it.

    python -m app.layout --root /srv/posix/data              # report only (default)
    python -m app.layout --root /srv/posix/data --apply      # apply

Owners, groups and administrators' ACL entries are left alone: administrators and project managers
manage direct access on the machine (A1, 2026-10-31), and researchers' processes keep working on raw
data and derivatives. The tool only makes sure the portal's grants are the one way in for anyone
else, and that new files and folders start that way:
- nothing is open to everyone else ("other" has no access, on files and folders);
- folders let the pass-through group through (``x``, never ``r``), so a temporary ID reaches a file
  it was granted and nothing else;
- folders have default entries with the same two rules, so a file or folder made later (by a
  pipeline, with any umask) starts closed to everyone else and passable.
Run as root on the machine, before the file service is first used, and again any time to check.

Changes are made through descriptors from a walk that never follows symlinks. Things the tool won't
decide are reported for an administrator and left alone: symlinks (the service refuses them),
special files (FIFOs, devices, sockets), files with more than one hard link (another path could
reach them), and ACL entries for user IDs in the temporary range (left by a crash or a retired ID).
Running it twice changes nothing the second time.
"""
import argparse
import json
import os
import stat as stat_module
import sys
from dataclasses import dataclass, field

from app import acl



@dataclass
class Report:
    changed: list[dict] = field(default_factory=list)       # would change (or changed, with --apply)
    for_admin: list[dict] = field(default_factory=list)     # left alone; someone has to decide

    def as_dict(self) -> dict:
        return {"changed": self.changed, "for_admin": self.for_admin}


def _temporary_acl_ids(fd: int, id_start: int, id_count: int) -> list[int]:
    try:
        entries = acl.read(fd)
    except OSError:
        return []
    return [i for tag, _, i in entries if tag == acl.USER and id_start <= i < id_start + id_count]


def file_changes(fd: int, apply: bool) -> list[str]:
    """Close a file to everyone else; return what differed."""
    entries = acl.read(fd)
    other = next(p for t, p, _ in entries if t == acl.OTHER)
    if not other:
        return []
    if apply:
        acl.write(fd, [(t, 0 if t == acl.OTHER else p, i) for t, p, i in entries if t != acl.MASK])
    return [f"everyone else: {_rwx(other)} -> ---"]


def folder_changes(fd: int, traverse_gid: int, apply: bool) -> list[str]:
    """Close a folder to everyone else, let the pass-through group through, and set the same rules as
    defaults for what's made in it later; return what differed."""
    changes = []
    entries, defaults = acl.read(fd), acl.read_default(fd)
    other = next(p for t, p, _ in entries if t == acl.OTHER)
    passing = next((p for t, p, i in entries if t == acl.GROUP and i == traverse_gid), 0)
    if other:
        changes.append(f"everyone else: {_rwx(other)} -> ---")
    if not passing & acl.EXECUTE:
        changes.append("pass-through for the portal's temporary IDs added")
    if other or not passing & acl.EXECUTE:
        if apply:
            acl.write(fd, [(t, 0 if t == acl.OTHER else p, i) for t, p, i in entries
                           if t != acl.MASK and not (t == acl.GROUP and i == traverse_gid)]
                      + [(acl.GROUP, passing | acl.EXECUTE, traverse_gid)])
    if not defaults:
        base = {t: p for t, p, _ in acl.read(fd) if t in (acl.USER_OBJ, acl.GROUP_OBJ)}
        defaults = [(acl.USER_OBJ, base[acl.USER_OBJ], acl.UNDEFINED), (acl.GROUP_OBJ, base[acl.GROUP_OBJ], acl.UNDEFINED),
                    (acl.OTHER, 0, acl.UNDEFINED)]
        changes.append("defaults for new files and folders set")
        stale = True
    else:
        d_other = next(p for t, p, _ in defaults if t == acl.OTHER)
        d_passing = next((p for t, p, i in defaults if t == acl.GROUP and i == traverse_gid), 0)
        stale = bool(d_other) or not d_passing & acl.EXECUTE
        if stale:
            changes.append("defaults for new files and folders corrected")
    if stale and apply:
        d_passing = next((p for t, p, i in defaults if t == acl.GROUP and i == traverse_gid), 0)
        acl.write_default(fd, [(t, 0 if t == acl.OTHER else p, i) for t, p, i in defaults
                               if t != acl.MASK and not (t == acl.GROUP and i == traverse_gid)]
                          + [(acl.GROUP, d_passing | acl.EXECUTE, traverse_gid)])
    return changes


def check(root: str, traverse_gid: int, apply: bool = False,
          id_start: int = 2_000_000, id_count: int = 1_000_000) -> Report:
    """Walk ``root`` without following symlinks; report (and with ``apply``, fix) layout differences."""
    report = Report()

    def note(fd: int, path: str, kind: str, changes: list[str]) -> None:
        ids = _temporary_acl_ids(fd, id_start, id_count)
        if ids:
            report.for_admin.append({"path": path, "issue": "ACL entries for temporary IDs", "ids": ids})
        if changes:
            report.changed.append({"path": path, "kind": kind, "changes": changes})

    def visit(dir_fd: int, rel: str) -> None:
        note(dir_fd, rel or ".", "folder", folder_changes(dir_fd, traverse_gid, apply))
        for entry in sorted(os.scandir(dir_fd), key=lambda e: e.name):
            path = f"{rel}/{entry.name}" if rel else entry.name
            est = os.stat(entry.name, dir_fd=dir_fd, follow_symlinks=False)
            if stat_module.S_ISLNK(est.st_mode):
                report.for_admin.append({"path": path, "issue": "symlink (the file service refuses it)",
                                         "target": os.readlink(entry.name, dir_fd=dir_fd)})
            elif stat_module.S_ISDIR(est.st_mode):
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    visit(child, path)
                finally:
                    os.close(child)
            elif stat_module.S_ISREG(est.st_mode):
                visit_file(dir_fd, entry.name, path)
            else:
                report.for_admin.append({"path": path, "issue": "special file (FIFO, device or socket)"})

    def visit_file(dir_fd: int, name: str, path: str) -> None:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
        try:
            if os.fstat(fd).st_nlink > 1:
                report.for_admin.append({"path": path, "issue": f"{os.fstat(fd).st_nlink} hard links (another path can reach it)"})
            note(fd, path, "file", file_changes(fd, apply))
        finally:
            os.close(fd)

    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visit(root_fd, "")
    finally:
        os.close(root_fd)
    return report


def _rwx(perm: int) -> str:
    return "".join(c if perm & bit else "-" for c, bit in (("r", 4), ("w", 2), ("x", 1)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--traverse-gid", type=int, default=10010)
    parser.add_argument("--apply", action="store_true", help="make the changes (default: report only)")
    args = parser.parse_args(argv)
    report = check(args.root, args.traverse_gid, apply=args.apply)
    json.dump(report.as_dict() | {"applied": args.apply}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
