"""Job persistence port (DB-agnostic)."""

from __future__ import annotations

from typing import Protocol

from bundler_core.models import BundleRecord


class JobStorePort(Protocol):
    """Persist and look up bundle records. One backend active at a time."""

    def get(self, bundle_id: str) -> BundleRecord | None:
        """Return the record for ``bundle_id``, or ``None``."""

    def get_by_key(self, key: str) -> BundleRecord | None:
        """Return the record for fingerprint ``key``, or ``None``."""

    def save(self, record: BundleRecord) -> None:
        """Insert or replace the record (keyed by id and fingerprint)."""

    def list_all(self) -> list[BundleRecord]:
        """Return all stored records (for snapshot / test reset)."""

    def count_by_status(self) -> dict[str, int]:
        """Return job counts keyed by status value string."""

    def clear(self) -> None:
        """Delete all records (tests / local reset)."""
