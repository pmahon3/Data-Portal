"""
The privileged helper: the only part of the file service that can touch the data.

Runs as root beside the unprivileged web service and answers it over a Unix socket that only the
web service's user may use. For every request it checks the portal's signed token itself (a bug in
the web service can't widen a grant), then:

- read:   gives the link's temporary user ID read access to that one file (an ACL entry), and opens
          it in a child process running as that ID, so the operating system decides the open.
          The open descriptor is handed back to the web service, which never has its own access.
- stat:   (the portal's own metadata calls) answers from the no-follow walk; no descriptor.
- write:  creates a staging file as the link's ID, outside the data tree; on commit, moves it
          into place and gives it to the data-owner account. Temporary IDs never get write access
          to data folders, where they could delete or replace other files.
- delete: carried out by the helper after its own token check (POSIX can't grant "delete only
          this file").

Each link (token ``jti``) gets its own ID from a reserved range on first use. When the link
expires, a sweeper removes its ACL entries and staging files and quarantines the ID before reuse,
so audit records never mix two links. Each grant records the file's identity (device, inode): if a
granted file was moved or replaced on the machine and its entry can't be found to remove, the ID is
retired for good rather than handed to another link, and logged for an administrator. Downloads already running keep their open descriptor and
finish. See STREAMING-SPEC.md and STATUS.md (decisions of 2026-10-23).
"""
import json
import logging
import os
import socket
import socketserver
import stat as stat_module
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException

from app import acl
from app.auth import check_token, jwks_key_resolver
from app.files import BadPath, Root, split_key

logger = logging.getLogger("storage-gateway.helper")
SERVICE_DIR = str(Path(__file__).resolve().parents[1])
CANARY = ".gateway-canary"
# Isolated mode (-I) ignores PYTHONPATH, so the service's code path is passed in directly.
_OPENER = f"import sys; sys.path.insert(0, {SERVICE_DIR!r}); from app.opener import main; main()"


@dataclass
class HelperSettings:
    socket_path: str
    data_root: Path
    staging_root: Path
    state_file: Path
    namespace: str
    jwks_url: str
    issuer: str = "inn-portal"
    client_uids: set[int] = field(default_factory=lambda: {10001})
    id_start: int = 2_000_000
    id_count: int = 1_000_000
    traverse_gid: int = 10010
    data_uid: int = 10002
    data_gid: int = 10002
    quarantine_seconds: int = 86400
    sweep_seconds: int = 15

    @classmethod
    def from_env(cls) -> "HelperSettings":
        env = os.environ
        return cls(
            socket_path=env["HELPER_SOCKET"],
            data_root=Path(env["GATEWAY_ROOT"]),
            staging_root=Path(env["HELPER_STAGING"]),
            state_file=Path(env["HELPER_STATE"]),
            namespace=env["GATEWAY_NAMESPACE"],
            jwks_url=env["GATEWAY_JWKS_URL"],
            issuer=env.get("GATEWAY_ISSUER", "inn-portal"),
            client_uids={int(u) for u in env.get("HELPER_CLIENT_UIDS", "10001").split(",")},
            id_start=int(env.get("HELPER_ID_START", 2_000_000)),
            id_count=int(env.get("HELPER_ID_COUNT", 1_000_000)),
            traverse_gid=int(env.get("HELPER_TRAVERSE_GID", 10010)),
            data_uid=int(env.get("HELPER_DATA_UID", 10002)),
            data_gid=int(env.get("HELPER_DATA_GID", 10002)),
            quarantine_seconds=int(env.get("HELPER_QUARANTINE_SECONDS", 86400)),
            sweep_seconds=int(env.get("HELPER_SWEEP_SECONDS", 15)),
        )


class Refused(Exception):
    def __init__(self, status: int):
        self.status = status


