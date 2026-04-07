from __future__ import annotations

from time import sleep

from app import api
from app import bundles as bundles_impl


def _reset_state() -> None:
    bundles_impl._reset_runtime_state_for_tests()


def _wait_for_terminal_status(bundle_id: str, timeout_seconds: float = 3.0) -> str:
    deadline = timeout_seconds
    elapsed = 0.0
    while elapsed < deadline:
        status = api.get_bundle_status(bundle_id)["status"]
        if status in {"complete", "failed"}:
            return status
        sleep(0.05)
        elapsed += 0.05
    return api.get_bundle_status(bundle_id)["status"]


def test_create_bundle_deduplicates_equivalent_requests() -> None:
    # Arrange
    _reset_state()

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
    _reset_state()


def test_get_bundle_status_and_not_found() -> None:
    # Arrange
    _reset_state()
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
    _reset_state()


def test_download_bundle_returns_zip() -> None:
    # Arrange
    _reset_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    create_response = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="download",
            compression="zip",
            urls=["__bundler_stub__"],
        )
    )
    bundle_id = create_response["id"]

    terminal_status = _wait_for_terminal_status(bundle_id)

    # Act
    zip_bytes = api.download_bundle_archive(bundle_id)
    status_response = api.get_bundle_status(bundle_id)

    # Assert
    assert terminal_status == "complete"
    assert isinstance(zip_bytes, (bytes, bytearray))
    assert zip_bytes.startswith(b"PK\x03\x04")
    assert status_response["status"] == "complete"

    # Cleanup
    bundles_impl._TEST_STUB_MODE_ENABLED = False
    _reset_state()


def test_download_bundle_not_ready_raises_runtime_error() -> None:
    _reset_state()
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

    raised = False
    try:
        api.download_bundle_archive(bundle_id)
    except RuntimeError as exc:
        raised = "not ready" in str(exc).lower()

    assert raised is True
    _reset_state()
