# coding: utf-8
"""Contract tests for bundle endpoints under ``/v1/...``.

| Endpoint | Request Type | Description / Status |
| --- | --- | --- |
| ``/v1/bundles`` | POST | malformed-json / 400-422 |
| ``/v1/bundles`` | POST | schema-invalid / 422 |
| ``/v1/bundles`` | POST | too-large / 413 |
| ``/v1/bundles`` | POST | accepted / 202 |
| ``/v1/bundles/{bundleId}`` | GET | found / 202 |
| ``/v1/bundles/{bundleId}`` | GET | not found / 404 |
| ``/v1/bundles/{bundleId}/download`` | GET | return a file / 200 |
| ``/v1/bundles/{bundleId}/download`` | GET | not found / 404 |
| ``/v1/bundles/{bundleId}/download`` | GET | not ready / 202 |
| ``<any endpoint>`` | <any> | unexpected error / return an error / 500 |

Failures use :func:`assert_status` so the response body and actual status code
appear in assertion messages.

Seeding runs once when ``tests.common`` is imported (``tests/seed_demo_bundles.py``).
Payloads pass ``api_prefix=_API_PREFIX`` into :mod:`tests.common` helpers so ``folderName`` keys stay distinct from ``test_v2.py``.

Each test follows Arrange / Act / Assert / Cleanup (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__); cleanup is omitted when there is nothing to tear down.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.common import (
    DOWNLOAD_HEADERS,
    GET_HEADERS,
    JSON_HEADERS,
    STUB_FORCE_500_URL,
    assert_status,
    duplicate_create_json,
    oversized_urls_payload,
    schema_malformed_create_json_missing_urls,
    valid_create_json,
)

_API_PREFIX = "/v1"

# POST ``{_API_PREFIX}/bundles``
_path_post_bundles = lambda: f"{_API_PREFIX}/bundles"
# GET ``{_API_PREFIX}/bundles/{bundle_id}``
_path_get_bundle = lambda bundle_id: f"{_API_PREFIX}/bundles/{bundle_id}"
# GET ``{_API_PREFIX}/bundles/{bundle_id}/download``
_path_get_bundle_download = lambda bundle_id: f"{_API_PREFIX}/bundles/{bundle_id}/download"


def test_post_bundles_returns_400_when_request_is_malformed(client: TestClient):
    """Malformed JSON is rejected before the handler (typically 400 or 422)."""
    # Arrange
    url = _path_post_bundles()
    invalid_body = b"{not-json"
    # Act
    response = client.post(url, content=invalid_body, headers=JSON_HEADERS)
    # Assert
    assert response.status_code in (400, 422), (
        f"expected 400 or 422 for invalid JSON, got {response.status_code} "
        f"(body: {response.text[:800]!r})"
    )
    # Cleanup — none


def test_post_bundles_returns_422_when_schema_malformed(client: TestClient):
    # Arrange
    url = _path_post_bundles()
    body = schema_malformed_create_json_missing_urls()
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 422)
    # Cleanup — none


def test_post_bundles_returns_413_when_request_is_too_large(client: TestClient):
    # Arrange
    url = _path_post_bundles()
    body = oversized_urls_payload(api_prefix=_API_PREFIX)
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 413)
    # Cleanup — none


def test_post_bundles_returns_202_when_request_is_accepted(client: TestClient):
    # Arrange
    url = _path_post_bundles()
    body = valid_create_json(api_prefix=_API_PREFIX)
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


def test_get_bundle_returns_202_when_found(client: TestClient):
    # Arrange
    url = _path_get_bundle("found-bundle-id")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


def test_get_bundle_returns_404_when_not_found(client: TestClient):
    # Arrange
    url = _path_get_bundle("missing-bundle")
    # Act
    response = client.get(url, headers=GET_HEADERS)
    # Assert
    assert_status(response, 404)
    # Cleanup — none


def test_get_bundle_download_returns_200_when_ready(client: TestClient):
    # Arrange
    url = _path_get_bundle_download("ready-id")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 200)
    assert response.content.startswith(b"PK\x03\x04")
    # Cleanup — none


def test_get_bundle_download_returns_404_when_not_found(client: TestClient):
    # Arrange
    url = _path_get_bundle_download("missing-download")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 404)
    # Cleanup — none


def test_get_bundle_download_returns_202_when_not_ready(client: TestClient):
    # Arrange
    url = _path_get_bundle_download("not-ready")
    # Act
    response = client.get(url, headers=DOWNLOAD_HEADERS)
    # Assert
    assert_status(response, 202)
    # Cleanup — none


def test_post_bundles_returns_409_when_request_is_duplicate(client: TestClient):
    # Arrange
    url = _path_post_bundles()
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


def test_assert_status_surfaces_actual_code_when_status_unexpected(client: TestClient, monkeypatch):
    """If the server returns something other than the expected code, the failure shows it."""
    import openapi_server.impl.default_api_impl as impl

    # Arrange
    def _raise_generic(*args, **kwargs):
        raise Exception("forced generic failure")

    monkeypatch.setattr(impl, "bundler_create_bundle_job", _raise_generic)
    url = _path_post_bundles()
    body = valid_create_json(api_prefix=_API_PREFIX, urls=[STUB_FORCE_500_URL])
    # Act
    response = client.post(url, json=body, headers=JSON_HEADERS)
    # Assert
    with pytest.raises(AssertionError) as excinfo:
        assert_status(response, 202)
    assert "500" in str(excinfo.value)
    assert "202" in str(excinfo.value)
    # Cleanup — ``monkeypatch`` restores ``bundler_create_bundle_job`` after the test
