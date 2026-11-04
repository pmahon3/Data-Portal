"""
Serve files under one root directory to holders of links signed by the portal (the POSIX file service).

Runs on (or next to) the POSIX machine: download with byte ranges (so downloads can resume), upload,
metadata and delete, and several files streamed as one ZIP (built as it's sent, never stored).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from functools import partial

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.auth import KeyResolver, bundle_listing, check_token, jwks_key_resolver, token_from_request
from app.file_access import BatchOpener, DirectAccess, BrokerAccess
from app.checksums import ChecksumStore
from app.config import CANARY, OPEN_BATCH, Settings
from app.files import BadPath, Root, etag, file_headers, parse_range, read_chunks, split_key
from app.metrics import Metrics
from app.zipstream import Entry, ZipStream

logger = logging.getLogger("storage-gateway")


def create_app(
    settings: Settings,
    resolve_key: KeyResolver | None = None,
    fetch_list: Callable[[str, str], str] | None = None,
) -> FastAPI:
    """
    Build the file service for ``settings``.

    ``resolve_key`` returns the key that verifies a token; by default, from the portal's published
    keys. ``fetch_list`` returns a bundle's file list, given its approval ID and link token; by default,
    it asks the portal.
    """
    if not resolve_key:
        resolve_key = jwks_key_resolver(settings.jwks_url)
    if not fetch_list:
        fetch_list = partial(_fetch_list, settings.bundle_list_url)
    access = _file_access(settings)
    checksums = ChecksumStore(settings.state_dir)  # so a resume needn't re-read earlier files
    metrics = Metrics()
    slots = DownloadSlots(settings.max_downloads)
    app = FastAPI(title="POSIX file service", docs_url=None, redoc_url=None)
    app.state.download_slots = slots

    # --- middleware ---

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "HEAD", "PUT"],
            allow_headers=["*"],
            expose_headers=["ETag", "Content-Length", "Content-Range", "Accept-Ranges"],
        )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        """
        Log one line per request, built without the query string, so a link's token is never logged
        (a logged link is usable until it expires). The link ID ties the line to the issued link.
        uvicorn's own access log is turned off (``--no-access-log``).
        """
        request.state.link_id = "-"
        try:
            response = await call_next(request)
        except Exception:
            metrics.error()
            metrics.request(request.method, _route(request), 500)
            raise
        metrics.request(request.method, _route(request), response.status_code)
        response.headers["Referrer-Policy"] = "no-referrer"
        logger.info(
            "%s %s %s link=%s",
            request.method,
            request.url.path,
            response.status_code,
            request.state.link_id,
        )
        return response

    def authorize(request: Request, resource: str) -> list[str]:
        """Check the request's token, then split the resource into path components under the root."""
        claims = check_token(
            token_from_request(request),
            resolve_key,
            namespace=settings.namespace,
            issuer=settings.issuer,
            path=resource,
            method=request.method,
        )
        request.state.link_id = claims["jti"]
        try:
            return split_key(settings.namespace, resource)
        except BadPath as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path") from e

    # --- health and metrics ---

    @app.get("/v1/health")
    def health():
        if not settings.root.is_dir():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage root unavailable",
            )
        return {"status": "ok", "namespace": settings.namespace}

    @app.get("/v1/metrics", response_class=PlainTextResponse)
    def metrics_text():
        """Return the request and error counters (Prometheus text format)."""
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    # --- one file: metadata and download ---

    @app.head("/v1/files/{resource:path}")
    def file_metadata(resource: str, request: Request):
        parts = authorize(request, resource)
        st = access.stat(token_from_request(request), resource, parts)
        return Response(status_code=status.HTTP_200_OK, headers=file_headers(parts[-1], st))

    @app.get("/v1/files/{resource:path}")
    def download(resource: str, request: Request):
        parts = authorize(request, resource)
        fd, st = access.open_read(token_from_request(request), resource, parts)
        headers = file_headers(parts[-1], st)
        validators = (headers["ETag"], headers["Last-Modified"])
        part = _part_to_send(request, st.st_size, validators, headers)
        if part is None:
            os.close(fd)
            return _unsatisfiable(st.st_size)
        start, end, code = part
        return StreamingResponse(
            read_chunks(fd, start, end, settings.chunk_size),
            status_code=code,
            headers=headers,
        )

    # --- several files as one ZIP ---

    @app.get("/v1/bundles/{resource:path}")
    def download_bundle(resource: str, request: Request):
        """Stream several files as one ZIP (stored, ZIP64), in the portal's order and folder layout."""
        token = token_from_request(request)
        claims = check_token(
            token,
            resolve_key,
            namespace=settings.namespace,
            issuer=settings.issuer,
            path=resource,
            method="GET",
            operation="bundle",
        )
        request.state.link_id = claims["jti"]
        # Wait for a slot (STREAMING-SPEC: extra downloads wait rather than fail), but not forever.
        slot = slots.acquire(timeout=settings.download_wait_seconds)
        if slot is None:
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, headers={"Retry-After": "30"})
        try:
            return _bundle_response(resource, request, token, claims, slot)
        except BaseException:
            slots.release(slot)
            raise

    def _bundle_response(resource: str, request: Request, token: str, claims: dict, slot) -> Response:
        """Return the ZIP for a bundle link already checked; ``slot`` is given back however it ends."""
        body = fetch_list(claims["grant"], token)
        listing = bundle_listing(claims, body)
        paths = listing["paths"]
        if len(paths) > settings.max_bundle_files:
            # 413 Content Too Large (the constant's name differs between Starlette versions)
            raise HTTPException(
                status_code=413,
                detail=f"A download may hold at most {settings.max_bundle_files} files",
            )
        access.register_bundle(token, resource, body)

        for path in paths:
            try:
                split_key(settings.namespace, path)
            except BadPath as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path") from e
        stats = []
        for i in range(0, len(paths), OPEN_BATCH):
            stats.extend(access.stat_many(token, paths[i:i + OPEN_BATCH], resource))
        opener = BatchOpener(access, token, resource, paths)
        entries = []
        tags = []
        for path, st in zip(paths, stats):
            if isinstance(st, HTTPException):
                raise st
            file_tag = etag(st)
            tags.append(file_tag)
            # Example: folder "StudyA" puts "posix/a/b.nii" at "StudyA/posix/a/b.nii" in the ZIP
            if listing["folder_name"]:
                name = f"{listing['folder_name']}/{path}"
            else:
                name = path
            entries.append(
                Entry(
                    name,
                    st.st_size,
                    st.st_mtime,
                    partial(opener.open, path),
                    checksums.get(path, file_tag),
                )
            )
        archive = ZipStream(entries, settings.chunk_size)
        tag = f'"{hashlib.sha256(" ".join(tags).encode()).hexdigest()}"'
        # Example: folder "Study A/scans" downloads as "Study_A_scans.zip"
        filename = re.sub(r"[^\w.-]+", "_", listing["folder_name"] or "download")
        headers = {
            "ETag": tag,
            "Accept-Ranges": "bytes",
            "Content-Type": "application/zip",
            "Content-Disposition": f'attachment; filename="{filename}.zip"',
        }

        part = _part_to_send(request, archive.size, (tag,), headers)
        if part is None:
            slots.release(slot)
            return _unsatisfiable(archive.size)
        start, end, code = part

        def stream():
            try:
                # Files are opened a batch at a time as the stream reaches them.
                with opener:
                    yield from archive.iter_bytes(start, end)
            finally:
                slots.release(slot)
            known = []
            for path, file_tag, crc in zip(listing["paths"], tags, archive.checksums()):
                if crc is not None:
                    known.append((path, file_tag, crc))
            checksums.put_many(known)

        # The background task also gives the slot back if the client left before the stream started.
        return StreamingResponse(
            stream(),
            status_code=code,
            headers=headers,
            background=BackgroundTask(slots.release, slot),
        )

    # --- one file: upload and delete ---

    @app.put("/v1/files/{resource:path}")
    async def upload(resource: str, request: Request):
        parts = authorize(request, resource)
        pending = access.begin_write(token_from_request(request), resource, parts)

        # Write beside the target (or into the link's staging area) and move it into place on commit,
        # so a failed upload never leaves a partial file in place.
        try:
            async for chunk in request.stream():
                pending.write(chunk)
            st = pending.commit()
        except BaseException:
            pending.abort()
            raise
        if pending.existed:
            code = status.HTTP_200_OK
        else:
            code = status.HTTP_201_CREATED
        return Response(status_code=code, headers={"ETag": etag(st)})

    @app.delete("/v1/files/{resource:path}")
    def delete(resource: str, request: Request):
        parts = authorize(request, resource)
        access.delete(token_from_request(request), resource, parts)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