class LinkIds:
    """Temporary IDs per link, persisted so a restart still revokes everything it granted."""

    def __init__(self, settings: HelperSettings):
        self.s = settings
        self.lock = threading.Lock()
        try:
            self.state = json.loads(settings.state_file.read_text())
        except FileNotFoundError:
            self.state = {"links": {}, "quarantine": {}, "cursor": 0}
        self.state.setdefault("retired", {})

    def _save(self) -> None:
        tmp = self.s.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.s.state_file)

    def uid_for(self, jti: str, exp: int) -> int:
        with self.lock:
            link = self.state["links"].get(jti)
            if link:
                return link["uid"]
            in_use = ({link["uid"] for link in self.state["links"].values()}
                      | {int(u) for u in self.state["quarantine"]} | {int(u) for u in self.state["retired"]})
            for step in range(self.s.id_count):
                candidate = self.s.id_start + (self.state["cursor"] + step) % self.s.id_count
                if candidate not in in_use:
                    break
            else:
                raise Refused(503)
            self.state["cursor"] = (candidate - self.s.id_start + 1) % self.s.id_count
            self.state["links"][jti] = {"uid": candidate, "exp": exp, "files": []}
            self._save()
            return candidate

    def record_file(self, jti: str, parts: list[str], st: os.stat_result) -> None:
        """Remember a grant with the file's identity, so expiry revokes it on the same file."""
        with self.lock:
            files = self.state["links"][jti]["files"]
            entry = [parts, st.st_dev, st.st_ino]
            if entry not in files:
                files.append(entry)
                self._save()

    def expired(self, now: float) -> list[tuple[str, dict]]:
        with self.lock:
            return [(jti, dict(link)) for jti, link in self.state["links"].items() if link["exp"] < now]

    def retire(self, jti: str, uid: int, now: float, leftovers: list) -> None:
        """
        Release a link's ID: into quarantine if every grant was revoked, otherwise retired for good
        (an ACL entry may remain on a file that was moved), so it never reaches another link.
        """
        with self.lock:
            self.state["links"].pop(jti, None)
            if leftovers:
                self.state["retired"][str(uid)] = {"jti": jti, "files": leftovers, "at": now}
                logger.warning("retired id %s: grants on moved or replaced files could not be revoked: %s",
                               uid, leftovers)
            else:
                self.state["quarantine"][str(uid)] = now + self.s.quarantine_seconds
            self.state["quarantine"] = {u: t for u, t in self.state["quarantine"].items() if t > now}
            self._save()


