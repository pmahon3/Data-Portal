"""
Serve the file service's privileged operations: the only part of it that can touch the data.

Runs as root beside the unprivileged web service and answers it over a Unix socket that only the web
service's user may use. For every request it checks the portal's signed token itself, so a bug in the
web service can't widen a grant. A read is granted to the link's temporary user ID and opened in a
child process running as that ID, so the operating system decides the open; the web service gets the
descriptor and never has its own access. Temporary IDs never get write access to data folders: an
upload goes to a staging file the access broker moves into place, and the access broker carries out deletes itself
(POSIX can't grant "delete only this file"). Each operation's method says what it does.

Each approved request gets its own ID from a reserved range on first use (see ``LinkIds``). When a
grant expires, a sweeper removes its ACL entries and staging files and quarantines the ID before
reuse, so audit records never mix two grants. Each grant records the file's identity (device, inode):
if a granted file was moved or replaced and its entry can't be found to remove, the ID is retired for
good rather than handed to another link, and logged for an administrator. Downloads already running
keep their open descriptor and finish. See STREAMING-SPEC.md and STATUS.md (decisions of 2026-10-23).
"""
from __future__ import annotations

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
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException

from app import acl, layout
from app.auth import bundle_listing, check_token, jwks_key_resolver
from app.config import CANARY, OPEN_BATCH
from app.files import BadPath, Root, split_key

logger = logging.getLogger("storage-gateway.access_broker")
# One line per grant, placement, delete and expiry: temporary ID -> link -> portal user.
audit = logging.getLogger("storage-gateway.audit")
SERVICE_DIR = str(Path(__file__).resolve().parents[1])
# Isolated mode (-I) ignores PYTHONPATH, so the service's code path is passed in directly.
_OPENER = f"import sys; sys.path.insert(0, {SERVICE_DIR!r}); from app.opener import main; main()"


# --- settings ---


@dataclass
class BrokerSettings:
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
    def from_env(cls) -> BrokerSettings:
        env = os.environ
        return cls(
            socket_path=env["BROKER_SOCKET"],
            data_root=Path(env["GATEWAY_ROOT"]),
            staging_root=Path(env["BROKER_STAGING"]),
            state_file=Path(env["BROKER_STATE"]),
            namespace=env["GATEWAY_NAMESPACE"],
            jwks_url=env["GATEWAY_JWKS_URL"],
            issuer=env.get("GATEWAY_ISSUER", "inn-portal"),
            client_uids={int(u) for u in env.get("BROKER_CLIENT_UIDS", "10001").split(",")},
            id_start=int(env.get("BROKER_ID_START", 2_000_000)),
            id_count=int(env.get("BROKER_ID_COUNT", 1_000_000)),
            traverse_gid=int(env.get("BROKER_TRAVERSE_GID", 10010)),
            data_uid=int(env.get("BROKER_DATA_UID", 10002)),
            data_gid=int(env.get("BROKER_DATA_GID", 10002)),
            quarantine_seconds=int(env.get("BROKER_QUARANTINE_SECONDS", 86400)),
            sweep_seconds=int(env.get("BROKER_SWEEP_SECONDS", 15)),
        )


# --- refusals ---


class Refused(Exception):
    """Refuse a request with the HTTP status the web service should return."""

    def __init__(self, status: int):
        self.status = status


@contextmanager
def _refusing():
    """Refuse a bad path with 400, a missing file or folder with 404."""
    try:
        yield
    except BadPath as e:
        raise Refused(400) from e
    except FileNotFoundError as e:
        raise Refused(404) from e


# --- temporary IDs ---


def grant_key(claims: dict) -> str:
    """
    Return the approval a link belongs to: its ``grant`` claim, or the link itself when it has none.

    Example: ``{"grant": "g1", "jti": "j1"}`` -> ``"g1"``; ``{"jti": "j1"}`` -> ``"j1"``
    """
    return claims.get("grant") or claims["jti"]


def _grant_note(claims: dict) -> str:
    """
    Return the audit line's ending that names the link's approval, if it has one.

    Example: ``{"grant": "g1"}`` -> ``" grant=g1"``; ``{}`` -> ``""``
    """
    if claims.get("grant"):
        return f" grant={claims['grant']}"
    return ""


