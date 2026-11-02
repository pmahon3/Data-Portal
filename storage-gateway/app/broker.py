"""
Give the web service its way to reach files.

- ``HelperAccess`` (deployed): every operation goes through the privileged helper, which checks the
  token itself and opens files as the link's temporary ID. The web service can't read the data on
  its own; if the helper is unreachable, requests fail with 503 and nothing falls back to direct
  access.
- ``DirectAccess`` (local unit tests only): reads the root directly. The deployed container sets
  ``GATEWAY_REQUIRE_ISOLATION`` so this can't be used there.

Both raise ``HTTPException`` with the status to return.
"""
from __future__ import annotations

import json
import os
import socket
from types import SimpleNamespace
from typing import BinaryIO

from fastapi import HTTPException, status

from app.config import OPEN_BATCH
from app.files import BadPath, Root

# What the web service answers for each refusal the helper reports.
_HELPER_DETAILS = {
    400: "Bad path",
    401: "Invalid or expired token",
    403: "Token doesn't allow this request",
    404: "Not found",
    409: "A folder exists at this path",
}


def _refused(error: Exception) -> HTTPException:
    """Return the ``HTTPException`` for a path the tree refused."""
    if isinstance(error, BadPath):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path")
    if isinstance(error, IsADirectoryError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder exists at this path")
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


class DirectAccess:
    """Read and write the root directly, with the web service's own access (local unit tests only)."""

    def __init__(self, root: Root):
        self.root = root

    def register_bundle(self, token, resource, listing):
        pass  # the web service has already checked the list against the link

    def open_read(self, token, resource, parts, bundle=None):
        try:
            return self.root.open_file(parts)
        except (BadPath, FileNotFoundError) as e:
            raise _refused(e)

    def open_read_many(self, token, resources, bundle):
        opened = []
        for resource in resources:
            try:
                opened.append(self.open_read(token, resource, resource.split("/")[1:], bundle)[0])
            except HTTPException as e:
                opened.append(e)
        return opened

    def stat_many(self, token, resources, bundle):
        stats = []
        for resource in resources:
            try:
                stats.append(self.stat(token, resource, resource.split("/")[1:], bundle))
            except HTTPException as e:
                stats.append(e)
        return stats

    def stat(self, token, resource, parts, bundle=None):
        try:
            return self.root.stat_file(parts)
        except (BadPath, FileNotFoundError) as e:
            raise _refused(e)

    def begin_write(self, token, resource, parts):
        try:
            return self.root.begin_write(parts)
        except (BadPath, FileNotFoundError, IsADirectoryError) as e:
            raise _refused(e)

    def delete(self, token, resource, parts):
        try:
            self.root.delete_file(parts)
        except (BadPath, FileNotFoundError) as e:
            raise _refused(e)


class HelperAccess:
    """Reach files only through the privileged helper's socket."""

    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    def call(self, request: dict, max_fds: int = 8) -> tuple[dict, list[int]]:
        """
        Send one request to the helper; return its reply and the descriptors it handed back.

        A refusal closes any descriptors and raises the ``HTTPException`` for its status.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(60)
                sock.connect(self.socket_path)
                sock.sendall(json.dumps(request).encode() + b"\n")
                message, fds, _, _ = socket.recv_fds(sock, 1 << 16, max_fds)
        except OSError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File access unavailable",
            )
        reply = json.loads(message or b'{"ok": false, "status": 503}')
        if not reply.get("ok"):
            for fd in fds:
                os.close(fd)
            code = reply.get("status", 500)
            raise HTTPException(status_code=code, detail=_HELPER_DETAILS.get(code, "File access failed"))
        return reply, fds

    def register_bundle(self, token, resource, listing):
        """Give the helper a bundle link's file list once; later opens name the bundle only."""
        self.call({"op": "bundle", "token": token, "path": resource, "list": listing})

    def _read_request(self, op, token, resource, bundle):
        """
        Return the request to read or stat one file, naming its bundle if it has one.

        Example: ``("open", t, "ns/study/a.txt", None)`` ->
        ``{"op": "open", "token": t, "path": "ns/study/a.txt"}``
        """
        request = {"op": op, "token": token, "path": resource}
        if bundle:
            request["bundle"] = bundle
        return request

    def open_read(self, token, resource, parts, bundle=None):
        _, fds = self.call(self._read_request("open", token, resource, bundle))
        return fds[0], os.fstat(fds[0])

    def open_read_many(self, token, resources, bundle):
        """
        Open several files of a bundle in one request (one process in the helper).

        Return, in order, a descriptor or the ``HTTPException`` for each file that couldn't be opened.
        """
        reply, fds = self.call(
            {
                "op": "open_many",
                "token": token,
                "path": bundle,
                "bundle": bundle,
                "paths": list(resources),
            },
            max_fds=OPEN_BATCH,
        )
        # The helper sends descriptors only for the files it opened, in order.
        given = iter(fds)
        opened = []
        for result in reply["results"]:
            if result["ok"]:
                opened.append(next(given))
            else:
                opened.append(HTTPException(status_code=result["status"], detail="File access failed"))
        return opened

    def stat(self, token, resource, parts, bundle=None):
        reply, _ = self.call(self._read_request("stat", token, resource, bundle))
        return SimpleNamespace(**reply["stat"])

    def stat_many(self, token, resources, bundle):
        """
        Stat (and grant) several files of a bundle in one request.

        Return, in order, a stat or the ``HTTPException`` for each file.
        """
        reply, _ = self.call({
            "op": "stat_many",
            "token": token,
            "path": bundle,
            "bundle": bundle,
            "paths": list(resources),
        })
        stats = []
        for result in reply["results"]:
            if result["ok"]:
                stats.append(SimpleNamespace(**result["stat"]))
            else:
                stats.append(HTTPException(status_code=result["status"], detail="File access failed"))
        return stats

    def begin_write(self, token, resource, parts):
        reply, fds = self.call({"op": "begin_write", "token": token, "path": resource})
        return HelperWrite(self, token, resource, reply["staging"], fds[0])

    def delete(self, token, resource, parts):
        self.call({"op": "delete", "token": token, "path": resource})


class HelperWrite:
    """Write an upload into the link's staging file; the helper moves it into place on commit."""

    def __init__(self, access: HelperAccess, token: str, resource: str, staging: str, fd: int):
        self.access = access
        self.token = token
        self.resource = resource
        self.staging = staging
        self.fd = fd
        self.existed = False

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self.fd, view):]

    def commit(self):
        os.fsync(self.fd)
        os.close(self.fd)
        reply, _ = self.access.call({
            "op": "commit",
            "token": self.token,
            "path": self.resource,
            "staging": self.staging,
        })
        st = dict(reply["stat"])
        self.existed = st.pop("existed")
        return SimpleNamespace(**st)

    def abort(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            self.access.call({
                "op": "abort",
                "token": self.token,
                "path": self.resource,
                "staging": self.staging,
            })
        except HTTPException:
            pass  # the sweeper removes staging files when the link expires


class BatchOpener:
    """
    Open a multi-file download's files a batch at a time, starting from the file the stream reaches.

    The helper then starts one process per batch rather than one per file. Files opened but never
    sent (the stream ended or stopped early) are closed on exit.
    """

    def __init__(self, access, token: str, bundle: str, paths: list[str], batch: int = OPEN_BATCH):
        self.access = access
        self.token = token
        self.bundle = bundle
        self.paths = paths
        self.batch = batch
        self._index = {path: i for i, path in enumerate(paths)}
        self._opened: dict[str, int | HTTPException] = {}

    def open(self, path: str) -> BinaryIO:
        if path not in self._opened:
            start = self._index[path]
            wanted = [p for p in self.paths[start:start + self.batch] if p not in self._opened]
            results = self.access.open_read_many(self.token, wanted, self.bundle)
            self._opened.update(zip(wanted, results))
        opened = self._opened.pop(path)
        if isinstance(opened, HTTPException):
            raise opened
        return os.fdopen(opened, "rb")

    def close(self) -> None:
        for opened in self._opened.values():
            if isinstance(opened, int):
                os.close(opened)
        self._opened.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
