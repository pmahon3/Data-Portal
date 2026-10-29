"""
Approved multi-file downloads from POSIX storage: the file list each one may stream.

The portal checks access to every file, records the list here, and signs one link carrying the
list's SHA-256. The file service fetches the list with that link and streams the files as one ZIP;
it refuses a list whose digest doesn't match, and anything not on it.
"""
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
    Record an approved file list.

    :param paths: ``namespace/key`` of each file, in archive order.
    :param folder_name: Top-level folder inside the archive ("" for none), as the bundler uses it.
    :return: The approval ID and the SHA-256 of the list as served.
    """
    grant = uuid.uuid4().hex
    body = json.dumps({"folder_name": folder_name, "paths": paths}, separators=(",", ":"))
    _collection().insert_one({"_id": grant, "owner": owner, "body": body, "created_at": datetime.utcnow()})
    return grant, hashlib.sha256(body.encode()).hexdigest()


def bundle_list(grant: str) -> str | None:
    """The recorded list for an approval ID, exactly as its digest was taken."""
    record = _collection().find_one({"_id": grant})
    return record["body"] if record else None
