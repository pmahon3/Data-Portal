from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
import os
import shutil
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

import anyio
import httpx
from anyio.from_thread import BlockingPortal, start_blocking_portal
from app.fingerprint import _bundle_key
from app.logger import logger
from app.models import BundleRecord, BundleState, CreateBundleRequest
from app.state_ops import _finalize_complete, _mark_failed, _transition_state


_TEST_STUB_MODE_ENABLED = False


class _PortalRuntime:
    """Owns BlockingPortal lifecycle and hides context-manager internals.

    This is infrastructure-only state (event-loop bridge), while BundleService
    owns domain state and workflow logic for bundle jobs.

    We use AnyIO's BlockingPortal because the public service entrypoints are
    synchronous (called by HTTP adapters/tests) while worker orchestration is
    asynchronous. The portal enables safe sync->async handoff, including
    scheduling long-lived worker supervisors and calling async queue operations
    from synchronous code paths.

    Keeping this in a dedicated runtime helper preserves separation of concerns:
    BundleService remains focused on domain transitions and job orchestration,
    and portal lifecycle/error handling stays isolated in one place.

    Terminology in this module:
    - runtime: the full background execution environment (portal lifecycle +
      worker task-group + queue stream wiring)
    - portal: the BlockingPortal handle used to call/schedule async work from
      synchronous methods
    """

    def __init__(self) -> None:
        self._portal_cm: Any | None = None
        self.portal: BlockingPortal | None = None

    @property
    def is_running(self) -> bool:
        return self.portal is not None

    def start(self) -> BlockingPortal:
        if self.portal is not None:
            return self.portal
        # Start a dedicated AnyIO event loop in a worker thread so sync code can call async workers safely.
        portal_cm = start_blocking_portal()
        portal = portal_cm.__enter__()
        self._portal_cm = portal_cm
        self.portal = portal
        return portal

    def stop(self) -> None:
        portal_cm = self._portal_cm
        self._portal_cm = None
        self.portal = None
        if portal_cm is not None:
            try:
                portal_cm.__exit__(None, None, None)
            except Exception:
                logger.exception("BlockingPortal context manager exit failed")