class LinkIds:
    """
    Keep the temporary ID of each grant, persisted so a restart still revokes everything it granted.

    A grant's links share an approval ID (token ``grant``); a link without one is its own request
    (keyed by ``jti``).
    """

    def __init__(self, settings: BrokerSettings):
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

    def uid_for(self, key: str, exp: int, user: str | None = None) -> int:
        """
        Return the grant's temporary ID, taking a free one on first use.

        A grant is bound to the user of its first link and lasts until its latest link expires; a link
        of a grant that has already expired starts a new ID.
        """
        with self.lock:
            now = time.time()
            link = self.state["links"].get(key)
            if link and link["user"] != user:
                raise Refused(403)  # a grant belongs to one user
            if link and link["exp"] >= now:
                if exp > link["exp"]:
                    link["exp"] = exp
                    self._save()
                return link["uid"]
            if link:
                # Expired but not yet swept: keep it for the sweeper under its own name; start a new ID.
                self.state["links"][f"{key}~{link['uid']}"] = self.state["links"].pop(key)
            candidate = self._free_id(now)
            self.state["cursor"] = (candidate - self.s.id_start + 1) % self.s.id_count
            self.state["quarantine"].pop(str(candidate), None)
            self.state["links"][key] = {"uid": candidate, "exp": exp, "user": user, "files": []}
            self._save()
            return candidate

    def _free_id(self, now: float) -> int:
        """
        Return the first ID from the cursor on that no grant holds and isn't quarantined or retired.

        Called with the lock held. Refuses with 503 when the whole range is taken.
        """
        in_use = {link["uid"] for link in self.state["links"].values()}
        for uid, until in self.state["quarantine"].items():
            if until > now:
                in_use.add(int(uid))
        for uid in self.state["retired"]:
            in_use.add(int(uid))
        for step in range(self.s.id_count):
            candidate = self.s.id_start + (self.state["cursor"] + step) % self.s.id_count
            if candidate not in in_use:
                return candidate
        raise Refused(503)

    def record_files(self, key: str, grants: list[tuple[list[str], os.stat_result]]) -> None:
        """
        Remember grants with each file's identity, so expiry revokes them on the same files.

        One save for the lot: saving rewrites the whole state, so saving per file grew with the square
        of a download's size.
        """
        with self.lock:
            files = self.state["links"][key]["files"]
            known = {(tuple(parts), dev, ino) for parts, dev, ino in files}
            new = []
            for parts, st in grants:
                if (tuple(parts), st.st_dev, st.st_ino) not in known:
                    new.append([parts, st.st_dev, st.st_ino])
            if new:
                files.extend(new)
                self._save()

    def expired(self, now: float) -> list[tuple[str, dict]]:
        """Return a copy of each grant that expired before ``now``, with its key."""
        with self.lock:
            return [(key, dict(link)) for key, link in self.state["links"].items() if link["exp"] < now]

    def retire(self, key: str, uid: int, now: float, leftovers: list) -> None:
        """
        Release a grant's ID: into quarantine if every file grant was revoked, otherwise retired for good.

        A retired ID may still have an ACL entry on a file that was moved, so it never reaches another
        grant.
        """
        with self.lock:
            # The grant may have been renamed since the sweep began (a new link started a new ID).
            for name, link in self.state["links"].items():
                if link["uid"] == uid:
                    key = name
                    break
            self.state["links"].pop(key, None)
            if leftovers:
                self.state["retired"][str(uid)] = {"jti": key, "files": leftovers, "at": now}
                logger.warning(
                    "retired id %s: grants on moved or replaced files could not be revoked: %s",
                    uid,
                    leftovers,
                )
            else:
                self.state["quarantine"][str(uid)] = now + self.s.quarantine_seconds
            self.state["quarantine"] = {u: t for u, t in self.state["quarantine"].items() if t > now}
            self._save()


# --- the access broker ---


