"""MongoDB job store (pymongo). Activated when ``MONGO_URI`` is set.

URI conventions:
- Database name: standard path segment (``mongodb://host:27017/mydb``).
- Collection name: ``collection`` query param (``...?collection=bundles``),
  default ``bundles`` if omitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import CollectionInvalid, OperationFailure

from bundler_core.archive_build.timings import ArchiveBuildTimings
from bundler_core.failures import FailureKind
from bundler_core.logger import logger
from bundler_core.models import BundleRecord, BundleState


def _parse_db_and_collection(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    path = (parsed.path or "").lstrip("/")
    db_name = path.split("/")[0] if path else ""
    if not db_name:
        db_name = "bundler"
    qs = parse_qs(parsed.query)
    collection = (qs.get("collection") or ["bundles"])[0]
    return db_name, collection


def _ensure_collection(db: Any, collection_name: str) -> Collection[Any]:
    """Create the collection if missing; on failure log a warning and continue."""
    try:
        if collection_name not in db.list_collection_names():
            db.create_collection(collection_name)
    except (OperationFailure, CollectionInvalid) as exc:
        logger.warning(
            "Could not ensure Mongo collection {!r} on db {!r}: {}. ",
            collection_name,
            getattr(db, "name", "?"),
            exc,
        )
    return db[collection_name]


def _record_to_doc(record: BundleRecord) -> dict[str, Any]:
    timings = record.last_build_timings
    return {
        "_id": record.id,
        "key": record.key,
        "status": record.status.value if isinstance(record.status, BundleState) else str(record.status),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "folder_name": record.folder_name,
        "compression": record.compression,
        "urls": list(record.urls),
        "result_url": record.result_url,
        "error_message": record.error_message,
        "archive_path": record.archive_path,
        "archive_size_bytes": record.archive_size_bytes,
        "content_type": record.content_type,
        "retry_count": record.retry_count,
        "failure_kind": record.failure_kind.value if record.failure_kind is not None else None,
        "last_build_strategy": record.last_build_strategy,
        "last_build_timings": None
        if timings is None
        else {
            "download_seconds": timings.download_seconds,
            "zip_seconds": timings.zip_seconds,
            "total_seconds": timings.total_seconds,
            "url_count": timings.url_count,
        },
    }


def _doc_to_record(doc: dict[str, Any]) -> BundleRecord:
    timings_raw = doc.get("last_build_timings")
    timings = None
    if isinstance(timings_raw, dict):
        timings = ArchiveBuildTimings(
            download_seconds=float(timings_raw["download_seconds"]),
            zip_seconds=float(timings_raw["zip_seconds"]),
            total_seconds=float(timings_raw["total_seconds"]),
            url_count=int(timings_raw["url_count"]),
        )
    failure_raw = doc.get("failure_kind")
    failure_kind = FailureKind(failure_raw) if failure_raw else None
    created_at = doc.get("created_at") or datetime.now(tz=timezone.utc)
    updated_at = doc.get("updated_at") or created_at
    return BundleRecord(
        id=str(doc["_id"]),
        key=str(doc.get("key") or doc["_id"]),
        status=BundleState(str(doc["status"])),
        created_at=created_at,
        updated_at=updated_at,
        folder_name=str(doc.get("folder_name") or ""),
        compression=str(doc.get("compression") or "zip"),
        urls=list(doc.get("urls") or []),
        result_url=doc.get("result_url"),
        error_message=doc.get("error_message"),
        archive_path=doc.get("archive_path"),
        archive_size_bytes=doc.get("archive_size_bytes"),
        content_type=doc.get("content_type"),
        retry_count=int(doc.get("retry_count") or 0),
        failure_kind=failure_kind,
        last_build_timings=timings,
        last_build_strategy=doc.get("last_build_strategy"),
    )


class MongoJobStore:
    """``JobStorePort`` backed by a MongoDB collection."""

    def __init__(self, uri: str) -> None:
        db_name, collection_name = _parse_db_and_collection(uri)
        self._client: MongoClient[Any] = MongoClient(uri)
        db = self._client[db_name]
        self._collection: Collection[Any] = _ensure_collection(db, collection_name)
        self._collection.create_index([("key", ASCENDING)], unique=True)

    def get(self, bundle_id: str) -> BundleRecord | None:
        doc = self._collection.find_one({"_id": bundle_id})
        return None if doc is None else _doc_to_record(doc)

    def get_by_key(self, key: str) -> BundleRecord | None:
        doc = self._collection.find_one({"key": key})
        return None if doc is None else _doc_to_record(doc)

    def save(self, record: BundleRecord) -> None:
        self._collection.replace_one({"_id": record.id}, _record_to_doc(record), upsert=True)

    def list_all(self) -> list[BundleRecord]:
        return [_doc_to_record(doc) for doc in self._collection.find()]

    def count_by_status(self) -> dict[str, int]:
        counts = {state.value: 0 for state in BundleState}
        for row in self._collection.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        ):
            status = str(row["_id"])
            counts[status] = int(row["n"])
        return counts

    def clear(self) -> None:
        self._collection.delete_many({})
