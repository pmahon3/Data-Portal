from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models import BundleRecord, BundleState, can_transition


def _transition_state(
    record: BundleRecord,
    new_state: BundleState,
    *,
    error_message: str | None = None,
) -> None:
    if not can_transition(record.status, new_state):
        raise RuntimeError(f"Illegal state transition: {record.status} -> {new_state}")
    record.status = new_state
    if error_message is not None:
        record.error_message = error_message
    record.updated_at = datetime.now(tz=timezone.utc)


def _finalize_complete(record: BundleRecord, archive_path: Path) -> None:
    record.archive_path = str(archive_path)
    record.archive_size_bytes = archive_path.stat().st_size
    record.content_type = "application/zip"
    record.result_url = None
    _transition_state(record, BundleState.COMPLETE)


def _mark_failed(record: BundleRecord, exc: Exception) -> None:
    if record.status in {BundleState.COMPLETE, BundleState.FAILED}:
        return
    _transition_state(record, BundleState.FAILED, error_message=str(exc))
