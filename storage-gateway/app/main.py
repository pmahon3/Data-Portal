"""
POSIX file service.

Runs on (or next to) the POSIX machine and serves files under one root directory to holders of
links signed by the portal: download with byte ranges (so downloads can resume), upload, metadata
and delete, and several files streamed as one ZIP (built as it's sent, never stored).
"""
import hashlib
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.auth import KeyResolver, bundle_listing, check_token, jwks_key_resolver, token_from_request
from app.config import CANARY, OPEN_BATCH, Settings
from app.broker import BatchOpener, DirectAccess, HelperAccess
from app.checksums import ChecksumStore
from app.files import BadPath, Root, etag, file_headers, parse_range, read_chunks, split_key
from app.metrics import Metrics
from app.zipstream import Entry, ZipStream

logger = logging.getLogger("storage-gateway")


def create_app(settings: Settings, resolve_key: KeyResolver | None = None,
               fetch_list: Callable[[str, str], str] | None = None) -> FastAPI:
    """
    :param settings: Service settings.
    :param resolve_key: Returns the key that verifies a token; defaults to the portal's published keys.
    :param fetch_list: Returns a bundle's file list, given its approval ID and link token; defaults to
        asking the portal.
    """
    resolve_key = resolve_key or jwks_key_resolver(settings.jwks_url)
    fetch_list = fetch_list or (lambda grant, token: _fetch_list(settings.bundle_list_url, grant, token))
    access = _file_access(settings)
    checksums = ChecksumStore(settings.state_dir)  # so a resume needn't re-read earlier files
    metrics = Metrics()
    slots = DownloadSlots(settings.max_downloads)
    app = FastAPI(title="POSIX file service", docs_url=None, redoc_url=None)
    app.state.download_slots = slots

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
        One line per request, built without the query string, so a link's token is never logged
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
            "%s %s %s link=%s", request.method, request.url.path, response.status_code, request.state.link_id
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
        except BadPath:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path")

    @app.get("/v1/health")
    def health():
        if not settings.root.is_dir():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Storage root unavailable")
        return {"status": "ok", "namespace": settings.namespace}

    @app.get("/v1/metrics", response_class=PlainTextResponse)
    def metrics_text():
        """Request and error counters (Prometheus text format)."""
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

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
        part = _part_to_send(request, st.st_size, (headers["ETag"], headers["Last-Modified"]), headers)
        if part is None:
            os.close(fd)
            return _unsatisfiable(st.st_size)
        start, end, code = part
        return StreamingResponse(read_chunks(fd, start, end, settings.chunk_size), status_code=code, headers=headers)

    @app.get("/v1/bundles/{resource:path}")
    def download_bundle(resource: str, request: Request):
        """Several files as one ZIP (stored, ZIP64), in the portal's order and folder layout."""
        token = token_from_request(request)
        claims = check_token(token, resolve_key, namespace=settings.namespace, issuer=settings.issuer,
                             path=resource, method="GET", operation="bundle")
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
        """The ZIP for a bundle link already checked; ``slot`` is given back however the download ends."""
        body = fetch_list(claims["grant"], token)
        listing = bundle_listing(claims, body)
        paths = listing["paths"]
        if len(paths) > settings.max_bundle_files:
            raise HTTPException(status_code=413,  # Content Too Large
                                detail=f"A download may hold at most {settings.max_bundle_files} files")
        access.register_bundle(token, resource, body)

        for path in paths:
            try:
                split_key(settings.namespace, path)
            except BadPath:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path")
        stats = [st for i in range(0, len(paths), OPEN_BATCH)
                 for st in access.stat_many(token, paths[i:i + OPEN_BATCH], resource)]
        opener = BatchOpener(access, token, resource, paths)
        entries, tags = [], []
        for path, st in zip(paths, stats):
            if isinstance(st, HTTPException):
                raise st
            tags.append(etag(st))
            name = f"{listing['folder_name']}/{path}" if listing["folder_name"] else path
            entries.append(Entry(name, st.st_size, st.st_mtime, lambda path=path: opener.open(path),
                                 checksums.get(path, tags[-1])))
        archive = ZipStream(entries, settings.chunk_size)
        tag = f'"{hashlib.sha256(" ".join(tags).encode()).hexdigest()}"'
        filename = re.sub(r"[^\w.-]+", "_", listing["folder_name"] or "download")
        headers = {"ETag": tag, "Accept-Ranges": "bytes", "Content-Type": "application/zip",
                   "Content-Disposition": f'attachment; filename="{filename}.zip"'}

        part = _part_to_send(request, archive.size, (tag,), headers)
        if part is None:
            slots.release(slot)
            return _unsatisfiable(archive.size)
        start, end, code = part

        def stream():
            try:
                with opener:  # files are opened a batch at a time as the stream reaches them
                    yield from archive.iter_bytes(start, end)
            finally:
                slots.release(slot)
            checksums.put_many([(p, t, crc) for p, t, crc in zip(listing["paths"], tags, archive.checksums())
                                if crc is not None])

        # The background task also gives the slot back if the client left before the stream started.
        return StreamingResponse(stream(), status_code=code, headers=headers,
                                 background=BackgroundTask(slots.release, slot))

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
        return Response(
            status_code=status.HTTP_200_OK if pending.existed else status.HTTP_201_CREATED,
            headers={"ETag": etag(st)},
        )

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
        """A slot, waiting up to ``timeout`` seconds for one; None if none came free."""
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
    """The matched route's template (never the path, which names a file), or ``unmatched``."""
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def _part_to_send(request: Request, size: int, validators: tuple[str, ...],
                  headers: dict) -> tuple[int, int, int] | None:
    """
    The bytes to send, (start, end, status), with the headers that describe them; None if the range
    can't be met. If-Range: send only part if nothing changed since the client started (it names one
    of ``validators``), otherwise all of it again.
    """
    range_header = request.headers.get("range")
    if range_header and request.headers.get("if-range") not in (None, *validators):
        range_header = None
    try:
        byte_range = parse_range(range_header, size)
    except ValueError:
        return None
    if byte_range is None:
        start, end, code = 0, size - 1, status.HTTP_200_OK
    else:
        (start, end), code = byte_range, status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return start, end, code


