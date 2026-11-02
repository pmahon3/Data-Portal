"""
Record approved multi-file downloads from POSIX storage: the file list each one may stream.

The portal checks access to every file, records the list here, and signs one link carrying the
list's SHA-256. The file service fetches the list with that link and streams the files as one ZIP;
it refuses a list whose digest doesn't match, and anything not on it.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime

from core.db.mongodb.mongo_client import get_mongo_database


def _collection():
    return get_mongo_database()[os.getenv("MONGO_POSIX_BUNDLE_COLLECTION", "posix-bundles")]


def record_bundle(paths: list[str], folder_name: str, owner: str) -> tuple[str, str]:
    """
    Record an approved file list and return its approval ID and the SHA-256 of the list as served.

    ``paths`` holds each file's ``namespace/key``, in archive order; ``folder_name`` is the top-level
    folder inside the archive ("" for none), as the bundler uses it.

    Example: ``record_bundle(["posix/a.nii"], "StudyA", owner)`` serves
    ``{"folder_name":"StudyA","paths":["posix/a.nii"]}``
    """
    grant = uuid.uuid4().hex
    body = json.dumps({"folder_name": folder_name, "paths": paths}, separators=(",", ":"))
    _collection().insert_one({
        "_id": grant,
        "owner": owner,
        "body": body,
        "created_at": datetime.utcnow(),
    })
    return grant, hashlib.sha256(body.encode()).hexdigest()


def bundle_list(grant: str) -> str | None:
    """Return the recorded list for an approval ID, exactly as its digest was taken; None if unknown."""
    record = _collection().find_one({"_id": grant})
    if record:
        return record["body"]
    return None
