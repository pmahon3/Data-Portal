"""
Check, and optionally convert, a data tree to the layout the file service needs.

    python -m app.layout --root /srv/posix/data              # report only (default)
    python -m app.layout --root /srv/posix/data --apply      # convert

The layout (STATUS.md, 2026-10-23): everything owned by the data-owner account; folders 0710 with
the pass-through group, so temporary IDs can pass through but never list; files 0600, so nothing but
a temporary ID's own ACL entry can read them. Run as root on the machine, before the file service
is first used, and again any time to check.

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

DIR_MODE, FILE_MODE = 0o710, 0o600


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


def check(root: str, owner: tuple[int, int], traverse_gid: int, apply: bool = False,
          id_start: int = 2_000_000, id_count: int = 1_000_000) -> Report:
    """Walk ``root`` without following symlinks; report (and with ``apply``, fix) layout differences."""
    report = Report()
    uid, gid = owner

    def visit(dir_fd: int, rel: str) -> None:
        st = os.fstat(dir_fd)
        want = (uid, traverse_gid, DIR_MODE)
        have = (st.st_uid, st.st_gid, stat_module.S_IMODE(st.st_mode))
        if have != want:
            report.changed.append({"path": rel or ".", "kind": "folder", "from": _fmt(*have), "to": _fmt(*want)})
            if apply:
                os.fchown(dir_fd, uid, traverse_gid)
                os.fchmod(dir_fd, DIR_MODE)
        ids = _temporary_acl_ids(dir_fd, id_start, id_count)
        if ids:
            report.for_admin.append({"path": rel or ".", "issue": "ACL entries for temporary IDs", "ids": ids})
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
            st = os.fstat(fd)
            if st.st_nlink > 1:
                report.for_admin.append({"path": path, "issue": f"{st.st_nlink} hard links (another path can reach it)"})
            ids = _temporary_acl_ids(fd, id_start, id_count)
            if ids:
                report.for_admin.append({"path": path, "issue": "ACL entries for temporary IDs", "ids": ids})
            want = (uid, gid, FILE_MODE)
            have = (st.st_uid, st.st_gid, stat_module.S_IMODE(st.st_mode))
            if have != want:
                report.changed.append({"path": path, "kind": "file", "from": _fmt(*have), "to": _fmt(*want)})
                if apply:
                    os.fchown(fd, uid, gid)
                    os.fchmod(fd, FILE_MODE)
        finally:
            os.close(fd)

    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visit(root_fd, "")
    finally:
        os.close(root_fd)
    return report


def _fmt(uid: int, gid: int, mode: int) -> str:
    return f"{uid}:{gid} {mode:04o}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--owner", default="10002:10002", help="uid:gid of the data-owner account")
    parser.add_argument("--traverse-gid", type=int, default=10010)
    parser.add_argument("--apply", action="store_true", help="make the changes (default: report only)")
    args = parser.parse_args(argv)
    uid, gid = (int(x) for x in args.owner.split(":"))
    report = check(args.root, (uid, gid), args.traverse_gid, apply=args.apply)
    json.dump(report.as_dict() | {"applied": args.apply}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