class Helper:
    def __init__(self, settings: HelperSettings, resolve_key=None):
        self.s = settings
        self.resolve_key = resolve_key or jwks_key_resolver(settings.jwks_url)
        self.ids = LinkIds(settings)
        self.acl_lock = threading.Lock()
        # Folders created by uploads: owned by the data owner; the traverse group may pass through, not list.
        self.tree = Root(settings.data_root, dir_owner=(settings.data_uid, settings.traverse_gid), dir_mode=0o710)

    # --- checks ---

    def _verify(self, token: str, path: str, method: str) -> tuple[dict, list[str]]:
        try:
            claims = check_token(token, self.resolve_key, namespace=self.s.namespace, issuer=self.s.issuer,
                                 path=path, method=method)
        except HTTPException as e:
            raise Refused(e.status_code) from e
        try:
            return claims, split_key(self.s.namespace, path)
        except BadPath as e:
            raise Refused(400) from e

    # --- reads ---

    def open_read(self, token: str, path: str) -> int:
        claims, parts = self._verify(token, path, "GET")
        uid = self.ids.uid_for(claims["jti"], claims["exp"])
        self._grant_read(uid, claims["jti"], parts)
        results, fds = self._as_link(uid, {"mode": "read", "root": str(self.s.data_root), "paths": [parts]},
                                     extra_groups=[self.s.traverse_gid])
        if not results[0]["ok"]:
            raise Refused(results[0]["status"])
        return fds[0]

    def _grant_read(self, uid: int, jti: str, parts: list[str]) -> None:
        try:
            fd, st = self.tree.open_file(parts)
        except BadPath as e:
            raise Refused(400) from e
        except FileNotFoundError as e:
            raise Refused(404) from e
        try:
            self.ids.record_file(jti, parts, st)  # recorded first, so a crash can't leave an unrecorded grant
            with self.acl_lock:
                acl.grant_user(fd, uid, acl.READ)
        finally:
            os.close(fd)

    def stat(self, token: str, path: str) -> dict:
        _, parts = self._verify(token, path, "HEAD")
        try:
            fd, st = self.tree.open_file(parts)
        except BadPath as e:
            raise Refused(400) from e
        except FileNotFoundError as e:
            raise Refused(404) from e
        os.close(fd)
        return _stat_fields(st)

    # --- writes ---

    def _staging_dir(self, uid: int) -> Path:
        directory = self.s.staging_root / str(uid)
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass
        st = os.lstat(directory)
        if not stat_module.S_ISDIR(st.st_mode):
            raise Refused(500)
        os.chown(directory, uid, uid, follow_symlinks=False)
        os.chmod(directory, 0o700)
        return directory

    def begin_write(self, token: str, path: str) -> tuple[str, int]:
        claims, _ = self._verify(token, path, "PUT")
        uid = self.ids.uid_for(claims["jti"], claims["exp"])
        name = f".upload-{uuid.uuid4().hex}"
        results, fds = self._as_link(uid, {"mode": "create", "dir": str(self._staging_dir(uid)), "name": name})
        if not results[0]["ok"]:
            raise Refused(500)
        return name, fds[0]

    def _staged(self, uid: int, name: str) -> tuple[int, int]:
        """Open the link's staging folder and file without following symlinks; check ownership."""
        if "/" in name or not name.startswith(".upload-"):
            raise Refused(400)
        dir_fd = os.open(self.s.staging_root / str(uid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        except FileNotFoundError as e:
            os.close(dir_fd)
            raise Refused(404) from e
        st = os.fstat(fd)
        if not stat_module.S_ISREG(st.st_mode) or st.st_uid != uid:
            os.close(fd)
            os.close(dir_fd)
            raise Refused(400)
        return dir_fd, fd

    def commit(self, token: str, path: str, name: str) -> dict:
        claims, parts = self._verify(token, path, "PUT")
        uid = self.ids.uid_for(claims["jti"], claims["exp"])
        staging_dir, fd = self._staged(uid, name)
        try:
            try:
                target_dir = self.tree._open_dir(parts[:-1], create=True)
            except BadPath as e:
                raise Refused(400) from e
            except FileNotFoundError as e:
                raise Refused(404) from e
            try:
                try:
                    existing = os.stat(parts[-1], dir_fd=target_dir, follow_symlinks=False)
                except FileNotFoundError:
                    existing = None
                if existing is not None and stat_module.S_ISLNK(existing.st_mode):
                    raise Refused(400)
                if existing is not None and stat_module.S_ISDIR(existing.st_mode):
                    raise Refused(409)
                # Hand the file to the data owner before it appears in the tree.
                os.fchown(fd, self.s.data_uid, self.s.data_gid)
                os.fchmod(fd, 0o600)
                os.fsync(fd)
                os.replace(name, parts[-1], src_dir_fd=staging_dir, dst_dir_fd=target_dir)
                st = os.fstat(fd)
                placed = os.stat(parts[-1], dir_fd=target_dir, follow_symlinks=False)
                if (placed.st_dev, placed.st_ino) != (st.st_dev, st.st_ino):
                    logger.error("upload to %s was replaced after placement; refusing", path)
                    raise Refused(500)
            finally:
                os.close(target_dir)
        finally:
            os.close(fd)
            os.close(staging_dir)
        return _stat_fields(st) | {"existed": existing is not None}

    def abort(self, token: str, path: str, name: str) -> None:
        claims, _ = self._verify(token, path, "PUT")
        uid = self.ids.uid_for(claims["jti"], claims["exp"])
        staging_dir, fd = self._staged(uid, name)
        os.close(fd)
        try:
            os.unlink(name, dir_fd=staging_dir)
        finally:
            os.close(staging_dir)

    # --- deletes ---

    def delete(self, token: str, path: str) -> None:
        _, parts = self._verify(token, path, "DELETE")
        try:
            self.tree.delete_file(parts)
        except BadPath as e:
            raise Refused(400) from e
        except FileNotFoundError as e:
            raise Refused(404) from e

    # --- running as the link's ID ---

    def _as_link(self, uid: int, request: dict, extra_groups: list[int] | None = None) -> tuple[list, list[int]]:
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", _OPENER, str(child.fileno())],
                input=json.dumps(request).encode(), pass_fds=(child.fileno(),),
                user=uid, group=uid, extra_groups=extra_groups or [],
                env={}, cwd="/", capture_output=True, timeout=30,
            )
            child.close()
            if result.returncode != 0:
                logger.error("opener failed for id %s: %s", uid, result.stderr.decode()[-500:])
                raise Refused(500)
            message, fds, _, _ = socket.recv_fds(parent, 1 << 16, 64)
            return json.loads(message), fds
        finally:
            parent.close()
            if child.fileno() != -1:
                child.close()

    # --- expiry ---

    def sweep(self, now: float | None = None) -> int:
        """
        Revoke expired links: ACL entries (on the same files they were granted on), staging files;
        then release or retire their IDs. A link that fails is logged and retried next time, and its ID
        stays out of the pool; it never stops the others. Returns how many links were finished.
        """
        now = time.time() if now is None else now
        swept = 0
        for jti, link in self.ids.expired(now):
            uid = link["uid"]
            try:
                leftovers = []
                for entry in link["files"]:
                    parts, dev, ino = (entry, None, None) if isinstance(entry[0], str) else entry
                    try:
                        fd, st = self.tree.open_file(parts)
                    except (BadPath, FileNotFoundError):
                        leftovers.append(parts)  # moved or removed on the machine
                        continue
                    try:
                        if (st.st_dev, st.st_ino) != (dev, ino):
                            leftovers.append(parts)  # a different file is there now
                            continue
                        with self.acl_lock:
                            acl.revoke_user(fd, uid)
                    finally:
                        os.close(fd)
                staging = self.s.staging_root / str(uid)
                if staging.is_dir() and not staging.is_symlink():
                    for item in os.scandir(staging):
                        os.unlink(item.path)
                    os.rmdir(staging)
                self.ids.retire(jti, uid, now, leftovers)
                swept += 1
            except Exception:
                logger.exception("could not revoke link %s (id %s); will retry", jti, uid)
        return swept

    def write_canary(self) -> None:
        """A file only the data owner can read; the web service refuses to start if it can read it."""
        canary = self.s.data_root / CANARY
        canary.write_text("the web service must not be able to read this\n")
        os.chown(canary, self.s.data_uid, self.s.data_gid)
        os.chmod(canary, 0o600)


def _stat_fields(st: os.stat_result) -> dict:
    return {"st_size": st.st_size, "st_mtime": st.st_mtime, "st_mtime_ns": st.st_mtime_ns,
            "st_ctime_ns": st.st_ctime_ns, "st_ino": st.st_ino}


# --- socket server ---

_OPS = {"open", "stat", "begin_write", "commit", "abort", "delete"}


def make_server(helper: Helper) -> socketserver.ThreadingUnixStreamServer:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            sock = self.request
            uid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[1]
            if uid not in helper.s.client_uids:
                logger.warning("refused helper connection from uid %s", uid)
                sock.sendall(json.dumps({"ok": False, "status": 403}).encode())
                return
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    return
                data += chunk
            fds: list[int] = []
            try:
                req = json.loads(data)
                op = req.get("op")
                if op not in _OPS:
                    raise Refused(400)
                token, path = req["token"], req["path"]
                if op == "open":
                    fds = [helper.open_read(token, path)]
                    reply = {"ok": True}
                elif op == "stat":
                    reply = {"ok": True, "stat": helper.stat(token, path)}
                elif op == "begin_write":
                    name, fd = helper.begin_write(token, path)
                    fds, reply = [fd], {"ok": True, "staging": name}
                elif op == "commit":
                    reply = {"ok": True, "stat": helper.commit(token, path, req["staging"])}
                elif op == "abort":
                    helper.abort(token, path, req["staging"])
                    reply = {"ok": True}
                else:
                    helper.delete(token, path)
                    reply = {"ok": True}
            except Refused as e:
                reply = {"ok": False, "status": e.status}
            except Exception:
                logger.exception("helper request failed")
                reply = {"ok": False, "status": 500}
            try:
                socket.send_fds(sock, [json.dumps(reply).encode()], fds) if fds else sock.sendall(json.dumps(reply).encode())
            finally:
                for fd in fds:
                    os.close(fd)

    try:
        os.unlink(helper.s.socket_path)
    except FileNotFoundError:
        pass
    server = socketserver.ThreadingUnixStreamServer(helper.s.socket_path, Handler)
    server.daemon_threads = True
    return server


def serve(settings: HelperSettings, resolve_key=None, socket_mode: int = 0o660, socket_gid: int | None = None):
    helper = Helper(settings, resolve_key)
    helper.write_canary()
    helper.sweep()
    server = make_server(helper)
    os.chmod(settings.socket_path, socket_mode)
    if socket_gid is not None:
        os.chown(settings.socket_path, 0, socket_gid)

    def sweeper():
        while True:
            time.sleep(settings.sweep_seconds)
            try:
                swept = helper.sweep()
                if swept:
                    logger.info("revoked %d expired link(s)", swept)
            except Exception:
                logger.exception("sweep failed")

    threading.Thread(target=sweeper, daemon=True).start()
    return helper, server


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if os.geteuid() != 0:
        raise SystemExit("the helper must run as root")
    settings = HelperSettings.from_env()
    _, server = serve(settings, socket_gid=int(os.getenv("HELPER_SOCKET_GID", "10001")))
    logger.info("helper serving %s for namespace %r", settings.socket_path, settings.namespace)
    server.serve_forever()


if __name__ == "__main__":
    main()