class BundleService:
    """Domain service for bundle workflows.

    Responsibilities:
    - Owns bundle domain state and state transitions.
    - Enqueues and processes bundle jobs.
    - Coordinates async download and zip creation.

    It composes _PortalRuntime for infrastructure concerns (sync<->async
    bridge), but keeps portal mechanics internal to this module.
    """

    def __init__(
        self,
        *,
        worker_count: int,
        download_concurrency: int,
        http_timeout_seconds: float,
        queue_max_size: int,
    ) -> None:
        # RLock is used because some code paths can re-enter lock-protected helpers on the same thread.
        self.state_lock = RLock()
        # Keep two indexes for different concerns:
        # - bundle_by_id: primary lookup for status/download by public bundle id
        # - bundle_id_by_key: idempotency lookup from normalized request fingerprint
        #
        # Today id == key, but this is intentional future-proofing. We may move
        # to generated/public ids (UUID/ULID) while keeping key as an internal
        # dedupe fingerprint so equivalent requests map to one bundle id.
        self.bundle_by_id: dict[str, BundleRecord] = {}
        self.bundle_id_by_key: dict[str, str] = {}

        self._runtime = _PortalRuntime()
        self._send_stream: anyio.streams.memory.MemoryObjectSendStream[str] | None = None

        # Two concurrency knobs at different layers:
        # - worker_count: number of bundle jobs processed concurrently
        # - download_concurrency: max parallel URL downloads within one job
        self.worker_count = worker_count
        self.download_concurrency = download_concurrency
        self.http_timeout_seconds = http_timeout_seconds
        self.queue_max_size = queue_max_size

    def _to_response(self, record: BundleRecord) -> dict[str, Any]:
        """Return HTTP-serializable bundle fields from domain state without adapter-model coupling."""
        # This stays a plain dict so core/domain logic is independent of server-layer Pydantic models.
        status_value = record.status.value if isinstance(record.status, BundleState) else str(record.status)
        return {
            "id": record.id,
            "status": status_value,
            "createdAt": record.created_at.isoformat(),
            "updatedAt": record.updated_at.isoformat(),
            "resultUrl": record.result_url,
        }

    # ------------------------------------------------------------------
    # Runtime Lifecycle (portal + queue wiring)
    # ------------------------------------------------------------------
    # Runtime lifecycle (portal + queue wiring).
    def start_runtime(self) -> None:
        with self.state_lock:
            if self._runtime.is_running:
                return
            # AnyIO memory streams integrate naturally with async task groups/cancellation and explicit close semantics.
            # A vanilla thread-safe queue would require extra bridging code for async workers and shutdown signaling.
            send_stream, receive_stream = anyio.create_memory_object_stream[str](self.queue_max_size)
            portal = self._runtime.start()
            portal.start_task_soon(self._worker_supervisor, receive_stream)
            self._send_stream = send_stream
        logger.info(
            "Bundle worker runtime started: workers={} queue_max={} download_concurrency={} http_timeout_s={}",
            self.worker_count,
            self.queue_max_size,
            self.download_concurrency,
            self.http_timeout_seconds,
        )

    def stop_runtime(self) -> None:
        with self.state_lock:
            portal = self._runtime.portal
            send_stream = self._send_stream
            self._send_stream = None

        if portal is not None and send_stream is not None:
            try:
                portal.call(send_stream.aclose)
            except Exception:
                logger.exception("Failed to close bundle worker send stream")

        self._runtime.stop()
        logger.debug("Bundle worker runtime stopped")

    async def _enqueue_bundle_id(self, bundle_id: str) -> None:
        """Enqueue one bundle id onto the async worker stream."""
        if self._send_stream is None:
            raise RuntimeError("Bundle worker queue unavailable")
        await self._send_stream.send(bundle_id)

    # ------------------------------------------------------------------
    # Public Domain API
    # ------------------------------------------------------------------
    # Public domain API methods.
    def create_bundle_job(self, create_bundle_request: Any) -> dict[str, Any]:
        """Validate input, persist a pending bundle record, and enqueue it for async processing."""
        payload: Any = create_bundle_request
        if hasattr(create_bundle_request, "model_dump"):
            payload = create_bundle_request.model_dump(by_alias=True, exclude_none=True)
        request = CreateBundleRequest.model_validate(payload)

        key = _bundle_key(request)
        now = datetime.now(tz=timezone.utc)

        with self.state_lock:
            existing_id = self.bundle_id_by_key.get(key)
            if existing_id is not None:
                # Duplicate submission: signal idempotency conflict to the HTTP layer.
                raise KeyError(f"Duplicate bundle request: {key}")

            record = BundleRecord(
                id=key,
                key=key,
                status=BundleState.PENDING,
                created_at=now,
                updated_at=now,
                folder_name=request.folder_name or "",
                compression=request.compression,
                urls=request.urls,
            )
            self.bundle_by_id[record.id] = record
            self.bundle_id_by_key[key] = record.id
            response = self._to_response(record)

        self.start_runtime()
        portal = self._runtime.portal
        # Defensive invariant check: start_runtime() should provide a portal.
        # If startup fails unexpectedly, raise a clear runtime error here.
        if portal is None:
            raise RuntimeError("Bundle worker runtime unavailable")
        portal.call(self._enqueue_bundle_id, record.id)
        logger.info(
            "Bundle job enqueued: bundle_id={} url_count={}",
            record.id,
            len(request.urls),
        )
        return response

    def get_bundle_status(self, bundle_id: str) -> dict[str, Any]:
        with self.state_lock:
            record = self.bundle_by_id.get(bundle_id)
        if record is None:
            raise KeyError(f"Bundle not found: {bundle_id}")
        return self._to_response(record)

    def download_bundle_archive(self, bundle_id: str) -> bytes:
        with self.state_lock:
            record = self.bundle_by_id.get(bundle_id)
            if record is None:
                raise KeyError(f"Bundle not found: {bundle_id}")
            if record.status != BundleState.COMPLETE:
                raise RuntimeError(f"Bundle not ready:{self._to_response(record)}")
            archive_path = record.archive_path

        if archive_path is None:
            raise RuntimeError("Bundle not ready")
        try:
            return Path(archive_path).read_bytes()
        except Exception as exc:
            with self.state_lock:
                _mark_failed(record, exc)
            logger.exception("Failed to read bundle archive: bundle_id={}", bundle_id)
            raise RuntimeError(f"Failed to read bundle archive: {exc}") from exc

    # ------------------------------------------------------------------
    # Sync/Async Bridge
    # ------------------------------------------------------------------
    # Sync/async bridge helper for tests/debug tooling.
    @logger.catch
    def build_bundle_zip(self, record: BundleRecord) -> Path:
        return anyio.run(self._build_bundle_archive, record)

    # ------------------------------------------------------------------
    # Worker Orchestration
    # ------------------------------------------------------------------
    # Worker orchestration and job execution.
    async def _worker_supervisor(
        self, receive_stream: anyio.streams.memory.MemoryObjectReceiveStream[str]
    ) -> None:
        async with receive_stream:
            async with anyio.create_task_group() as tg:
                for _ in range(self.worker_count):
                    tg.start_soon(self._worker_consumer, receive_stream.clone())

    async def _worker_consumer(
        self, receive_stream: anyio.streams.memory.MemoryObjectReceiveStream[str]
    ) -> None:
        async with receive_stream:
            while True:
                try:
                    bundle_id = await receive_stream.receive()
                except anyio.EndOfStream:
                    return
                await self._process_bundle_job(bundle_id)

    async def _process_bundle_job(self, bundle_id: str) -> None:
        """Process one queued bundle id through transition, build, and completion/failure finalization."""
        with self.state_lock:
            record = self.bundle_by_id.get(bundle_id)
            if record is None:
                logger.warning("Bundle job skipped: unknown bundle_id={}", bundle_id)
                return
            if record.status != BundleState.PENDING:
                st = record.status.value if isinstance(record.status, BundleState) else str(record.status)
                logger.warning(
                    "Bundle job skipped: bundle_id={} status={} (expected PENDING)",
                    bundle_id,
                    st,
                )
                return
            _transition_state(record, BundleState.PROCESSING)
        try:
            archive_path = await self._build_bundle_archive(record)
        except Exception as exc:
            with self.state_lock:
                _mark_failed(record, exc)
            logger.exception("Bundle archive build failed: {}", bundle_id)
            return

        with self.state_lock:
            try:
                _finalize_complete(record, archive_path)
            except Exception as exc:
                archive_path.unlink(missing_ok=True)
                _mark_failed(record, exc)
                logger.exception("Bundle finalize failed: {}", bundle_id)
            else:
                logger.info(
                    "Bundle job completed: bundle_id={} size_bytes={}",
                    record.id,
                    record.archive_size_bytes,
                )

    # ------------------------------------------------------------------
    # Bundling Internals (name mapping, download, archive assembly)
    # ------------------------------------------------------------------
    # Bundling internals (name mapping, download, archive assembly).
    @staticmethod
    def _archive_name_from_url(url: str, index: int) -> str | None:
        """Map source URL to archive path using URL-derived root prefix.

        Contract:
        - Keep the first decoded path segment as the archive root (for example bucket name).
        - Preserve remaining decoded nested path segments.
        - If URL path is a trailing slash directory marker, treat it as an empty
          folder reference and return ``None`` so no ZIP member is created.
        - If no usable path segment exists, treat as pathless and return ``None``
          so no ZIP member is created.
        """
        raw_decoded_path = unquote(urlsplit(url).path)
        decoded_path = raw_decoded_path.lstrip("/")
        segments = [segment for segment in decoded_path.split("/") if segment]
        if not segments:
            return None

        if raw_decoded_path.endswith("/"):
            return None

        root = segments[0]
        tail = segments[1:]
        if not tail:
            return None
        return "/".join([root, *tail])

    async def _download_url_to_file(
        self,
        client: httpx.AsyncClient,
        semaphore: anyio.Semaphore,
        url: str,
        target: Path,
    ) -> None:
        if _TEST_STUB_MODE_ENABLED and url == "__bundler_stub__":
            async with await anyio.open_file(target, "wb") as out_f:
                await out_f.write(b"stub")
            return

        async with semaphore:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async with await anyio.open_file(target, "wb") as out_f:
                    async for chunk in response.aiter_bytes():
                        await out_f.write(chunk)

    async def _build_bundle_archive(self, record: BundleRecord) -> Path:
        """Build one bundle archive by downloading eligible URLs and zipping staged files."""
        # Per-bundle staging workspace: isolates concurrent jobs and simplifies cleanup/debugging.
        temp_dir = Path(tempfile.mkdtemp(prefix=f"bundle-stage-{record.id}-"))
        downloaded_files: list[tuple[str, Path]] = []
        timeout = httpx.Timeout(self.http_timeout_seconds)
        # Bound concurrent downloads to avoid unbounded sockets/memory usage when
        # a bundle contains many URLs. TaskGroup structures task lifetime; this
        # semaphore enforces capacity/backpressure.
        semaphore = anyio.Semaphore(self.download_concurrency)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with anyio.create_task_group() as tg:
                    for index, url in enumerate(record.urls, start=1):
                        archive_name = self._archive_name_from_url(url, index)
                        if archive_name is None:
                            continue
                        # Stable local temp filename (not URL-derived) to avoid path traversal and name collisions.
                        stage_path = temp_dir / f"download-{index:05d}.bin"
                        downloaded_files.append((archive_name, stage_path))
                        tg.start_soon(self._download_url_to_file, client, semaphore, url, stage_path)

            # Keep download and zipping separate: downloads are async IO-bound
            # work, while zip creation is blocking file/CPU work offloaded to a
            # worker thread to keep the event loop responsive.
            archive_path = await anyio.to_thread.run_sync(
                self._zip_from_files,
                downloaded_files,
                record.id,
            )
            return archive_path
        finally:
            await anyio.to_thread.run_sync(shutil.rmtree, temp_dir, True)

    @staticmethod
    def _zip_from_files(files: list[tuple[str, Path]], bundle_id: str) -> Path:
        with tempfile.NamedTemporaryFile(prefix=f"bundle-{bundle_id}-", suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        with zipfile.ZipFile(tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for archive_name, file_path in files:
                zf.write(file_path, arcname=archive_name)
        return tmp_path

    # ------------------------------------------------------------------
    # Test Hook
    # ------------------------------------------------------------------
    # Test hook.
    def reset_runtime_state_for_tests(self) -> None:
        with self.state_lock:
            records = list(self.bundle_by_id.values())
            self.bundle_by_id.clear()
            self.bundle_id_by_key.clear()
        self.stop_runtime()

        for record in records:
            if record.archive_path:
                Path(record.archive_path).unlink(missing_ok=True)


_DEFAULT_SERVICE = BundleService(
    worker_count=max(1, int(os.getenv("BUNDLER_WORKER_COUNT", "1"))),
    download_concurrency=max(1, int(os.getenv("BUNDLER_DOWNLOAD_CONCURRENCY", "4"))),
    http_timeout_seconds=float(os.getenv("BUNDLER_HTTP_TIMEOUT_SECONDS", "60")),
    queue_max_size=max(1, int(os.getenv("BUNDLER_QUEUE_MAX_SIZE", "1024"))),
)

# Backward-compatible internal symbols used by tests.
_STATE_LOCK = _DEFAULT_SERVICE.state_lock
_BUNDLE_BY_ID = _DEFAULT_SERVICE.bundle_by_id
_BUNDLE_ID_BY_KEY = _DEFAULT_SERVICE.bundle_id_by_key

def create_bundle_job(create_bundle_request: Any) -> dict[str, Any]:
    return _DEFAULT_SERVICE.create_bundle_job(create_bundle_request)


def get_bundle_status(bundle_id: str) -> dict[str, Any]:
    return _DEFAULT_SERVICE.get_bundle_status(bundle_id)


def download_bundle_archive(bundle_id: str) -> bytes:
    return _DEFAULT_SERVICE.download_bundle_archive(bundle_id)


def _reset_runtime_state_for_tests() -> None:
    _DEFAULT_SERVICE.reset_runtime_state_for_tests()
