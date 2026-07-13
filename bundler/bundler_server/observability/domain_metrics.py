"""Domain Prometheus metrics bound to ``bundler_core`` snapshot + metrics hook."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector, CollectorRegistry

from bundler_core import get_bundle_runtime_snapshot, set_bundle_metrics_hook
from bundler_core.archive_build.timings import ArchiveBuildTimings

_SETUP_DONE = False

ARCHIVE_DOWNLOAD_SECONDS = Histogram(
    "bundler_archive_download_seconds",
    "Wall time spent downloading URLs for one archive build",
    labelnames=("strategy",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, float("inf")),
)
ARCHIVE_ZIP_SECONDS = Histogram(
    "bundler_archive_zip_seconds",
    "Wall time spent zipping one archive build",
    labelnames=("strategy",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, float("inf")),
)
ARCHIVE_TOTAL_SECONDS = Histogram(
    "bundler_archive_total_seconds",
    "Wall time for download+zip of one archive build",
    labelnames=("strategy",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, float("inf")),
)
JOBS_COMPLETED = Counter(
    "bundler_jobs_completed_total",
    "Bundle jobs that reached complete",
)
JOBS_FAILED = Counter(
    "bundler_jobs_failed_total",
    "Bundle jobs that reached failed",
    labelnames=("failure_kind",),
)


class _PrometheusBundleMetricsHook:
    def on_archive_built(self, *, strategy: str, timings: ArchiveBuildTimings) -> None:
        ARCHIVE_DOWNLOAD_SECONDS.labels(strategy=strategy).observe(timings.download_seconds)
        ARCHIVE_ZIP_SECONDS.labels(strategy=strategy).observe(timings.zip_seconds)
        ARCHIVE_TOTAL_SECONDS.labels(strategy=strategy).observe(timings.total_seconds)

    def on_job_completed(self) -> None:
        JOBS_COMPLETED.inc()

    def on_job_failed(self, *, failure_kind: str | None) -> None:
        JOBS_FAILED.labels(failure_kind=failure_kind or "unknown").inc()


class BundlerSnapshotCollector(Collector):
    """Pull gauges from ``BundleService.snapshot`` on each Prometheus scrape."""

    def collect(self):  # type: ignore[override]
        snap = get_bundle_runtime_snapshot()

        yield GaugeMetricFamily(
            "bundler_runtime_running",
            "1 if the AnyIO worker runtime is running",
            value=1.0 if snap.runtime_running else 0.0,
        )
        yield GaugeMetricFamily(
            "bundler_worker_count",
            "Configured concurrent bundle workers",
            value=float(snap.worker_count),
        )
        yield GaugeMetricFamily(
            "bundler_download_concurrency",
            "Configured max parallel URL downloads per job",
            value=float(snap.download_concurrency),
        )
        yield GaugeMetricFamily(
            "bundler_queue_max_size",
            "Configured max pending jobs on the in-process queue",
            value=float(snap.queue_max_size),
        )
        yield GaugeMetricFamily(
            "bundler_queue_depth",
            "Approximate jobs waiting on the in-process queue",
            value=float(snap.queued_jobs),
        )

        jobs = GaugeMetricFamily(
            "bundler_jobs",
            "In-memory bundle jobs by lifecycle status",
            labels=["status"],
        )
        for status, count in snap.jobs_by_status.items():
            jobs.add_metric([status], float(count))
        yield jobs


def setup_domain_metrics(*, registry: CollectorRegistry | None = None) -> None:
    """Register snapshot collector and bind the Prometheus metrics hook (idempotent)."""
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    target = registry or REGISTRY
    try:
        target.register(BundlerSnapshotCollector())
    except ValueError:
        # Collector already registered in this process (e.g. reload).
        pass

    set_bundle_metrics_hook(_PrometheusBundleMetricsHook())
    _SETUP_DONE = True
