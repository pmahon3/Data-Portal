"""In-memory job store (default when ``MONGO_URI`` is unset)."""

from __future__ import annotations

from bundler_core.models import BundleRecord, BundleState


class InMemoryJobStore:
    """Process-local dicts; same behavior as the former BundleService maps."""

    def __init__(self) -> None:
        self.by_id: dict[str, BundleRecord] = {}
        self.by_key: dict[str, str] = {}

    def get(self, bundle_id: str) -> BundleRecord | None:
        return self.by_id.get(bundle_id)

    def get_by_key(self, key: str) -> BundleRecord | None:
        bundle_id = self.by_key.get(key)
        if bundle_id is None:
            return None
        return self.by_id.get(bundle_id)

    def save(self, record: BundleRecord) -> None:
        self.by_id[record.id] = record
        self.by_key[record.key] = record.id

    def list_all(self) -> list[BundleRecord]:
        return list(self.by_id.values())

    def count_by_status(self) -> dict[str, int]:
        counts = {state.value: 0 for state in BundleState}
        for record in self.by_id.values():
            status = record.status.value if isinstance(record.status, BundleState) else str(record.status)
            counts[status] = counts.get(status, 0) + 1
        return counts

    def clear(self) -> None:
        self.by_id.clear()
        self.by_key.clear()
