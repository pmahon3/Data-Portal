"""Shared helpers for bundle HTTP contract tests across API versions."""

from __future__ import annotations

import os

STUB_FORCE_500_URL = "https://example.com/presigned/force-500"
STUB_MAX_URL_COUNT = int(os.environ.get("STUB_MAX_URL_COUNT", 64))

JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}
GET_HEADERS = {"Accept": "application/json"}
DOWNLOAD_HEADERS = {"Accept": "application/zip"}


def _folder_tag_from_api_prefix(api_prefix: str | None) -> str:
    """Derive ``folderName`` segment from URL prefix, or ``\"default\"`` when ``api_prefix`` is omitted.

    ``None`` → ``\"default\"`` (generic contract payloads). ``\"/v1\"`` → ``\"v1\"``, ``\"\"`` → ``\"current\"``.
    """
    if api_prefix is None:
        return "default"
    return api_prefix.strip("/") or "current"


def assert_status(response, expected: int) -> None:
    """Assert HTTP status; on failure include the **received** code and response body."""
    assert response.status_code == expected, (
        f"expected HTTP {expected}, got {response.status_code} "
        f"(body: {response.text[:800]!r})"
    )


def valid_create_json(
    *,
    api_prefix: str | None = None,
    urls: list[str] | None = None,
) -> dict:
    """``api_prefix`` sets ``folderName`` (see :func:`_folder_tag_from_api_prefix`); optional ``urls`` overrides defaults."""
    v = _folder_tag_from_api_prefix(api_prefix)
    return {
        # Pathless default URL keeps contract tests network-independent because
        # bundler path-mapping ignores URLs without path segments.
        "urls": urls if urls is not None else ["https://example.com"],
        "folderName": f"out-{v}",
        "compression": "zip",
    }


def oversized_urls_payload(*, api_prefix: str | None = None) -> dict:
    v = _folder_tag_from_api_prefix(api_prefix)
    base = "https://example.com/presigned/"
    return {
        "urls": [f"{base}{i}" for i in range(STUB_MAX_URL_COUNT + 1)],
        "folderName": f"out-{v}",
        "compression": "zip",
    }


def schema_malformed_create_json_missing_urls() -> dict:
    return {
        "folderName": "out",
        "compression": "zip",
    }


def duplicate_create_json(*, api_prefix: str | None = None) -> dict:
    v = _folder_tag_from_api_prefix(api_prefix)
    return {
        "urls": ["https://example.com"],
        "folderName": f"out-duplicate-{v}",
        "compression": "zip",
    }


def complete_duplicate_create_json(*, api_prefix: str | None = None) -> dict:
    """Payload for idempotent re-submit tests once the first job reaches ``complete``."""
    v = _folder_tag_from_api_prefix(api_prefix)
    return {
        "urls": ["__bundler_stub__"],
        "folderName": f"out-complete-duplicate-{v}",
        "compression": "zip",
    }


def transient_retry_create_json(*, api_prefix: str | None = None) -> dict:
    """Payload for retry-after-transient-failure HTTP contract tests."""
    v = _folder_tag_from_api_prefix(api_prefix)
    return {
        "urls": ["__bundler_stub__"],
        "folderName": f"out-retry-transient-{v}",
        "compression": "zip",
    }


def permanent_retry_create_json(*, api_prefix: str | None = None) -> dict:
    """Payload for permanent-failure retry rejection HTTP contract tests."""
    v = _folder_tag_from_api_prefix(api_prefix)
    return {
        "urls": ["https://example.com/bucket/missing-object.txt"],
        "folderName": f"out-retry-permanent-{v}",
        "compression": "zip",
    }


def seed_contract_test_bundles() -> None:
    """Populate in-memory bundle state for HTTP contract tests (idempotent)."""
    from tests.seed_demo_bundles import seed_demo_bundles

    seed_demo_bundles()


# Imported by bundle contract modules (e.g. ``test_v1``, ``test_v2``, ``test_v10``).
seed_contract_test_bundles()
