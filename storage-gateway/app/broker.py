"""
How the web service reaches files.

- ``HelperAccess`` (deployed): every operation goes through the privileged helper, which checks the
  token itself and opens files as the link's temporary ID. The web service can't read the data on
  its own; if the helper is unreachable, requests fail with 503 and nothing falls back to direct
  access.
- ``DirectAccess`` (local unit tests only): reads the root directly. The deployed container sets
  ``GATEWAY_REQUIRE_ISOLATION`` so this can't be used there.

Both raise ``HTTPException`` with the status to return.
"""
import json
import os
import socket
from types import SimpleNamespace

from fastapi import HTTPException, status

from app.files import BadPath, Root


def _refused(error: Exception) -> HTTPException:
    if isinstance(error, BadPath):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path")
    if isinstance(error, IsADirectoryError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder exists at this path")
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


class DirectAccess:
    def __init__(self, root: Root):
        self.root = root

    def open_read(self, token, resource, parts):
        try:
            return self.root.open_file(parts)
        except (BadPath, FileNotFoundError) as e:
            raise _refused(e)

    def stat(self, token, resource, parts):
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
    def __init__(self, socket_path: str):
        self.socket_path = socket_path

    def call(self, request: dict) -> tuple[dict, list[int]]:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(60)
                sock.connect(self.socket_path)
                sock.sendall(json.dumps(request).encode() + b"\n")
                message, fds, _, _ = socket.recv_fds(sock, 1 << 16, 8)
        except OSError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File access unavailable")
        reply = json.loads(message or b'{"ok": false, "status": 503}')
        if not reply.get("ok"):
            for fd in fds:
                os.close(fd)
            code = reply.get("status", 500)
            detail = {400: "Bad path", 401: "Invalid or expired token", 403: "Token doesn't allow this request",
                      404: "Not found", 409: "A folder exists at this path"}.get(code, "File access failed")
            raise HTTPException(status_code=code, detail=detail)
        return reply, fds

    def open_read(self, token, resource, parts):
        _, fds = self.call({"op": "open", "token": token, "path": resource})
        return fds[0], os.fstat(fds[0])

    def stat(self, token, resource, parts):
        reply, _ = self.call({"op": "stat", "token": token, "path": resource})
        return SimpleNamespace(**reply["stat"])

    def begin_write(self, token, resource, parts):
        reply, fds = self.call({"op": "begin_write", "token": token, "path": resource})
        return HelperWrite(self, token, resource, reply["staging"], fds[0])

    def delete(self, token, resource, parts):
        self.call({"op": "delete", "token": token, "path": resource})


class HelperWrite:
    """An upload into the link's staging file; the helper moves it into place on commit."""

    def __init__(self, access: HelperAccess, token: str, resource: str, staging: str, fd: int):
        self.access, self.token, self.resource, self.staging, self.fd = access, token, resource, staging, fd
        self.existed = False

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self.fd, view):]

    def commit(self):
        os.fsync(self.fd)
        os.close(self.fd)
        reply, _ = self.access.call({"op": "commit", "token": self.token, "path": self.resource,
                                     "staging": self.staging})
        st = dict(reply["stat"])
        self.existed = st.pop("existed")
        return SimpleNamespace(**st)

    def abort(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            self.access.call({"op": "abort", "token": self.token, "path": self.resource, "staging": self.staging})
        except HTTPException:
            pass  # the sweeper removes staging files when the link expires
