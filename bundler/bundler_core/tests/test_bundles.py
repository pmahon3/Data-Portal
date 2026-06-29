"""Unit tests for bundle domain API (``bundler_core`` / ``bundler_core.bundles``).

Boundary: this module verifies public bundle domain API behavior (create/get/download responses, dedupe, and not-found handling), 
while explicit lifecycle transition semantics live in ``tests/test_state_transitions.py`` and archive-path/content rules live in ``tests/test_bundle_zip_paths.py``.

Rule of thumb: if the question is "does bundling logic do the right thing?",
this suite (and sibling ``bundler_core/tests`` modules) is the right place.

Each test follows Arrange / Act / Assert / Cleanup (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__).

- ``test_create_bundle_deduplicates_equivalent_requests``: equivalent normalized requests yield first ``pending`` acceptance and second duplicate ``KeyError``.
- ``test_duplicate_request_rejected_while_first_request_is_processing``: duplicate submission is rejected even when the first equivalent request is already ``processing``.
- ``test_get_bundle_status_and_not_found``: known bundle id returns status payload while unknown id raises ``KeyError``.
- ``test_download_bundle_returns_zip``: completed stub-backed bundle download returns valid ZIP bytes (including empty-archive case) and keeps status ``complete``.

"""

from __future__ import annotations

import io
import zipfile
from threading import Event

import anyio
import pytest

import bundler_core as api
from bundler_core import bundles as bundles_impl
from bundler_core.bundles import BundleService

from .common import reset_bundle_test_state, wait_for_bundle_terminal_status


def test_create_bundle_deduplicates_equivalent_requests() -> None:
    # Arrange
    reset_bundle_test_state()

    payload_one = api.CreateBundleRequest(
        folder_name="alpha-folder",
        compression="zip",
        urls=[
            "https://example.com/b.txt?b=2&a=1&X-Amz-Date=123",
            "https://example.com/a.txt?z=9&X-Amz-Signature=abc",
        ],
    )
    payload_two = api.CreateBundleRequest(
        folder_name="alpha-folder",
        compression="zip",
        urls=[
            "https://example.com/a.txt?z=9&X-Amz-Signature=DIFFERENT",
            "https://example.com/b.txt?a=1&b=2&X-Amz-Date=DIFFERENT",
        ],
    )

    # Act
    response_one = api.create_bundle_job(payload_one)
    duplicate_error_raised = False
    try:
        api.create_bundle_job(payload_two)
    except KeyError:
        duplicate_error_raised = True

    # Assert
    assert response_one["status"] == "pending"
    assert duplicate_error_raised is True

    # Cleanup
    reset_bundle_test_state()


def test_get_bundle_status_and_not_found() -> None:
    # Arrange
    reset_bundle_test_state()
    create_response = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="status-check",
            compression="zip",
            urls=["https://example.com/file.txt"],
        )
    )
    bundle_id = create_response["id"]

    # Act
    status_response = api.get_bundle_status(bundle_id)
    missing_error_raised = False

    try:
        api.get_bundle_status("does-not-exist")
    except KeyError:
        missing_error_raised = True

    # Assert
    assert status_response["id"] == bundle_id
    # Worker may move the job to processing before this read (async race).
    assert status_response["status"] in ("pending", "processing")
    assert missing_error_raised is True

    # Cleanup
    reset_bundle_test_state()


def test_duplicate_request_rejected_while_first_request_is_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure duplicate submission is rejected even while first job is processing."""
    # Arrange
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    entered_build = Event()
    original_build = BundleService._build_bundle_archive

    async def _slow_build_bundle_archive(self: BundleService, record):
        entered_build.set()
        await anyio.sleep(0.5)
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _slow_build_bundle_archive)
    payload = api.CreateBundleRequest(
        folder_name="duplicate-while-processing",
        compression="zip",
        urls=["__bundler_stub__"],
    )
    first = api.create_bundle_job(payload)
    assert entered_build.wait(timeout=2.0) is True
    assert api.get_bundle_status(first["id"])["status"] == "processing"

    # Act
    duplicate_raised = False
    try:
        api.create_bundle_job(payload)
    except KeyError:
        duplicate_raised = True

    # Assert
    assert duplicate_raised is True

    # Cleanup
    bundles_impl._TEST_STUB_MODE_ENABLED = False
    reset_bundle_test_state()


def test_download_bundle_returns_zip() -> None:
    # Arrange
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    create_response = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="download",
            compression="zip",
            urls=["__bundler_stub__"],
        )
    )
    bundle_id = create_response["id"]
    terminal_status = wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0)

    # Act
    zip_bytes = api.download_bundle_archive(bundle_id)
    status_response = api.get_bundle_status(bundle_id)

    # Assert
    assert terminal_status == "complete"
    assert isinstance(zip_bytes, (bytes, bytearray))
    # Empty ZIP archives can begin with EOCD (PK\x05\x06) instead of local header (PK\x03\x04).
    assert zip_bytes.startswith(b"PK\x03\x04") or zip_bytes.startswith(b"PK\x05\x06") # ZIP file magic
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert zf.testzip() is None
    assert status_response["status"] == "complete"

    # Cleanup
    bundles_impl._TEST_STUB_MODE_ENABLED = False
    reset_bundle_test_state()
