from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bundler_core.models import BundleRecord, BundleState, can_transition


def _transition_state(
    record: BundleRecord,
    new_state: BundleState,
    *,
    error_message: str | None = None,
) -> None:
    """Apply a validated bundle state transition and refresh metadata.

    Raises ``RuntimeError`` when the requested transition is not allowed by the
    state machine rules declared in :mod:`bundler_core.models`.
    """
    if not can_transition(record.status, new_state):
        raise RuntimeError(f"Illegal state transition: {record.status} -> {new_state}")
    record.status = new_state
    if error_message is not None:
        record.error_message = error_message
    record.updated_at = datetime.now(tz=timezone.utc)


def _finalize_complete(record: BundleRecord, archive_path: Path) -> None:
    """Persist archive metadata on the record and transition it to ``COMPLETE``."""
    record.archive_path = str(archive_path)
    record.archive_size_bytes = archive_path.stat().st_size
    record.content_type = "application/zip"
    record.result_url = None
    _transition_state(record, BundleState.COMPLETE)


def _mark_failed(record: BundleRecord, exc: Exception) -> None:
    """Transition a non-terminal bundle into ``FAILED`` with the exception message."""
    if record.status in {BundleState.COMPLETE, BundleState.FAILED}:
        return
    _transition_state(record, BundleState.FAILED, error_message=str(exc))
