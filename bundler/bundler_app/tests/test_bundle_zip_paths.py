"""Core bundle tests: zip layout for object-store-style hierarchical URLs.

Boundary: this module focuses on archive structure and file-content mapping from input URLs, 
while API behavior belongs in ``tests/test_bundles.py`` and lifecycle transition/state-machine behavior belongs in ``tests/test_state_transitions.py``.

These tests live in ``bundler_app`` (domain logic), not in the generated HTTP
contract suite. Network is avoided by monkeypatching ``BundleService._download_url_to_file``.

Expected contract: hierarchical URL paths are preserved in ZIP member names so
nested object-store keys are recreated as nested paths in the archive. The root
of archived paths is URL-derived: the first URL path segment (for example the
bucket name) is kept as the top-level prefix.

Each test follows Arrange / Act / Assert / Cleanup (`pytest anatomy
<https://docs.pytest.org/en/stable/explanation/anatomy.html>`__).

- ``test_zip_preserves_hierarchical_paths_for_object_urls``: hierarchical object URLs are bundled with nested ZIP entries and expected per-file payload bytes.
- ``test_hierarchical_paths_prevent_same_basename_collision``: same basename under different nested paths remains distinct archive entries.
- ``test_zip_preserves_url_encoded_path_segments``: URL-encoded path segments should remain represented as path segments under URL-derived root prefix.
- ``test_trailing_slash_empty_folder_adds_no_entries``: trailing-slash URL is treated as an empty folder marker and contributes no explicit ZIP member.
- ``test_trailing_slash_is_ignored_when_other_files_exist``: trailing-slash URL adds no entry while regular object URLs are still archived normally.
- ``test_pathless_url_is_ignored_when_other_files_exist``: URL with no path segments contributes no ZIP member while regular object URLs are still archived.
- ``test_all_pathless_urls_produce_empty_zip``: when every URL is pathless, bundle completes and ZIP contains no members.
- ``test_duplicate_exact_url_preserves_two_entries``: duplicate exact URL input keeps two archive entries at the same expected path.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import anyio
import pytest

from app import api
from app.bundles import BundleService

from tests.common import reset_bundle_test_state, wait_for_bundle_terminal_status


@pytest.fixture
def fake_hierarchical_downloads(monkeypatch: pytest.MonkeyPatch):
    """Write deterministic bytes per URL; no real HTTP to MinIO."""

    async def _download_url_to_file(
        self: BundleService,
        client: object,
        semaphore: object,
        url: str,
        target: Path,
    ) -> None:
        payload = _URL_TO_BYTES.get(url)
        if payload is None:
            raise RuntimeError(f"unexpected URL in test fake: {url}")
        async with await anyio.open_file(target, "wb") as out_f:
            await out_f.write(payload)

    monkeypatch.setattr(BundleService, "_download_url_to_file", _download_url_to_file)


def _patch_downloads_from_map(
    monkeypatch: pytest.MonkeyPatch,
    url_to_bytes: dict[str, bytes],
) -> None:
    """Patch BundleService downloader to write deterministic bytes per URL."""

    async def _download_url_to_file(
        self: BundleService,
        client: object,
        semaphore: object,
        url: str,
        target: Path,
    ) -> None:
        payload = url_to_bytes[url]
        async with await anyio.open_file(target, "wb") as out_f:
            await out_f.write(payload)

    monkeypatch.setattr(BundleService, "_download_url_to_file", _download_url_to_file)


_URL_TO_BYTES = {
    "http://127.0.0.1:9000/test-bucket/test-a.txt?X-Amz-Signature=abc": b"alpha-bytes\n",
    "http://127.0.0.1:9000/test-bucket/timelog/samples/timelog-Aug-800.pdf?X-Amz-Signature=abc": b"%PDF-fake-payload",
}

def test_zip_preserves_hierarchical_paths_for_object_urls(
    fake_hierarchical_downloads: None,
) -> None:
    """Object URLs with nested paths should keep hierarchical archive names."""
    # Arrange
    reset_bundle_test_state()
    request = api.CreateBundleRequest(
        folder_name="my-export",
        compression="zip",
        urls=list(_URL_TO_BYTES.keys()),
    )

    try:
        # Act
        create = api.create_bundle_job(request)
        bundle_id = create["id"]
        terminal_status = wait_for_bundle_terminal_status(bundle_id)
        raw = api.download_bundle_archive(bundle_id)

        # Assert
        assert terminal_status == "complete"
        assert raw.startswith(b"PK\x03\x04") # ZIP file magic
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
        # Expected behavior: preserve nested key path segments in the archive.
        assert names == {
            "test-bucket/test-a.txt",
            "test-bucket/timelog/samples/timelog-Aug-800.pdf",
        }
        first_url, second_url = tuple(_URL_TO_BYTES.keys())
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.read("test-bucket/test-a.txt") == _URL_TO_BYTES[first_url]
            assert zf.read("test-bucket/timelog/samples/timelog-Aug-800.pdf") == _URL_TO_BYTES[second_url]
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_hierarchical_paths_prevent_same_basename_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec test: same basename under different paths should remain distinct in ZIP."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000/test-bucket/a/x/report.pdf?X-Amz-Signature=abc": b"a-report",
        "http://127.0.0.1:9000/test-bucket/b/y/report.pdf?X-Amz-Signature=abc": b"b-report",
    }

    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="collision",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            assert names == {
                "test-bucket/a/x/report.pdf",
                "test-bucket/b/y/report.pdf",
            }
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_zip_preserves_url_encoded_path_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL-encoded segments should map to nested path segments under URL-derived root."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000/test-bucket/a%20space/report%20v1.txt?X-Amz-Signature=abc": b"encoded",
    }
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            assert names == {"test-bucket/a space/report v1.txt"}
            assert zf.read("test-bucket/a space/report v1.txt") == b"encoded"
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_trailing_slash_empty_folder_adds_no_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec test: trailing-slash URL should not create fallback file or explicit directory entry."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000/test-bucket/folder/subfolder/?X-Amz-Signature=abc": b"dir-like-object",
    }
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            # Empty folder markers should not create explicit entries in this ZIP contract.
            assert names == []
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_trailing_slash_is_ignored_when_other_files_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trailing slash marker should be ignored when mixed with normal file URLs."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000/test-bucket/folder/subfolder/?X-Amz-Signature=abc": b"ignored-dir-marker",
        "http://127.0.0.1:9000/test-bucket/real/file.txt?X-Amz-Signature=abc": b"real-file",
    }
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            assert names == ["test-bucket/real/file.txt"]
            assert zf.read("test-bucket/real/file.txt") == b"real-file"
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_pathless_url_is_ignored_when_other_files_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec test: pathless URL should be ignored when mixed with normal file URLs."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000?X-Amz-Signature=abc": b"ignore-pathless",
        "http://127.0.0.1:9000/test-bucket/real/file.txt?X-Amz-Signature=abc": b"real-file",
    }
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            assert names == ["test-bucket/real/file.txt"]
            assert zf.read("test-bucket/real/file.txt") == b"real-file"
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_all_pathless_urls_produce_empty_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    """All-pathless URL requests should complete with an empty ZIP archive."""
    # Arrange
    reset_bundle_test_state()
    urls_to_bytes = {
        "http://127.0.0.1:9000?X-Amz-Signature=a": b"ignored-a",
        "http://127.0.0.1:9000?X-Amz-Signature=b": b"ignored-b",
    }
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=list(urls_to_bytes.keys()),
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.namelist() == []
    finally:
        # Cleanup
        reset_bundle_test_state()


def test_duplicate_exact_url_preserves_two_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Duplicate exact URL input should keep two entries at the same target path."""
    # Arrange
    reset_bundle_test_state()
    duplicate_url = "http://127.0.0.1:9000/test-bucket/dup/same.txt?X-Amz-Signature=abc"
    urls_to_bytes = {duplicate_url: b"same"}
    _patch_downloads_from_map(monkeypatch, urls_to_bytes)
    created = api.create_bundle_job(
        api.CreateBundleRequest(
            folder_name="ignored-by-url-root-policy",
            compression="zip",
            urls=[duplicate_url, duplicate_url],
        )
    )

    try:
        # Act
        terminal = wait_for_bundle_terminal_status(created["id"], timeout_seconds=4.0)
        raw = api.download_bundle_archive(created["id"])

        # Assert
        assert terminal == "complete"
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            assert names.count("test-bucket/dup/same.txt") == 2
    finally:
        # Cleanup
        reset_bundle_test_state()
