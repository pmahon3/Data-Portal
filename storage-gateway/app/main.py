"""
POSIX file service.

Runs on (or next to) the POSIX machine and serves files under one root directory to holders of
links signed by the portal. Single files only: download with byte ranges (so downloads can
resume), upload, metadata and delete.
"""
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.auth import KeyResolver, check_token, jwks_key_resolver, token_from_request
from app.config import Settings
from app.files import BadPath, etag, file_headers, parse_range, read_chunks, resolve
from app.logs import install_token_redaction

logger = logging.getLogger("storage-gateway")


def create_app(settings: Settings, resolve_key: KeyResolver | None = None) -> FastAPI:
    """
    :param settings: Service settings.
    :param resolve_key: Returns the key that verifies a token; defaults to the portal's published keys.
    """
    resolve_key = resolve_key or jwks_key_resolver(settings.jwks_url)
    app = FastAPI(title="POSIX file service", docs_url=None, redoc_url=None)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "HEAD", "PUT"],
            allow_headers=["*"],
            expose_headers=["ETag", "Content-Length", "Content-Range", "Accept-Ranges"],
        )

    def authorize(request: Request, resource: str) -> Path:
        """Check the request's token, then map the resource to a path under the root."""
        check_token(
            token_from_request(request),
            resolve_key,
            namespace=settings.namespace,
            issuer=settings.issuer,
            path=resource,
            method=request.method,
        )
        try:
            return resolve(settings.root, settings.namespace, resource)
        except BadPath:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad path")

    def existing_file(path: Path) -> os.stat_result:
        try:
            stat = path.stat()
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return stat

    @app.get("/v1/health")
    def health():
        if not settings.root.is_dir():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Storage root unavailable")
        return {"status": "ok", "namespace": settings.namespace}

    @app.head("/v1/files/{resource:path}")
    def file_metadata(resource: str, request: Request):
        path = authorize(request, resource)
        stat = existing_file(path)
        return Response(status_code=status.HTTP_200_OK, headers=file_headers(path, stat))

    @app.get("/v1/files/{resource:path}")
    def download(resource: str, request: Request):
        path = authorize(request, resource)
        stat = existing_file(path)
        headers = file_headers(path, stat)

        range_header = request.headers.get("range")
        # If-Range: only send part of the file if it hasn't changed since the client started.
        if_range = request.headers.get("if-range")
        if range_header and if_range and if_range not in (headers["ETag"], headers["Last-Modified"]):
            range_header = None
        try:
            byte_range = parse_range(range_header, stat.st_size)
        except ValueError:
            return Response(
                status_code=416,  # Range Not Satisfiable
                headers={"Content-Range": f"bytes */{stat.st_size}"},
            )

        if byte_range is None:
            start, end, code = 0, stat.st_size - 1, status.HTTP_200_OK
        else:
            (start, end), code = byte_range, status.HTTP_206_PARTIAL_CONTENT
            headers["Content-Range"] = f"bytes {start}-{end}/{stat.st_size}"
            headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            read_chunks(path, start, end, settings.chunk_size), status_code=code, headers=headers
        )

    @app.put("/v1/files/{resource:path}")
    async def upload(resource: str, request: Request):
        path = authorize(request, resource)
        if path.is_dir():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder exists at this path")
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write beside the target and rename, so a failed upload never leaves a partial file in place.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return Response(
            status_code=status.HTTP_200_OK if existed else status.HTTP_201_CREATED,
            headers={"ETag": etag(path.stat())},
        )

    @app.delete("/v1/files/{resource:path}")
    def delete(resource: str, request: Request):
        path = authorize(request, resource)
        existing_file(path)
        path.unlink()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


def app_from_env() -> FastAPI:
    """Entry point for uvicorn (``--factory``)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    install_token_redaction()
    settings = Settings.from_env()
    logger.info("Serving namespace %r from %s", settings.namespace, settings.root)
    return create_app(settings)
