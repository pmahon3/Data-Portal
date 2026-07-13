from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
import os
from urllib.parse import unquote, urlsplit

import anyio
import httpx
from anyio.from_thread import BlockingPortal, start_blocking_portal
from bundler_core.archive_build.context import ArchiveBuildContext
from bundler_core.archive_build.factory import create_archive_build_strategy
from bundler_core.archive_build.protocol import ArchiveBuildStrategy
from bundler_core.archive_build.timings import ArchiveBuildResult
from bundler_core.failures import MAX_BUNDLE_RETRIES, FailureKind
from bundler_core.fingerprint import _bundle_key
from bundler_core.job_store import JobStorePort, create_job_store
from bundler_core.job_store.memory import InMemoryJobStore
from bundler_core.logger import logger
from bundler_core.models import BundleRecord, BundleState, CreateBundleRequest
from bundler_core.observability import BundleMetricsHook, BundleRuntimeSnapshot
from bundler_core.state_ops import _finalize_complete, _mark_failed, _requeue_for_retry, _transition_state


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
        archive_strategy: ArchiveBuildStrategy | None = None,
        job_store: JobStorePort | None = None,
    ) -> None:
        # RLock is used because some code paths can re-enter lock-protected helpers on the same thread.
        self.state_lock = RLock()
        self._store: JobStorePort = job_store if job_store is not None else create_job_store()
        # Compat for tests that poke the legacy in-memory maps directly.
        if isinstance(self._store, InMemoryJobStore):
            self.bundle_by_id = self._store.by_id
            self.bundle_id_by_key = self._store.by_key
        else:
            self.bundle_by_id = {}
            self.bundle_id_by_key = {}

        self._runtime = _PortalRuntime()
        self._send_stream: anyio.streams.memory.MemoryObjectSendStream[str] | None = None
        # Approximate jobs waiting on the memory stream (enqueue − dequeue).
        self._queued_jobs = 0
        self._metrics_hook: BundleMetricsHook | None = None

        # Two concurrency knobs at different layers:
        # - worker_count: number of bundle jobs processed concurrently
        # - download_concurrency: max parallel URL downloads within one job
        self.worker_count = worker_count
        self.download_concurrency = download_concurrency
        self.http_timeout_seconds = http_timeout_seconds
        self.queue_max_size = queue_max_size
        self._archive_strategy = archive_strategy or create_archive_build_strategy()

    def _save(self, record: BundleRecord) -> None:
        self._store.save(record)

    def set_metrics_hook(self, hook: BundleMetricsHook | None) -> None:
        """Attach or clear the optional push metrics hook (adapter-owned)."""
        self._metrics_hook = hook

    def snapshot(self) -> BundleRuntimeSnapshot:
        """Return a lock-consistent runtime/job inventory for readiness and gauges."""
        with self.state_lock:
            return BundleRuntimeSnapshot(
                runtime_running=self._runtime.is_running,
                worker_count=self.worker_count,
                download_concurrency=self.download_concurrency,
                queue_max_size=self.queue_max_size,
                queued_jobs=self._queued_jobs,
                jobs_by_status=self._store.count_by_status(),
            )

    def _notify_metrics(self, method: str, **kwargs: Any) -> None:
        hook = self._metrics_hook
        if hook is None:
            return
        try:
            getattr(hook, method)(**kwargs)
        except Exception:
            logger.exception("Bundle metrics hook failed: method={}", method)

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

    def _can_retry_failed(self, record: BundleRecord) -> bool:
        if record.failure_kind == FailureKind.PERMANENT:
            return False
        if record.failure_kind not in {FailureKind.TRANSIENT, FailureKind.UNKNOWN, None}:
            return False
        return record.retry_count < MAX_BUNDLE_RETRIES

    def _retry_failed_bundle(
        self,
        record: BundleRecord,
        request: CreateBundleRequest,
        key: str,
    ) -> dict[str, Any]:
        """Re-queue a failed bundle when retry policy allows it."""
        if not self._can_retry_failed(record):
            raise KeyError(f"Duplicate bundle request: {key}")

        record.urls = list(request.urls)
        record.folder_name = request.folder_name or ""
        record.compression = request.compression
        record.retry_count += 1
        _requeue_for_retry(record)
        self._save(record)
        return self._to_response(record)

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
            self._queued_jobs = 0

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
        with self.state_lock:
            self._queued_jobs += 1

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
            existing_record = self._store.get_by_key(key)
            if existing_record is not None:
                if existing_record.status == BundleState.COMPLETE:
                    return self._to_response(existing_record)
                if existing_record.status == BundleState.FAILED:
                    response = self._retry_failed_bundle(existing_record, request, key)
                    bundle_id = existing_record.id
                else:
                    raise KeyError(f"Duplicate bundle request: {key}")
            else:
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
                self._save(record)
                response = self._to_response(record)
                bundle_id = record.id

        self.start_runtime()
        portal = self._runtime.portal
        # Defensive invariant check: start_runtime() should provide a portal.
        # If startup fails unexpectedly, raise a clear runtime error here.
        if portal is None:
            raise RuntimeError("Bundle worker runtime unavailable")
        portal.call(self._enqueue_bundle_id, bundle_id)
        logger.info(
            "Bundle job enqueued: bundle_id={} url_count={}",
            bundle_id,
            len(request.urls),
        )
        return response

    def get_bundle_status(self, bundle_id: str) -> dict[str, Any]:
        with self.state_lock:
            record = self._store.get(bundle_id)
        if record is None:
            raise KeyError(f"Bundle not found: {bundle_id}")
        return self._to_response(record)

    def download_bundle_archive(self, bundle_id: str) -> bytes:
        with self.state_lock:
            record = self._store.get(bundle_id)
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
                self._save(record)
            logger.exception("Failed to read bundle archive: bundle_id={}", bundle_id)
            raise RuntimeError(f"Failed to read bundle archive: {exc}") from exc

    # ------------------------------------------------------------------
    # Sync/Async Bridge
    # ------------------------------------------------------------------
    # Sync/async bridge helper for tests/debug tooling.
    @logger.catch
    def build_bundle_zip(self, record: BundleRecord) -> Path:
        result = anyio.run(self._build_bundle_archive, record)
        return result.archive_path

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
                with self.state_lock:
                    self._queued_jobs = max(0, self._queued_jobs - 1)
                await self._process_bundle_job(bundle_id)

    async def _process_bundle_job(self, bundle_id: str) -> None:
        """Process one queued bundle id through transition, build, and completion/failure finalization."""
        with self.state_lock:
            record = self._store.get(bundle_id)
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
            self._save(record)
        try:
            build_result = await self._build_bundle_archive(record)
        except Exception as exc:
            with self.state_lock:
                _mark_failed(record, exc)
                self._save(record)
                failure_kind = record.failure_kind.value if record.failure_kind is not None else None
            self._notify_metrics("on_job_failed", failure_kind=failure_kind)
            logger.exception("Bundle archive build failed: {}", bundle_id)
            return

        # --- observability: record/log build timings (does not affect finalize or job outcome) ---
        with self.state_lock:
            self._observe_archive_build_timings(record, build_result)
            strategy = record.last_build_strategy or self._archive_strategy_name()
            timings = build_result.timings
            try:
                _finalize_complete(record, build_result.archive_path)
            except Exception as exc:
                build_result.archive_path.unlink(missing_ok=True)
                _mark_failed(record, exc)
                failure_kind = record.failure_kind.value if record.failure_kind is not None else None
                finalize_ok = False
                logger.exception("Bundle finalize failed: {}", bundle_id)
            else:
                failure_kind = None
                finalize_ok = True
                logger.info(
                    "Bundle job completed: bundle_id={} size_bytes={}",
                    record.id,
                    record.archive_size_bytes,
                )
            self._save(record)

        self._notify_metrics("on_archive_built", strategy=strategy, timings=timings)
        if finalize_ok:
            self._notify_metrics("on_job_completed")
        else:
            self._notify_metrics("on_job_failed", failure_kind=failure_kind)

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

    def _archive_strategy_name(self) -> str:
        strategy = self._archive_strategy
        name = getattr(strategy, "STRATEGY_NAME", None)
        if isinstance(name, str) and name:
            return name
        return type(strategy).__name__

    def _observe_archive_build_timings(
        self,
        record: BundleRecord,
        build_result: ArchiveBuildResult,
    ) -> None:
        """Persist and log archive build timings. Observability only; does not affect bundle outcome."""
        timings = build_result.timings
        strategy = self._archive_strategy_name()
        record.last_build_timings = timings
        record.last_build_strategy = strategy
        logger.info(
            "Bundle archive built: bundle_id={} strategy={} download_s={:.3f} zip_s={:.3f} total_s={:.3f} url_count={}",
            record.id,
            strategy,
            timings.download_seconds,
            timings.zip_seconds,
            timings.total_seconds,
            timings.url_count,
        )

    def _archive_build_context(self) -> ArchiveBuildContext:
        """Build strategy dependencies from current service settings (resolved at build time)."""
        return ArchiveBuildContext(
            archive_name_from_url=self._archive_name_from_url,
            download_url_to_file=self._download_url_to_file,
            download_concurrency=self.download_concurrency,
            http_timeout_seconds=self.http_timeout_seconds,
        )

    async def _build_bundle_archive(self, record: BundleRecord) -> ArchiveBuildResult:
        """Build one bundle archive via the configured archive build strategy."""
        return await self._archive_strategy.build(record, self._archive_build_context())

    # ------------------------------------------------------------------
    # Test Hook
    # ------------------------------------------------------------------
    # Test hook.
    def reset_runtime_state_for_tests(self) -> None:
        with self.state_lock:
            records = self._store.list_all()
            self._store.clear()
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


def get_bundle_runtime_snapshot() -> BundleRuntimeSnapshot:
    return _DEFAULT_SERVICE.snapshot()


def set_bundle_metrics_hook(hook: BundleMetricsHook | None) -> None:
    _DEFAULT_SERVICE.set_metrics_hook(hook)


def _reset_runtime_state_for_tests() -> None:
    _DEFAULT_SERVICE.reset_runtime_state_for_tests()