class DownloadSlots:
    """Multi-file downloads streaming at once. Each slot is given back once, however often it's released."""

    def __init__(self, size: int):
        self.size = size
        self._free = threading.BoundedSemaphore(size)
        self._held: set[object] = set()
        self._lock = threading.Lock()

    def acquire(self, timeout: float) -> object | None:
        """Return a slot, waiting up to ``timeout`` seconds for one; None if none came free."""
        if not self._free.acquire(timeout=timeout):
            return None
        slot = object()
        with self._lock:
            self._held.add(slot)
        return slot

    def release(self, slot: object) -> None:
        with self._lock:
            if slot not in self._held:
                return
            self._held.remove(slot)
        self._free.release()

    @property
    def free(self) -> int:
        with self._lock:
            return self.size - len(self._held)


def _route(request: Request) -> str:
    """Return the matched route's template (never the path, which names a file), or ``unmatched``."""
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def _part_to_send(
    request: Request,
    size: int,
    validators: tuple[str, ...],
    headers: dict,
) -> tuple[int, int, int] | None:
    """
    Return the bytes to send as (start, end, status), and set the headers that describe them; None if
    the range can't be met. If-Range: send only part if nothing changed since the client started (it
    names one of ``validators``), otherwise all of it again.

    Example: ``Range: bytes=0-99`` on 1000 bytes gives (0, 99, 206) and ``Content-Range: bytes 0-99/1000``.
    """
    range_header = request.headers.get("range")
    if range_header and request.headers.get("if-range") not in (None, *validators):
        range_header = None
    try:
        byte_range = parse_range(range_header, size)
    except ValueError:
        return None
    if byte_range is None:
        start = 0
        end = size - 1
        code = status.HTTP_200_OK
    else:
        start, end = byte_range
        code = status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return start, end, code


