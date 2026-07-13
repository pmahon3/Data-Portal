"""Runtime snapshot helpers for ``BundleService`` observability."""

from __future__ import annotations

from bundler_core.bundles import BundleService
from bundler_core.models import BundleRecord, BundleState
from datetime import datetime, timezone


def test_snapshot_counts_jobs_by_status() -> None:
    service = BundleService(
        worker_count=2,
        download_concurrency=4,
        http_timeout_seconds=30.0,
        queue_max_size=16,
    )
    now = datetime.now(tz=timezone.utc)
    service._store.save(
        BundleRecord(
            id="a",
            key="a",
            status=BundleState.PENDING,
            created_at=now,
            updated_at=now,
            folder_name="f",
            compression="zip",
            urls=["https://example.com/a"],
        )
    )
    service._store.save(
        BundleRecord(
            id="b",
            key="b",
            status=BundleState.COMPLETE,
            created_at=now,
            updated_at=now,
            folder_name="f",
            compression="zip",
            urls=["https://example.com/b"],
        )
    )

    snap = service.snapshot()
    assert snap.runtime_running is False
    assert snap.worker_count == 2
    assert snap.queue_max_size == 16
    assert snap.queued_jobs == 0
    assert snap.jobs_by_status["pending"] == 1
    assert snap.jobs_by_status["complete"] == 1
    assert snap.jobs_by_status["processing"] == 0
    assert snap.jobs_by_status["failed"] == 0
