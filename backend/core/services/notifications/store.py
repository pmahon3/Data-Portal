"""
Notifications to researchers about their data (strategy 5.1: stored, and the exceptions: failed
validation, held in quarantine). Each is recorded per user in the portal and listed at
``GET /api/notifications/``, and also sent by every channel in ``CHANNELS``: researchers are told
both in the portal and by email (NT-NOTIFY). A channel that fails is logged and never fails the
operation that raised the notification.
"""
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime

from core.db.mongodb.mongo_client import get_mongo_database

logger = logging.getLogger(__name__)

LISTED = 50  # the newest this many are listed
CHANNELS: list[Callable[[dict], None]] = []  # delivery besides the portal's own list (email: see below)


def _collection():
    return get_mongo_database()[os.getenv("MONGO_NOTIFICATION_COLLECTION", "notifications")]


def notify(user: str, kind: str, message: str, **refs) -> dict:
    """
    Record a notification for ``user`` and pass it to each channel.

    :param kind: ``stored``, ``stored_with_failures``, ...
    :param refs: What it's about: ``file_id``, ``folder_id``, counts.
    """
    notification = {"_id": uuid.uuid4().hex, "user": user, "kind": kind, "message": message,
                    "created_at": datetime.utcnow(), **refs}
    _collection().insert_one(notification)
    for channel in CHANNELS:
        try:
            channel(notification)
        except Exception:
            logger.exception("notification channel %r failed", channel)
    return notification


def for_user(user: str) -> list[dict]:
    """The user's newest notifications, newest first."""
    return list(_collection().find({"user": user}).sort("created_at", -1).limit(LISTED))


def file_stored(user: str, file_id: int, name: str) -> dict:
    return notify(user, "stored", f"Stored {name}", file_id=file_id)


def folder_stored(user: str, folder_id: int, completed: int, failed: int) -> dict:
    if failed:
        return notify(user, "stored_with_failures", f"Stored {completed} files; {failed} failed and weren't stored",
                      folder_id=folder_id, completed=completed, failed=failed)
    return notify(user, "stored", f"Stored {completed} files", folder_id=folder_id, completed=completed, failed=0)


def _register_channels() -> None:
    from core.services.notifications import email_channel

    email = email_channel.channel()
    if email:
        CHANNELS.append(email)


_register_channels()