class Broker:
    """Carry out the web service's requests after checking each link's token."""

    def __init__(self, settings: BrokerSettings, resolve_key=None):
        self.s = settings
        self.resolve_key = resolve_key or jwks_key_resolver(settings.jwks_url)
        self.ids = LinkIds(settings)
        self.acl_lock = threading.Lock()
        self.bundles: dict[str, tuple[frozenset[str], int]] = {}  # list digest -> (paths, expiry)
        # Folders created by uploads: owned by the data owner; the traverse group may pass through, not list.
        self.tree = Root(settings.data_root, on_create=self._new_folder, dir_mode=0o700)

    # --- checks ---

    def _uid(self, claims: dict) -> int:
        """Return the temporary ID of the link's approval (or of the link, if it has none)."""
        return self.ids.uid_for(grant_key(claims), claims["exp"], claims.get("sub"))

    def _verify(
        self,
        token: str,
        path: str,
        method: str,
        bundle: str | None = None,
    ) -> tuple[dict, list[str]]:
        """
        Check a link for ``path``; with ``bundle``, a bundle link whose registered list holds ``path``.

        Return the link's claims and the path's components.
        """
        operation = "bundle" if bundle else None
        try:
            claims = check_token(
                token,
                self.resolve_key,
                namespace=self.s.namespace,
                issuer=self.s.issuer,
                path=bundle or path,
                method=method,
                operation=operation,
            )
        except HTTPException as e:
            raise Refused(e.status_code) from e
        if bundle:
            listed, _ = self.bundles.get(claims.get("list"), ((), 0))
            if path not in listed:
                raise Refused(403)
        try:
            return claims, split_key(self.s.namespace, path)
        except BadPath as e:
            raise Refused(400) from e

    # --- reads ---

    def register_bundle(self, token: str, path: str, listing: str) -> None:
        """
        Keep a multi-file download's file list, after checking it against the SHA-256 its link carries.

        Reads and stats that name the bundle are then allowed only for files on it.
        """
        try:
            claims = check_token(
                token,
                self.resolve_key,
                namespace=self.s.namespace,
                issuer=self.s.issuer,
                path=path,
                method="GET",
                operation="bundle",
            )
            paths = frozenset(bundle_listing(claims, listing)["paths"])
        except HTTPException as e:
            raise Refused(e.status_code) from e
        except (ValueError, KeyError, TypeError) as e:
            raise Refused(400) from e
        now = time.time()
        self.bundles = {d: v for d, v in self.bundles.items() if v[1] > now}
        self.bundles[claims["list"]] = (paths, claims["exp"])

    def open_read(self, token: str, path: str, bundle: str | None = None) -> int:
        """
        Give the link's temporary ID read access to that one file (an ACL entry) and open it as that ID.

        Return the open descriptor, for the web service, which never has its own access.
        """
        claims, parts = self._verify(token, path, "GET", bundle)
        key = grant_key(claims)
        uid = self._uid(claims)
        self._grant_read(uid, key, parts)
        audit.info(
            "read link=%s id=%s user=%s path=%s%s",
            claims["jti"],
            uid,
            claims.get("sub", "-"),
            path,
            _grant_note(claims),
        )
        results, fds = self._as_link(
            uid,
            {"mode": "read", "root": str(self.s.data_root), "paths": [parts]},
            extra_groups=[self.s.traverse_gid],
        )
        if not results[0]["ok"]:
            raise Refused(results[0]["status"])
        return fds[0]

    def open_read_many(self, token: str, paths: list[str], bundle: str) -> tuple[list[dict], list[int]]:
        """
        Open several files of a bundle with one process as its temporary ID.

        Every path must be on the bundle's list, or nothing is opened; a file that can't be opened
        fails alone.
        """
        checked = [self._verify(token, path, "GET", bundle) for path in paths]
        claims = checked[0][0]
        key = grant_key(claims)
        uid = self._uid(claims)
        results: list[dict | None] = []
        for path, granted in zip(paths, self._grant_reads(uid, key, [parts for _, parts in checked])):
            if isinstance(granted, Refused):  # gone or replaced since it was listed: only this file fails
                results.append({"ok": False, "status": granted.status})
                continue
            results.append(None)
            audit.info(
                "read link=%s id=%s user=%s path=%s%s",
                claims["jti"],
                uid,
                claims.get("sub", "-"),
                path,
                _grant_note(claims),
            )
        to_open = [parts for (_, parts), result in zip(checked, results) if result is None]
        if to_open:
            opened, fds = self._as_link(
                uid,
                {"mode": "read", "root": str(self.s.data_root), "paths": to_open},
                extra_groups=[self.s.traverse_gid],
            )
        else:
            opened, fds = [], []
        # The opener answers for the granted files only, in order; the others have their refusal.
        from_opener = iter(opened)
        replies = []
        for result in results:
            if result is None:
                replies.append(next(from_opener))
            else:
                replies.append(result)
        return replies, fds

    def _grant_read(self, uid: int, key: str, parts: list[str]) -> None:
        (granted,) = self._grant_reads(uid, key, [parts])
        if isinstance(granted, Refused):
            raise granted

    def _grant_reads(self, uid: int, key: str, paths: list[list[str]]) -> list[os.stat_result | Refused]:
        """
        Grant ``uid`` read access to each file.

        Return each file's status after its grant, or why it couldn't be granted.
        """
        opened: list[tuple[int, os.stat_result] | Refused] = []
        try:
            for parts in paths:
                try:
                    with _refusing():
                        opened.append(self.tree.open_file(parts))
                except Refused as e:
                    opened.append(e)
            # Recorded first, so a crash can't leave an unrecorded grant.
            identities = []
            for parts, o in zip(paths, opened):
                if not isinstance(o, Refused):
                    identities.append((parts, o[1]))
            self.ids.record_files(key, identities)
            with self.acl_lock:
                for o in opened:
                    if not isinstance(o, Refused):
                        acl.grant_user(o[0], uid, acl.READ)
            statuses: list[os.stat_result | Refused] = []
            for o in opened:
                if isinstance(o, Refused):
                    statuses.append(o)
                else:
                    statuses.append(os.fstat(o[0]))
            return statuses
        finally:
            for o in opened:
                if not isinstance(o, Refused):
                    os.close(o[0])

    def stat(self, token: str, path: str, bundle: str | None = None) -> dict:
        """Answer the portal's metadata call from the no-follow walk; no descriptor is handed back."""
        claims, parts = self._verify(token, path, "HEAD", bundle)
        if bundle:
            # Grant now, as opening will: the grant changes the file's ctime, which is part of the
            # validator the download's ETag is built from, so it must already be in place.
            key = grant_key(claims)
            self._grant_read(self._uid(claims), key, parts)
        audit.info("stat link=%s user=%s path=%s", claims["jti"], claims.get("sub", "-"), path)
        with _refusing():
            fd, st = self.tree.open_file(parts)
        os.close(fd)
        return _stat_fields(st)

    def stat_many(self, token: str, paths: list[str], bundle: str) -> list[dict]:
        """Grant and stat several files of a bundle (see ``stat``); every path must be on its list."""
        checked = [self._verify(token, path, "HEAD", bundle) for path in paths]
        claims = checked[0][0]
        granted = self._grant_reads(self._uid(claims), grant_key(claims), [parts for _, parts in checked])
        for path in paths:
            audit.info("stat link=%s user=%s path=%s", claims["jti"], claims.get("sub", "-"), path)
        replies = []
        for g in granted:
            if isinstance(g, Refused):
                replies.append({"ok": False, "status": g.status})
            else:
                replies.append({"ok": True, "stat": _stat_fields(g)})
        return replies

    # --- writes ---

    def _staging_dir(self, uid: int) -> Path:
        """Return the ID's own staging folder, outside the data tree, creating it if needed."""
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
        """
        Create a staging file as the link's ID, outside the data tree; return its name and descriptor.

        Temporary IDs never get write access to data folders, where they could delete or replace
        other files; ``commit`` moves the upload into place.
        """
        claims, _ = self._verify(token, path, "PUT")
        uid = self._uid(claims)
        audit.info(
            "write link=%s id=%s user=%s path=%s%s",
            claims["jti"],
            uid,
            claims.get("sub", "-"),
            path,
            _grant_note(claims),
        )
        name = f".upload-{uuid.uuid4().hex}"
        request = {"mode": "create", "dir": str(self._staging_dir(uid)), "name": name}
        results, fds = self._as_link(uid, request)
        if not results[0]["ok"]:
            raise Refused(500)
        return name, fds[0]

    def _staged(self, uid: int, name: str) -> tuple[int, int]:
        """Open the link's staging folder and file without following symlinks; check ownership."""
        if "/" in name or not name.startswith(".upload-"):
            raise Refused(400)
        try:
            dir_fd = os.open(self.s.staging_root / str(uid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError as e:
            raise Refused(404) from e
        except OSError as e:  # a symlink or not a folder
            raise Refused(400) from e
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
        """Move a staged upload into place and give it to the data-owner account; return its stat."""
        claims, parts = self._verify(token, path, "PUT")
        uid = self._uid(claims)
        staging_dir, fd = self._staged(uid, name)
        try:
            with _refusing():
                target_dir = self.tree.open_dir(parts[:-1], create=True)
            try:
                try:
                    existing = os.stat(parts[-1], dir_fd=target_dir, follow_symlinks=False)
                except FileNotFoundError:
                    existing = None
                if existing is not None and stat_module.S_ISLNK(existing.st_mode):
                    raise Refused(400)
                if existing is not None and stat_module.S_ISDIR(existing.st_mode):
                    raise Refused(409)
                # Hand the file to the data owner, with its folder's permissions, before it appears.
                self._placed_permissions(fd, target_dir)
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
        audit.info("placed link=%s id=%s user=%s path=%s", claims["jti"], uid, claims.get("sub", "-"), path)
        return _stat_fields(st) | {"existed": existing is not None}

    def abort(self, token: str, path: str, name: str) -> None:
        """Remove a staged upload."""
        claims, _ = self._verify(token, path, "PUT")
        uid = self._uid(claims)
        staging_dir, fd = self._staged(uid, name)
        os.close(fd)
        try:
            os.unlink(name, dir_fd=staging_dir)
        finally:
            os.close(staging_dir)

    def _temporary(self, uid: int) -> bool:
        """Return whether ``uid`` is in the range of temporary IDs."""
        return self.s.id_start <= uid < self.s.id_start + self.s.id_count

    def _without_temporary(self, entries: list[acl.Entry]) -> list[acl.Entry]:
        """Return ``entries`` without the mask and without any temporary ID's entry."""
        kept = []
        for entry in entries:
            tag, _, ident = entry
            if tag == acl.MASK:
                continue
            if tag == acl.USER and self._temporary(ident):
                continue
            kept.append(entry)
        return kept

    def _placed_permissions(self, fd: int, folder_fd: int) -> None:
        """
        Give an upload what a file made in its folder would get: the folder's group and default entries.

        It's moved in from staging, so the kernel doesn't apply them. It never gets access for everyone
        else or a temporary ID's entry. A folder nobody set up keeps it the data owner's alone.
        """
        defaults = acl.read_default(folder_fd)
        if not defaults:
            os.fchown(fd, self.s.data_uid, self.s.data_gid)
            os.fchmod(fd, 0o600)
            return
        os.fchown(fd, self.s.data_uid, os.fstat(folder_fd).st_gid)
        entries = []
        for tag, perm, ident in self._without_temporary(defaults):
            if tag == acl.OTHER:
                entries.append((tag, 0, ident))
            else:
                entries.append((tag, perm & (acl.READ | acl.WRITE), ident))
        acl.write(fd, entries)

    def _new_folder(self, fd: int, parent_fd: int) -> None:
        """
        Set up a folder an upload creates as one made there would be: the parent's group and default entries.

        It's closed to everyone else and passable by the portal's temporary IDs. Under a parent nobody
        set up, it's the data owner's, passable by the pass-through group only.
        """
        defaults = acl.read_default(parent_fd)
        if not defaults:
            os.fchown(fd, self.s.data_uid, self.s.traverse_gid)
            os.fchmod(fd, 0o710)
            return
        os.fchown(fd, self.s.data_uid, os.fstat(parent_fd).st_gid)
        kept = self._without_temporary(defaults)
        acl.write(fd, kept)
        acl.write_default(fd, kept)
        layout.folder_changes(fd, self.s.traverse_gid, apply=True)

    # --- deletes ---

    def delete(self, token: str, path: str) -> None:
        """Delete a file after the access broker's own token check (POSIX can't grant "delete only this file")."""
        claims, parts = self._verify(token, path, "DELETE")
        audit.info("delete link=%s user=%s path=%s", claims["jti"], claims.get("sub", "-"), path)
        with _refusing():
            self.tree.delete_file(parts)

    # --- running as the link's ID ---

    def _as_link(
        self,
        uid: int,
        request: dict,
        extra_groups: list[int] | None = None,
    ) -> tuple[list, list[int]]:
        """Run the opener as ``uid`` on ``request``; return its results and the descriptors it opened."""
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", _OPENER, str(child.fileno())],
                input=json.dumps(request).encode(),
                pass_fds=(child.fileno(),),
                user=uid,
                group=uid,
                extra_groups=extra_groups or [],
                env={},
                cwd="/",
                capture_output=True,
                timeout=30,
            )
            child.close()
            if result.returncode != 0:
                logger.error("opener failed for id %s: %s", uid, result.stderr.decode()[-500:])
                raise Refused(500)
            message, fds, _, _ = socket.recv_fds(parent, 1 << 16, OPEN_BATCH)
            return json.loads(message), fds
        finally:
            parent.close()
            if child.fileno() != -1:
                child.close()

    # --- expiry ---

    def sweep(self, now: float | None = None) -> int:
        """
        Revoke expired links: ACL entries (on the same files they were granted on), staging files;
        then release or retire their IDs.

        A link that fails is logged and retried next time, and its ID stays out of the pool; it never
        stops the others. Return how many links were finished.
        """
        now = time.time() if now is None else now
        swept = 0
        for key, link in self.ids.expired(now):
            uid = link["uid"]
            try:
                leftovers = []
                for entry in link["files"]:
                    if isinstance(entry[0], str):  # the path alone, without the file's identity
                        parts, dev, ino = entry, None, None
                    else:
                        parts, dev, ino = entry
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
                self.ids.retire(key, uid, now, leftovers)
                outcome = "retired" if leftovers else "quarantined"
                audit.info("expired grant=%s id=%s %s", key, uid, outcome)
                swept += 1
            except Exception:
                logger.exception("could not revoke grant %s (id %s); will retry", key, uid)
        return swept

    def write_canary(self) -> None:
        """Write a file only the data owner can read; the web service refuses to start if it can read it."""
        canary = self.s.data_root / CANARY
        canary.write_text("the web service must not be able to read this\n")
        os.chown(canary, self.s.data_uid, self.s.data_gid)
        os.chmod(canary, 0o600)


def _stat_fields(st: os.stat_result) -> dict:
    """Return the stat fields the web service uses, as sent over the socket."""
    return {
        "st_size": st.st_size,
        "st_mtime": st.st_mtime,
        "st_mtime_ns": st.st_mtime_ns,
        "st_ctime_ns": st.st_ctime_ns,
        "st_ino": st.st_ino,
    }


# --- socket server ---

_OPS = {"open", "open_many", "stat", "stat_many", "begin_write", "commit", "abort", "delete", "bundle"}


def _validated(req) -> dict:
    """
    Check a request's shape and return it, or refuse it with 400.

    A request has a known op and string token and path (and staging name for commit and abort, the
    list for bundle); ``bundle``, if present, is a string.
    Example: ``{"op": "open", "token": "<jwt>", "path": "ns/study/a.txt"}``
    """
    if not isinstance(req, dict) or req.get("op") not in _OPS:
        raise Refused(400)
    needed = ["token", "path"]
    if req["op"] in ("commit", "abort"):
        needed.append("staging")
    elif req["op"] == "bundle":
        needed.append("list")
    if not all(isinstance(req.get(name), str) for name in needed):
        raise Refused(400)
    if not isinstance(req.get("bundle", ""), str):
        raise Refused(400)
    if req["op"] in ("open_many", "stat_many"):
        paths = req.get("paths")
        if not isinstance(req.get("bundle"), str) or not isinstance(paths, list):
            raise Refused(400)
        if not 0 < len(paths) <= OPEN_BATCH or not all(isinstance(p, str) for p in paths):
            raise Refused(400)
    return req


def make_server(broker: Broker) -> socketserver.ThreadingUnixStreamServer:
    """Return the server that answers the web service's requests on the access broker's socket."""

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            sock = self.request
            credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _, uid, _ = struct.unpack("3i", credentials)
            if uid not in broker.s.client_uids:
                logger.warning("refused access broker connection from uid %s", uid)
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
                try:
                    req = _validated(json.loads(data))
                except ValueError as e:  # not JSON
                    raise Refused(400) from e
                op, token, path = req["op"], req["token"], req["path"]
                if op == "open":
                    fds = [broker.open_read(token, path, req.get("bundle"))]
                    reply = {"ok": True}
                elif op == "open_many":
                    results, fds = broker.open_read_many(token, req["paths"], req["bundle"])
                    reply = {"ok": True, "results": results}
                elif op == "stat_many":
                    reply = {"ok": True, "results": broker.stat_many(token, req["paths"], req["bundle"])}
                elif op == "stat":
                    reply = {"ok": True, "stat": broker.stat(token, path, req.get("bundle"))}
                elif op == "bundle":
                    broker.register_bundle(token, path, req["list"])
                    reply = {"ok": True}
                elif op == "begin_write":
                    name, fd = broker.begin_write(token, path)
                    fds = [fd]
                    reply = {"ok": True, "staging": name}
                elif op == "commit":
                    reply = {"ok": True, "stat": broker.commit(token, path, req["staging"])}
                elif op == "abort":
                    broker.abort(token, path, req["staging"])
                    reply = {"ok": True}
                else:
                    broker.delete(token, path)
                    reply = {"ok": True}
            except Refused as e:
                reply = {"ok": False, "status": e.status}
            except Exception:
                logger.exception("access broker request failed")
                reply = {"ok": False, "status": 500}
            try:
                if fds:
                    socket.send_fds(sock, [json.dumps(reply).encode()], fds)
                else:
                    sock.sendall(json.dumps(reply).encode())
            finally:
                for fd in fds:
                    os.close(fd)

    try:
        os.unlink(broker.s.socket_path)
    except FileNotFoundError:
        pass
    server = _BrokerServer(broker.s.socket_path, Handler)
    server.daemon_threads = True
    return server


class _BrokerServer(socketserver.ThreadingUnixStreamServer):
    # The default backlog is 5, and the file service connects with a timeout, which makes a full
    # backlog refuse at once (EAGAIN) rather than wait: a few downloads at once failed as unavailable.
    request_queue_size = socket.SOMAXCONN


# --- starting the access broker ---


def serve(
    settings: BrokerSettings,
    resolve_key=None,
    socket_mode: int = 0o660,
    socket_gid: int | None = None,
):
    """
    Start the access broker: write the canary, sweep, open the socket and start the sweeper thread.

    Return the access broker and its server, which isn't serving yet.
    """
    broker = Broker(settings, resolve_key)
    broker.write_canary()
    broker.sweep()
    server = make_server(broker)
    os.chmod(settings.socket_path, socket_mode)
    if socket_gid is not None:
        os.chown(settings.socket_path, 0, socket_gid)

    def sweeper():
        while True:
            time.sleep(settings.sweep_seconds)
            try:
                swept = broker.sweep()
                if swept:
                    logger.info("revoked %d expired link(s)", swept)
            except Exception:
                logger.exception("sweep failed")

    threading.Thread(target=sweeper, daemon=True).start()
    return broker, server


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if os.geteuid() != 0:
        raise SystemExit("the access broker must run as root")
    settings = BrokerSettings.from_env()
    _, server = serve(settings, socket_gid=int(os.getenv("BROKER_SOCKET_GID", "10001")))
    logger.info("access broker serving %s for namespace %r", settings.socket_path, settings.namespace)
    server.serve_forever()


if __name__ == "__main__":
    main()
