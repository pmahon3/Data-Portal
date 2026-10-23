"""
Opens files as a link's temporary ID and hands the descriptors back to the helper.

The helper starts this as a child process running as the link's temporary user ID, so the
operating system decides what it can open: only the files that ID has been granted, through
folders it can pass through but not list. Descriptors go back over the socket inherited as the
first argument (SCM_RIGHTS). Kept free of web-framework imports so it starts quickly.

Request (stdin, JSON):
  {"mode": "read", "root": "/srv/posix/data", "paths": [["study", "scan.nii.gz"], ...]}
  {"mode": "create", "dir": "/srv/posix/staging/2000001", "name": ".upload-<hex>"}
"""
import json
import os
import socket
import sys
from pathlib import Path

from app.files import BadPath, Root


def _open_reads(root: str, paths: list[list[str]]) -> tuple[list[dict], list[int]]:
    tree = Root(Path(root), path_only=True)
    results, fds = [], []
    for parts in paths:
        try:
            fd, _ = tree.open_file(parts)
        except BadPath:
            results.append({"ok": False, "status": 400})
        except FileNotFoundError:
            results.append({"ok": False, "status": 404})
        except PermissionError:
            results.append({"ok": False, "status": 403})
        else:
            results.append({"ok": True})
            fds.append(fd)
    return results, fds


def _create(directory: str, name: str) -> tuple[list[dict], list[int]]:
    dir_fd = os.open(directory, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)
    return [{"ok": True}], [fd]


def main() -> None:
    reply = socket.socket(fileno=int(sys.argv[1]))
    request = json.loads(sys.stdin.read())
    if request["mode"] == "read":
        results, fds = _open_reads(request["root"], request["paths"])
    else:
        results, fds = _create(request["dir"], request["name"])
    socket.send_fds(reply, [json.dumps(results).encode()], fds)


if __name__ == "__main__":
    main()
