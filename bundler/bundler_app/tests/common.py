"""Shared helpers for ``bundler_app`` tests."""

from __future__ import annotations

from time import sleep

from app import api
from app import bundles as bundles_impl


def reset_bundle_test_state() -> None:
    """Clear in-memory bundle state and stop worker runtime."""
    bundles_impl._reset_runtime_state_for_tests()


def wait_for_bundle_terminal_status(bundle_id: str, *, timeout_seconds: float = 5.0) -> str:
    """Poll until status is ``complete`` or ``failed``, or return last status after timeout."""
    elapsed = 0.0
    while elapsed < timeout_seconds:
        status = api.get_bundle_status(bundle_id)["status"]
        if status in {"complete", "failed"}:
            return status
        sleep(0.05)
        elapsed += 0.05
    return api.get_bundle_status(bundle_id)["status"]
