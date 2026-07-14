from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import unquote_plus

from sqlalchemy.ext.asyncio import AsyncSession

from .models import StorageEvent


def classify_action(event_type: str) -> str:
    """Map a Ceph/S3 event name to the worker action we store in Postgres."""
    if event_type.startswith("ObjectCreated:"):
        return "created"
    if event_type.startswith("ObjectRemoved:"):
        return "removed"
    return "unknown"


def parse_event_time(value: str | None) -> datetime | None:
    """Parse an event timestamp from the webhook payload, returning None if absent or invalid."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class StorageEventService:
    """Business logic for normalizing webhook payloads and storing storage event rows."""

    def __init__(self, session: AsyncSession):
        """Keep the request-scoped async database session used by this service."""
        self.session = session

    async def store_payload(self, payload: dict[str, Any]) -> list[StorageEvent]:
        """Validate Records[], convert each record to a StorageEvent, and commit them."""
        records = payload.get("Records", [])
        if not isinstance(records, list):
            raise ValueError("Payload field Records must be a list")

        events = [self._event_from_record(record) for record in records]
        if events:
            self.session.add_all(events)
            await self.session.commit()

        return events

    def _event_from_record(self, record: dict[str, Any]) -> StorageEvent:
        """Convert one raw Ceph/S3 Records[] item into a StorageEvent ORM object."""
        if not isinstance(record, dict):
            raise ValueError("Each Records[] item must be a JSON object")

        event_type = record.get("eventName") or ""
        s3 = record.get("s3") or {}
        bucket = s3.get("bucket") or {}
        obj = s3.get("object") or {}
        object_key = obj.get("key")
        bucket_name = bucket.get("name")

        if object_key is not None:
            # Ceph/S3 notifications URL-encode object keys; store the decoded key.
            object_key = unquote_plus(object_key)

        if not bucket_name:
            raise ValueError("Event record is missing s3.bucket.name")
        if not object_key:
            raise ValueError("Event record is missing s3.object.key")
        if not event_type:
            raise ValueError("Event record is missing eventName")

        return StorageEvent(
            event_id=record.get("eventId"),
            bucket=bucket_name,
            object_key=object_key,
            event_type=event_type,
            action=classify_action(event_type),
            size=obj.get("size"),
            etag=obj.get("eTag"),
            event_time=parse_event_time(record.get("eventTime")),
            status="pending",
            raw_event=record,
        )
