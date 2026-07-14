# coding: utf-8
"""Contract tests for ``/v2/...`` and unversioned paths (current API).

Same URL shapes as :mod:`tests.test_v1`, but path helpers live at module scope and take
``api_prefix`` as the first argument (``_API_PREFIX`` is injected by ``@_V2_AND_CURRENT``:
``"/v2"`` vs ``""`` for unversioned ``/bundles``). Each test calls only the helper it needs,
e.g. ``_path_post_bundles(_API_PREFIX)``.

Payload builders in :mod:`tests.common` accept ``api_prefix=`` so ``folderName`` / ``variant``
stay distinct per route family without extra logic here.

Each test follows Arrange / Act / Assert / Cleanup (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__); cleanup is omitted when there is nothing to tear down.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bundler_core import bundles as bundles_impl
from bundler_core.tests.common import reset_bundle_test_state, wait_for_bundle_terminal_status

from tests.common import (
    DOWNLOAD_HEADERS,
    GET_HEADERS,
    JSON_HEADERS,
    STUB_FORCE_500_URL,
    assert_status,
    complete_duplicate_create_json,
    duplicate_create_json,
    oversized_urls_payload,
    permanent_retry_create_json,
    schema_malformed_create_json_missing_urls,
    transient_retry_create_json,
    valid_create_json,
)

_V2_AND_CURRENT = pytest.mark.parametrize(
    "_API_PREFIX",
    ["/v2", ""],
    ids=["v2", "latest"],
)

# POST ``{api_prefix}/bundles`` — pass parametrized ``_API_PREFIX`` (same strings as :mod:`tests.test_v1`).
_path_post_bundles = lambda api_prefix: f"{api_prefix}/bundles"
# GET ``{api_prefix}/bundles/{bundle_id}``
_path_get_bundle = lambda api_prefix, bundle_id: f"{api_prefix}/bundles/{bundle_id}"
# GET ``{api_prefix}/bundles/{bundle_id}/download``
_path_get_bundle_download = lambda api_prefix, bundle_id: f"{api_prefix}/bundles/{bundle_id}/download"


@_V2_AND_CURRENT
def test_post_bundles_returns_400_when_request_is_malformed(
    client: TestClient,
    _API_PREFIX: str,
):
    """Malformed JSON is rejected before the handler (typically 400 or 422)."""
    # Arrange
    url = _path_post_bundles(_API_PREFIX)
    invalid_body = b"{not-json"
    # Act
    response = client.post(url, content=invalid_body, headers=JSON_HEADERS)
    # Assert
    assert response.status_code in (400, 422), (
        f"expected 400 or 422 for invalid JSON, got {response.status_code} "
        f"(body: {response.text[:800]!r})"
    )
    # Cleanup — none


@_V2_AND_CURRENT
def test_post_bundles_returns_422_when_schema_malformed(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_post_bundles(_API_PREFIX)
    body = schema_malformed_create_json_missing_urls()
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 422)
    # Cleanup — none


@_V2_AND_CURRENT
def test_post_bundles_returns_413_when_request_is_too_large(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_post_bundles(_API_PREFIX)
    body = oversized_urls_payload(api_prefix=_API_PREFIX)
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 413)
    # Cleanup — none


@_V2_AND_CURRENT
def test_post_bundles_returns_202_when_request_is_accepted(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_post_bundles(_API_PREFIX)
    body = valid_create_json(api_prefix=_API_PREFIX)
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_returns_202_when_found(client: TestClient, _API_PREFIX: str):
    # Arrange
    url = _path_get_bundle(_API_PREFIX, "found-bundle-id")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_returns_404_when_not_found(client: TestClient, _API_PREFIX: str):
    # Arrange
    url = _path_get_bundle(_API_PREFIX, "missing-bundle")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 404)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_returns_422_when_bundle_id_contains_whitespace(
    client: TestClient,
    _API_PREFIX: str,
):
    """``BundleId`` pattern ``^\\S+$`` forbids any whitespace; a lone space is invalid (**422**)."""
    # Arrange
    url = _path_get_bundle(_API_PREFIX, " ")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 422)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_returns_422_when_bundle_id_has_leading_whitespace(
    client: TestClient,
    _API_PREFIX: str,
):
    """``BundleId`` is ``^\\S+$``; a leading space before non-space chars still fails (**422**)."""
    # Arrange
    url = _path_get_bundle(_API_PREFIX, " a")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 422)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_download_returns_200_when_ready(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_get_bundle_download(_API_PREFIX, "ready-id")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 200)
    assert response.content.startswith(b"PK\x03\x04")
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_download_returns_404_when_not_found(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_get_bundle_download(_API_PREFIX, "missing-download")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 404)
    # Cleanup — none


@_V2_AND_CURRENT
def test_get_bundle_download_returns_202_when_not_ready(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_get_bundle_download(_API_PREFIX, "not-ready")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


@_V2_AND_CURRENT
def test_post_bundles_returns_202_when_duplicate_and_first_is_complete(
    client: TestClient,
    _API_PREFIX: str,
):
    """Equivalent POST after the first job is ``complete`` must return 202 with the same bundle id."""
    # Arrange
    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    url = _path_post_bundles(_API_PREFIX)
    payload = complete_duplicate_create_json(api_prefix=_API_PREFIX)

    try:
        # Act — first submit
        response_one = client.post(url, json=payload, headers=JSON_HEADERS)
        assert_status(response_one, 202)
        bundle_id = response_one.json()["id"]
        terminal = wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0)
        # Act — equivalent re-submit after completion
        response_two = client.post(url, json=payload, headers=JSON_HEADERS)

        # Assert
        assert terminal == "complete"
        assert_status(response_two, 202)
        body_two = response_two.json()
        assert body_two["id"] == bundle_id
        assert body_two["status"] == "complete"
    finally:
        # Cleanup
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


@_V2_AND_CURRENT
def test_post_bundles_returns_202_when_retry_after_transient_failed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _API_PREFIX: str,
):
    """POST after transient ``failed`` should be accepted and eventually complete."""
    from bundler_core.bundles import BundleService

    reset_bundle_test_state()
    bundles_impl._TEST_STUB_MODE_ENABLED = True
    build_calls = 0
    original_build = BundleService._build_bundle_archive

    async def _fail_once_with_timeout(self: BundleService, record):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            import httpx

            raise httpx.TimeoutException("simulated transient network timeout")
        return await original_build(self, record)

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _fail_once_with_timeout)
    url = _path_post_bundles(_API_PREFIX)
    payload = transient_retry_create_json(api_prefix=_API_PREFIX)

    try:
        response_one = client.post(url, json=payload, headers=JSON_HEADERS)
        assert_status(response_one, 202)
        bundle_id = response_one.json()["id"]
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

        response_two = client.post(url, json=payload, headers=JSON_HEADERS)
        assert_status(response_two, 202)
        assert response_two.json()["id"] == bundle_id
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=4.0) == "complete"
    finally:
        bundles_impl._TEST_STUB_MODE_ENABLED = False
        reset_bundle_test_state()


@_V2_AND_CURRENT
def test_post_bundles_returns_409_when_retry_after_permanent_failed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _API_PREFIX: str,
):
    """POST after permanent ``failed`` should remain a duplicate conflict."""
    from bundler_core.bundles import BundleService

    reset_bundle_test_state()

    async def _always_not_found(self: BundleService, record):
        import httpx

        request = httpx.Request("GET", "https://example.com/bucket/missing-object.txt")
        raise httpx.HTTPStatusError(
            "not found",
            request=request,
            response=httpx.Response(404, request=request),
        )

    monkeypatch.setattr(BundleService, "_build_bundle_archive", _always_not_found)
    url = _path_post_bundles(_API_PREFIX)
    payload = permanent_retry_create_json(api_prefix=_API_PREFIX)

    try:
        response_one = client.post(url, json=payload, headers=JSON_HEADERS)
        assert_status(response_one, 202)
        bundle_id = response_one.json()["id"]
        assert wait_for_bundle_terminal_status(bundle_id, timeout_seconds=3.0) == "failed"

        response_two = client.post(url, json=payload, headers=JSON_HEADERS)
        assert_status(response_two, 409)
    finally:
        reset_bundle_test_state()


@_V2_AND_CURRENT
def test_post_bundles_returns_409_when_request_is_duplicate(
    client: TestClient,
    _API_PREFIX: str,
):
    # Arrange
    url = _path_post_bundles(_API_PREFIX)
    payload = duplicate_create_json(api_prefix=_API_PREFIX)
    # Act — first submit (accepted)
    response_one = client.post(url, json=payload, headers=JSON_HEADERS)
    # Assert
    assert_status(response_one, 202)
    # Act — duplicate submit
    response_two = client.post(url, json=payload, headers=JSON_HEADERS)
    # Assert
    assert_status(response_two, 409)
    # Cleanup — none


@_V2_AND_CURRENT
def test_assert_status_surfaces_actual_code_when_status_unexpected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _API_PREFIX: str,
):
    import bundler_server.core.default_api_impl as core

    # Arrange
    def _raise_generic(*args, **kwargs):
        raise Exception("forced generic failure")

    monkeypatch.setattr(core, "bundler_create_bundle_job", _raise_generic)
    url = _path_post_bundles(_API_PREFIX)
    body = valid_create_json(api_prefix=_API_PREFIX, urls=[STUB_FORCE_500_URL])
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    with pytest.raises(AssertionError) as excinfo:
        assert_status(response, 202)
    assert "500" in str(excinfo.value)
    assert "202" in str(excinfo.value)
    # Cleanup — ``monkeypatch`` restores ``bundler_create_bundle_job`` after the test
