"""
POSIX file service.

Runs on (or next to) the POSIX machine and serves files under one root directory to holders of
links signed by the portal. Single files only: download with byte ranges (so downloads can
resume), upload, metadata and delete.
"""
import logging
import os

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.auth import KeyResolver, check_token, jwks_key_resolver, token_from_request
from app.config import CANARY, Settings
from app.broker import DirectAccess, HelperAccess
from app.files import BadPath, Root, etag, file_headers, parse_range, read_chunks, split_key

logger = logging.getLogger("storage-gateway")


def create_app(settings: Settings, resolve_key: KeyResolver | None = None) -> FastAPI:
    """
    :param settings: Service settings.
    :param resolve_key: Returns the key that verifies a token; defaults to the portal's published keys.
    """
    resolve_key = resolve_key or jwks_key_resolver(settings.jwks_url)
    access = _file_access(settings)
    app = FastAPI(title="POSIX file service", docs_url=None, redoc_url=None)

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
        response = await call_next(request)
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

        range_header = request.headers.get("range")
        # If-Range: only send part of the file if it hasn't changed since the client started.
        if_range = request.headers.get("if-range")
        if range_header and if_range and if_range not in (headers["ETag"], headers["Last-Modified"]):
            range_header = None
        try:
            byte_range = parse_range(range_header, st.st_size)
        except ValueError:
            os.close(fd)
            return Response(
                status_code=416,  # Range Not Satisfiable
                headers={"Content-Range": f"bytes */{st.st_size}"},
            )

        if byte_range is None:
            start, end, code = 0, st.st_size - 1, status.HTTP_200_OK
        else:
            (start, end), code = byte_range, status.HTTP_206_PARTIAL_CONTENT
            headers["Content-Range"] = f"bytes {start}-{end}/{st.st_size}"
            headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(read_chunks(fd, start, end, settings.chunk_size), status_code=code, headers=headers)

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


def _file_access(settings: Settings):
    """
    Choose how files are reached. With a helper, this service must not be able to read the data
    itself: it checks that at startup by trying to read the helper's canary file, and refuses to start
    if it can. Without a helper, only local unit tests may run (``require_isolation`` is off).
    """
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
