"""State transition tests for bundle worker lifecycle.

Boundary: this module owns lifecycle/state-machine assertions (for example pending->processing visibility and state-gated download behavior), 
while API-level response semantics remain in ``tests/test_bundles.py`` and archive structure/content assertions remain in ``tests/test_bundle_zip_paths.py``.

- ``test_pending_to_processing_is_observable_during_slow_build``: patches archive build with a short async pause so status can be asserted as ``processing`` before terminal completion.
- ``test_processing_to_failed_when_archive_build_raises``: forces archive-build failure and asserts terminal status becomes ``failed``.
- ``test_transition_sequence_pending_processing_complete_is_recorded``: records transition calls and asserts ``pending->processing->complete`` ordering.
- ``test_download_bundle_not_ready_raises_runtime_error``: forced pending state blocks archive download with a not-ready runtime error.
- ``test_transition_from_complete_is_rejected``: illegal transition out of terminal ``complete`` state raises ``RuntimeError``.
- ``test_transition_from_failed_is_rejected``: illegal transition out of terminal ``failed`` state raises ``RuntimeError``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Event

import anyio
import pytest

import bundler_core as api
from bundler_core import bundles as bundles_impl
from bundler_core import state_ops as state_ops_impl
from bundler_core.bundles import BundleService
from bundler_core.models import BundleRecord, BundleState
from bundler_core.state_ops import _transition_state
from .common import reset_bundle_test_state, wait_for_bundle_terminal_status


def test_pending_to_processing_is_observable_during_slow_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    entered_build = Event()
    original_build = BundleService._build_bundle_archive

    async def _slow_build_bundle_archive(self: BundleService, record):
        # `_process_bundle_job()` transitions pending->processing before calling build.
        entered_build.set()
        await anyio.sleep(0.5)
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _slow_build_bundle_archive)
    request = api.CreateBundleRequest(
        folder_name="processing-window",
        compression="zip",
        urls=["__bundler_stub__"],
    )

    try:
        # Act
        created = api.create_bundle_job(request)
        bundle_id = created["id"]
        assert entered_build.wait(timeout=2.0) is True
        mid_status = api.get_bundle_status(bundle_id)["status"]
        terminal_status = wait_for_bundle_terminal_status(bundle_id, timeout_seconds=4.0)

        # Assert
        assert mid_status == "processing"
        assert terminal_status == "complete"
    finally:
        # Cleanup
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


def test_processing_to_failed_when_archive_build_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force archive-build failure and assert terminal status becomes ``failed``."""
    # Arrange
    reset_bundle_test_state()
    raised = RuntimeError("forced build failure")

    async def _raise_in_build(self: BundleService, record: BundleRecord):
        raise raised

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _raise_in_build)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="processing-fail",
            compression="zip",
            urls=["https://example.com/source.txt"],
        )
    )

    # Act
    terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=3.0)
    status = api.get_bundle_status(created["id"])

    # Assert
    assert terminal == "failed"
    assert status["status"] == "failed"

    # Cleanup
    reset_bundle_test_state()


def test_transition_sequence_pending_processing_complete_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record transition calls and assert ``pending->processing->complete`` ordering."""
    # Arrange
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    observed: list[tuple[str, str]] = []
    original_bundles_transition = bundles_impl._transition_state
    original_state_ops_transition = state_ops_impl._transition_state

    def _make_recording_transition(original_fn):
        def _record_transition(
            record: BundleRecord, new_state: BundleState, *, error_message: str | None = None
        ) -> None:
            old = record.status.value if isinstance(record.status, BundleState) else str(record.status)
            new = new_state.value if isinstance(new_state, BundleState) else str(new_state)
            observed.append((old, new))
            original_fn(record, new_state, error_message=error_message)

        return _record_transition

    monkeypatch.setattr(bundles_impl, "_transition_state", _make_recording_transition(original_bundles_transition))
    monkeypatch.setattr(state_ops_impl, "_transition_state", _make_recording_transition(original_state_ops_transition))
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="sequence",
            compression="zip",
            urls=["__bundler_stub__"],
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)

        # Assert
        assert terminal == "complete"
        assert ("pending", "processing") in observed
        assert ("processing", "complete") in observed
        assert observed.index(("pending", "processing")) < observed.index(("processing", "complete"))
    finally:
        # Cleanup
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


def test_download_bundle_not_ready_raises_runtime_error() -> None:
    # Arrange
    reset_bundle_test_state()
    create_response = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="pending",
            compression="zip",
            urls=["https://example.com/source.txt"],
        )
    )
    bundle_id = create_response["id"]
    with api._STATE_LOCK:
        api._BUNDLE_BY_ID[bundle_id].status = api.BundleState.PENDING
        api._BUNDLE_BY_ID[bundle_id].archive_path = None

    # Act
    raised = False
    try:
        api.download_bundle_archive(bundle_id)
    except RuntimeError as exc:
        raised = "not ready" in str(exc).lower()

    # Assert
    assert raised is True

    # Cleanup
    reset_bundle_test_state()


def test_transition_from_complete_is_rejected() -> None:
    """Verify illegal transition out of ``complete`` raises ``RuntimeError``."""
    # Arrange
    now = datetime.now(tz=timezone.utc)
    record = BundleRecord(
        id="done",
        key="done",
        status=api.BundleState.COMPLETE,
        created_at=now,
        updated_at=now,
        folder_name="",
        compression="zip",
        urls=[],
    )

    # Act / Assert
    with pytest.raises(RuntimeError):
        _transition_state(record, api.BundleState.PROCESSING)


def test_transition_from_failed_is_rejected() -> None:
    """Verify illegal transition out of ``failed`` raises ``RuntimeError``."""
    # Arrange
    now = datetime.now(tz=timezone.utc)
    record = BundleRecord(
        id="failed",
        key="failed",
        status=api.BundleState.FAILED,
        created_at=now,
        updated_at=now,
        folder_name="",
        compression="zip",
        urls=[],
    )

    # Act / Assert
    with pytest.raises(RuntimeError):
        _transition_state(record, api.BundleState.PROCESSING)