def _unsatisfiable(size: int) -> Response:
    """Answer 416 Range Not Satisfiable (the constant's name differs between Starlette versions)."""
    return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})


def _fetch_list(url: str, grant: str, token: str) -> str:
    """Ask the portal for a bundle's file list, presenting the bundle's own link."""
    request = urllib.request.Request(f"{url}/{grant}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode()
    except urllib.error.HTTPError as e:
        # The portal's refusals pass through; any other answer means the portal failed.
        if e.code in (401, 403, 404):
            code = e.code
        else:
            code = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail="File list unavailable") from e
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="File list unavailable") from e


def _file_access(settings: Settings):
    """
    Choose how files are reached. With a broker, this service must not be able to read the data
    itself: it checks that at startup by trying to read the access broker's canary file, and refuses to start
    if it can. Without a broker, only local unit tests may run (``require_isolation`` is off).
    """
    if settings.shared_account:
        # Without administrator access: no broker, and this account must hold the data (the reverse
        # of the user-per-approval mode's check), or nothing could be served.
        if settings.broker_socket or settings.require_isolation:
            raise RuntimeError("GATEWAY_ACCESS=shared-account can't be combined with an access broker or required isolation")
        if not os.access(settings.root, os.R_OK | os.W_OK | os.X_OK):
            raise RuntimeError(f"GATEWAY_ACCESS=shared-account: this account can't read and write {settings.root}")
        return DirectAccess(Root(settings.root))
    if settings.broker_socket:
        try:
            fd = os.open(settings.root / CANARY, os.O_RDONLY)
        except PermissionError:
            return BrokerAccess(settings.broker_socket)
        except FileNotFoundError as e:
            raise RuntimeError(
                "The access broker's canary file is missing; can't confirm this service is isolated from the data"
            ) from e
        os.close(fd)
        raise RuntimeError(
            "This service can read the data directly; refusing to start "
            "(it must only reach files through the broker)"
        )
    if settings.require_isolation:
        raise RuntimeError("GATEWAY_REQUIRE_ISOLATION is set but no access broker socket is configured")
    return DirectAccess(Root(settings.root))


def app_from_env() -> FastAPI:
    """Build the app from the environment; the entry point for uvicorn (``--factory``)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    logger.info("Serving namespace %r from %s", settings.namespace, settings.root)
    return create_app(settings)
