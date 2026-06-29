from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import zipfile

from bundler_core import bundles as bundles_impl


def seed_demo_bundles() -> None:
    """
    Seed deterministic in-memory bundles used by the generated server contract tests.

    Kept inside `bundler_app_server_gen/tests/` so it cannot influence normal
    `bundler_core` imports.
    """

    now = datetime.now(tz=timezone.utc)
    with bundles_impl._STATE_LOCK:
        if bundles_impl._BUNDLE_BY_ID:
            return

        # Enable stubbed file content for the "__bundler_stub__" sentinel.
        bundles_impl._TEST_STUB_MODE_ENABLED = True

        def _build_ready_archive(bundle_id: str) -> Path:
            with tempfile.NamedTemporaryFile(prefix=f"seed-{bundle_id}-", suffix=".zip", delete=False) as tmp:
                archive_path = Path(tmp.name)
            with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("seed.txt", b"seeded ready archive")
            return archive_path

        def _add(bundle_id: str, status: str, urls: list[str]) -> None:
            # FIXME: status is seeded as plain str (not BundleState enum) because
            # bundler_app_server_gen tests currently do not import/use the enum
            # from bundler_core models directly.
            record = bundles_impl.BundleRecord(
                id=bundle_id,
                key=bundle_id,
                status=status,
                created_at=now,
                updated_at=now,
                folder_name="",
                compression="zip",
                urls=urls,
            )
            # New core behavior requires a real archive artifact when status is complete.
            if bundle_id == "ready-id":
                archive_path = _build_ready_archive(bundle_id)
                record.archive_path = str(archive_path)
                record.archive_size_bytes = archive_path.stat().st_size
                record.content_type = "application/zip"
            bundles_impl._BUNDLE_BY_ID[bundle_id] = record
            bundles_impl._BUNDLE_ID_BY_KEY[bundle_id] = bundle_id

        # IDs are hard-coded in `bundler_app_server_gen/tests/test_v1.py` and `test_v2.py`.
        _add("found-bundle-id", "complete", urls=[])
        _add("ready-id", "complete", urls=["__bundler_stub__"])
        _add("not-ready", "pending", urls=[])

