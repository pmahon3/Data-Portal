"""Domain-facing observability types (no Prometheus/OTel dependency).

The HTTP adapter binds a metrics hook and scrapes :meth:`BundleService.snapshot`
for gauges/readiness. Core stays free of vendor SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bundler_core.archive_build.timings import ArchiveBuildTimings


@dataclass(frozen=True)
class BundleRuntimeSnapshot:
    """Point-in-time view of bundle worker capacity and job inventory."""

    runtime_running: bool
    worker_count: int
    download_concurrency: int
    queue_max_size: int
    queued_jobs: int
    jobs_by_status: dict[str, int]


class BundleMetricsHook(Protocol):
    """Optional push hooks for terminal events and archive build timings."""

    def on_archive_built(self, *, strategy: str, timings: ArchiveBuildTimings) -> None:
        """Record one successful archive assembly attempt (timings only)."""

    def on_job_completed(self) -> None:
        """Record a job that reached ``complete``."""

    def on_job_failed(self, *, failure_kind: str | None) -> None:
        """Record a job that reached ``failed``."""
