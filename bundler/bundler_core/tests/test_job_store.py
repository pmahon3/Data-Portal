"""Job store unit tests (memory + Mongo document mapping; no live Mongo required)."""

from __future__ import annotations

from datetime import datetime, timezone

from bundler_core.archive_build.timings import ArchiveBuildTimings
from bundler_core.failures import FailureKind
from bundler_core.job_store.factory import create_job_store
from bundler_core.job_store.memory import InMemoryJobStore
from bundler_core.job_store.mongo import _doc_to_record, _record_to_doc
from bundler_core.models import BundleRecord, BundleState


def test_create_job_store_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("MONGO_URI", raising=False)
    store = create_job_store()
    assert isinstance(store, InMemoryJobStore)


def test_mongo_document_roundtrip() -> None:
    now = datetime.now(tz=timezone.utc)
    record = BundleRecord(
        id="abc",
        key="abc",
        status=BundleState.COMPLETE,
        created_at=now,
        updated_at=now,
        folder_name="folder",
        compression="zip",
        urls=["https://example.com/a"],
        archive_path="/tmp/a.zip",
        archive_size_bytes=12,
        content_type="application/zip",
        retry_count=1,
        failure_kind=None,
        last_build_strategy="sequential",
        last_build_timings=ArchiveBuildTimings(
            download_seconds=1.0,
            zip_seconds=0.5,
            total_seconds=1.5,
            url_count=1,
        ),
    )
    restored = _doc_to_record(_record_to_doc(record))
    assert restored.id == record.id
    assert restored.status == BundleState.COMPLETE
    assert restored.last_build_strategy == "sequential"
    assert restored.last_build_timings is not None
    assert restored.last_build_timings.total_seconds == 1.5
    assert restored.failure_kind is None

    failed = BundleRecord(
        id="f",
        key="f",
        status=BundleState.FAILED,
        created_at=now,
        updated_at=now,
        folder_name="",
        compression="zip",
        urls=["https://example.com/b"],
        failure_kind=FailureKind.TRANSIENT,
        error_message="boom",
    )
    restored_failed = _doc_to_record(_record_to_doc(failed))
    assert restored_failed.failure_kind == FailureKind.TRANSIENT


def test_memory_store_save_get_and_counts() -> None:
    store = InMemoryJobStore()
    now = datetime.now(tz=timezone.utc)
    record = BundleRecord(
        id="k1",
        key="k1",
        status=BundleState.PENDING,
        created_at=now,
        updated_at=now,
        folder_name="f",
        compression="zip",
        urls=["https://example.com/x"],
    )
    store.save(record)
    assert store.get("k1") is record
    assert store.get_by_key("k1") is record
    assert store.count_by_status()["pending"] == 1
    store.clear()
    assert store.get("k1") is None
