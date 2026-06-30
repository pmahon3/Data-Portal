"""Integration tests for bundle retry policy after ``failed`` jobs.

Boundary: create/re-enqueue retry semantics and retry metadata (``retry_count``,
fresh presigned URLs, max retries). Exception-to-policy mapping lives in
``tests/test_failure_classification.py``; idempotent ``complete`` duplicates
live in ``tests/test_bundles.py``.

Rule of thumb: if the question is "what happens when a failed job is
re-submitted?", this suite is the right place.

Each test follows Arrange / Act / Assert / Cleanup (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__).

- ``test_create_bundle_retries_when_failed_and_transient``: ``failed`` + transient build failure accepts re-create, reuses bundle id, and eventually reaches ``complete``.
- ``test_create_bundle_rejects_retry_when_failed_and_permanent``: ``failed`` + permanent failure (404) keeps duplicate rejection via ``KeyError`` (no retry).
- ``test_create_bundle_retries_with_fresh_presigned_urls``: accepted retry replaces stored URLs with incoming presigned values (fingerprint ignores signing params).
- ``test_create_bundle_increments_retry_count_on_retry``: each accepted retry from ``failed`` increments ``retry_count`` on the bundle record.
- ``test_create_bundle_rejects_retry_when_max_retries_exceeded``: after ``MAX_BUNDLE_RETRIES`` accepted retries, further re-create raises ``KeyError``.

"""

from __future__ import annotations

import httpx
import pytest

import bundler_core as api
from bundler_core import bundles as bundles_impl
from bundler_core.bundles import BundleService

from .common import reset_bundle_test_state, wait_for_bundle_terminal_status

from bundler_core.failures import MAX_BUNDLE_RETRIES


def _http_status_error(status_code: int, url: str = "https://example.com/bucket/object.txt") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"http {status_code}",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


def _retry_payload(
    *,
    folder_name: str,
    url: str,
) -> api.CreateBundleRequest:
    return api.CreateBundleRequest(
        folder_name=folder_name,
        compression="zip",
        urls=[url],
    )


def test_create_bundle_retries_when_failed_and_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``failed`` + transient failure should accept re-create and eventually complete."""
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    build_calls = 0
    original_build = BundleService._build_bundle_archive

    async def _fail_once_with_timeout(self: BundleService, record):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            raise httpx.TimeoutException("simulated transient network timeout")
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _fail_once_with_timeout)
    payload = _retry_payload(
        folder_name="retry-transient",
        url="__bundler_stub__",
    )

    try:
        first = api.create_bundle_job(payload)
        assert wait_for_bundle_terminal_status(first["id"], timeout_seconds=3.0) == "failed"

        second = api.create_bundle_job(payload)
        terminal = wait_for_bundle_terminal_status(second["id"], timeout_seconds=4.0)

        assert second["id"] == first["id"]
        assert terminal == "complete"
    finally:
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


def test_create_bundle_rejects_retry_when_failed_and_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``failed`` + permanent failure should keep duplicate rejection (no retry)."""
    reset_bundle_test_state()

    async def _always_not_found(self: BundleService, record):
        raise _http_status_error(404)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _always_not_found)
    payload = _retry_payload(
        folder_name="retry-permanent",
        url="https://example.com/bucket/missing.txt",
    )
    first = api.create_bundle_job(payload)
    assert wait_for_bundle_terminal_status(first["id"], timeout_seconds=3.0) == "failed"

    duplicate_raised = False
    try:
        api.create_bundle_job(payload)
    except KeyError:
        duplicate_raised = True

    assert duplicate_raised is True
    reset_bundle_test_state()


def test_create_bundle_retries_with_fresh_presigned_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry must use incoming URL values (fresh presign), not stale stored URLs."""
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    build_calls = 0
    original_build = BundleService._build_bundle_archive

    async def _fail_once_with_timeout(self: BundleService, record):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            raise httpx.TimeoutException("simulated transient network timeout")
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _fail_once_with_timeout)

    url_first = "https://example.com/bucket/object.txt?X-Amz-Signature=first"
    url_second = "https://example.com/bucket/object.txt?X-Amz-Signature=second"
    payload_first = _retry_payload(folder_name="retry-fresh-urls", url=url_first)
    payload_second = _retry_payload(folder_name="retry-fresh-urls", url=url_second)

    try:
        first = api.create_bundle_job(payload_first)
        bundle_id = first["id"]
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

        api.create_bundle_job(payload_second)
        with api._STATE_LOCK:
            record = api._BUNDLE_BY_ID[bundle_id]

        assert record.urls == [url_second]
    finally:
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


def test_create_bundle_increments_retry_count_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each accepted retry from ``failed`` increments ``retry_count``."""
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    build_calls = 0
    original_build = BundleService._build_bundle_archive

    async def _fail_once_with_timeout(self: BundleService, record):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            raise httpx.TimeoutException("simulated transient network timeout")
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _fail_once_with_timeout)
    payload = _retry_payload(
        folder_name="retry-count",
        url="__bundler_stub__",
    )

    try:
        first = api.create_bundle_job(payload)
        bundle_id = first["id"]
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

        with api._STATE_LOCK:
            assert api._BUNDLE_BY_ID[bundle_id].retry_count == 0

        api.create_bundle_job(payload)
        wait_for_bundle_terminal_status(bundle_id, timeout_seconds=4.0)

        with api._STATE_LOCK:
            assert api._BUNDLE_BY_ID[bundle_id].retry_count == 1
    finally:
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


def test_create_bundle_rejects_retry_when_max_retries_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After ``MAX_BUNDLE_RETRIES`` accepted retries, further re-create is rejected."""
    reset_bundle_test_state()

    async def _always_timeout(self: BundleService, record):
        raise httpx.TimeoutException("simulated transient network timeout")

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _always_timeout)
    payload = _retry_payload(
        folder_name="retry-max",
        url="https://example.com/bucket/object.txt",
    )

    create_response = api.create_bundle_job(payload)
    bundle_id = create_response["id"]
    assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

    for _ in range(MAX_BUNDLE_RETRIES):
        api.create_bundle_job(payload)
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

    duplicate_raised = False
    try:
        api.create_bundle_job(payload)
    except KeyError:
        duplicate_raised = True

    assert duplicate_raised is True
    with api._STATE_LOCK:
        assert api._BUNDLE_BY_ID[bundle_id].retry_count == MAX_BUNDLE_RETRIES

    reset_bundle_test_state()
