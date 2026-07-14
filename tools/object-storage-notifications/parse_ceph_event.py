#!/usr/bin/env python3
# Parse a saved Ceph/S3 webhook payload and print normalized JSON lines.
# Usage: python3 parse_ceph_event.py sample-event.json

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote_plus


def classify_action(event_type):
    if event_type.startswith("ObjectCreated:"):
        return "created"
    if event_type.startswith("ObjectRemoved:"):
        return "removed"
    return "unknown"


def normalize_record(record):
    event_type = record.get("eventName", "")
    s3 = record.get("s3") or {}
    bucket = s3.get("bucket") or {}
    obj = s3.get("object") or {}
    object_key = obj.get("key")

    if object_key is not None:
        object_key = unquote_plus(object_key)

    return {
        "event_id": record.get("eventId"),
        "event_time": record.get("eventTime"),
        "event_type": event_type,
        "action": classify_action(event_type),
        "bucket": bucket.get("name"),
        "object_key": object_key,
        "size": obj.get("size"),
        "etag": obj.get("eTag"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse a Ceph/S3 webhook payload and print normalized JSON lines."
    )
    parser.add_argument("payload", help="Path to a JSON webhook payload")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    try:
        with payload_path.open("r", encoding="utf-8") as payload_file:
            payload = json.load(payload_file)
    except OSError as exc:
        print(f"Failed to read {payload_path}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Failed to parse JSON in {payload_path}: {exc}", file=sys.stderr)
        return 1

    records = payload.get("Records", [])
    if not isinstance(records, list):
        print("Payload field Records must be a list", file=sys.stderr)
        return 1

    for record in records:
        print(json.dumps(normalize_record(record), sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
