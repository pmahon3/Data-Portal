"""Attach Prometheus metrics and Actuator-style ops routes to a FastAPI app.

Call once from the hand-owned ASGI entry (``observability.app``). Generated
``bundler_server.main`` stays untouched.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

_SETUP_ATTR = "_bundler_observability_setup"
_STARTED_AT = datetime.now(tz=timezone.utc)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _metrics_enabled() -> bool:
    return _env_flag("BUNDLER_METRICS_ENABLED", default=True)


def _actuator_enabled() -> bool:
    return _env_flag("BUNDLER_ACTUATOR_ENABLED", default=True)


def _readiness_payload() -> tuple[int, dict[str, object]]:
    """Evaluate domain readiness (queue capacity). Liveness stays process-only."""
    from bundler_core import get_bundle_runtime_snapshot

    snap = get_bundle_runtime_snapshot()
    queue_ok = snap.queued_jobs < snap.queue_max_size
    status = "UP" if queue_ok else "DOWN"
    code = 200 if queue_ok else 503
    return code, {
        "status": status,
        "components": {
            "queue": {"status": "UP" if queue_ok else "DOWN"},
        },
        "details": {
            "runtimeRunning": snap.runtime_running,
            "queuedJobs": snap.queued_jobs,
            "queueMaxSize": snap.queue_max_size,
            "workerCount": snap.worker_count,
            "downloadConcurrency": snap.download_concurrency,
            "jobsByStatus": snap.jobs_by_status,
        },
    }


def _build_actuator_router() -> APIRouter:
    """Minimal Spring-Actuator-like ops routes (not part of the product OpenAPI)."""
    router = APIRouter(tags=["actuator"])

    @router.get("/actuator")
    async def actuator_index() -> dict[str, list[str]]:
        return {
            "links": [
                "/actuator",
                "/actuator/health/live",
                "/actuator/health/ready",
                "/actuator/info",
            ]
        }

    @router.get("/actuator/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "UP"}

    @router.get("/actuator/health/ready")
    async def health_ready() -> JSONResponse:
        status_code, body = _readiness_payload()
        return JSONResponse(status_code=status_code, content=body)

    @router.get("/actuator/info")
    async def info() -> dict[str, object]:
        from bundler_core import get_bundle_runtime_snapshot

        snap = get_bundle_runtime_snapshot()
        return {
            "app": {
                "name": os.environ.get("OTEL_SERVICE_NAME", "bundler"),
                "startedAt": _STARTED_AT.isoformat(),
            },
            "bundler": {
                "runtimeRunning": snap.runtime_running,
                "workerCount": snap.worker_count,
                "downloadConcurrency": snap.download_concurrency,
                "queueMaxSize": snap.queue_max_size,
            },
        }

    return router


def _attach_prometheus(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator

    from bundler_server.observability.domain_metrics import setup_domain_metrics

    setup_domain_metrics()

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=[
            "/metrics",
            "/actuator",
            "/actuator/health/live",
            "/actuator/health/ready",
            "/actuator/info",
        ],
    )
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        should_gzip=True,
    )


def setup_observability(app: FastAPI) -> FastAPI:
    """Instrument ``app`` in place and return it (idempotent)."""
    if getattr(app.state, _SETUP_ATTR, False):
        return app

    if _metrics_enabled():
        _attach_prometheus(app)

    if _actuator_enabled():
        app.include_router(_build_actuator_router())

    setattr(app.state, _SETUP_ATTR, True)
    return app