def _unsatisfiable(size: int) -> Response:
    return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})  # Range Not Satisfiable


def _fetch_list(url: str, grant: str, token: str) -> str:
    """Ask the portal for a bundle's file list, presenting the bundle's own link."""
    request = urllib.request.Request(f"{url}/{grant}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode()
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=e.code if e.code in (401, 403, 404) else 502, detail="File list unavailable")
    except OSError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="File list unavailable")


def _file_access(settings: Settings):
    """
    Choose how files are reached. With a helper, this service must not be able to read the data
    itself: it checks that at startup by trying to read the helper's canary file, and refuses to start
    if it can. Without a helper, only local unit tests may run (``require_isolation`` is off).
    """
    if settings.account_mode:
        # Without administrator access: no helper, and this account must hold the data (the reverse
        # of the helper mode's check), or nothing could be served.
        if settings.helper_socket or settings.require_isolation:
            raise RuntimeError("GATEWAY_ACCESS=account can't be combined with a helper or required isolation")
        if not os.access(settings.root, os.R_OK | os.W_OK | os.X_OK):
            raise RuntimeError(f"GATEWAY_ACCESS=account: this account can't read and write {settings.root}")
        return DirectAccess(Root(settings.root))
    if settings.helper_socket:
        try:
            fd = os.open(settings.root / CANARY, os.O_RDONLY)
        except PermissionError:
            return HelperAccess(settings.helper_socket)
        except FileNotFoundError:
            raise RuntimeError("The helper's canary file is missing; can't confirm this service is isolated from the data")
        os.close(fd)
        raise RuntimeError("This service can read the data directly; refusing to start (it must only reach files through the helper)")
    if settings.require_isolation:
        raise RuntimeError("GATEWAY_REQUIRE_ISOLATION is set but no helper socket is configured")
    return DirectAccess(Root(settings.root))


def app_from_env() -> FastAPI:
    """Entry point for uvicorn (``--factory``)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    logger.info("Serving namespace %r from %s", settings.namespace, settings.root)
    return create_app(settings)
