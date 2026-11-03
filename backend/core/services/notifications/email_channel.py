"""
Notifications by email, alongside the portal's own list (N-NOTIFY: both). Off until a mail relay is
set (``SMTP_HOST``; SA-MAIL). The email never names files, since file names can identify participants:
it says what happened, with counts, and links to the portal for the details. Sending happens in the
background, so a slow relay never slows the upload that raised it; a failure is logged.
"""
import logging
import os
import smtplib
import threading
from collections.abc import Callable
from email.message import EmailMessage
from uuid import UUID

logger = logging.getLogger(__name__)

SUBJECTS = {"stored": "INN portal: your upload is stored",
            "stored_with_failures": "INN portal: some files of your upload weren't stored"}


def _text(notification: dict) -> str:
    completed, failed = notification.get("completed"), notification.get("failed")
    if notification["kind"] == "stored_with_failures":
        what = f"{completed} files of your upload are stored; {failed} weren't stored."
    elif completed is not None:
        what = f"Your upload of {completed} files is stored."
    else:
        what = "Your upload is stored."
    return f"{what}\n\nSign in to the portal for the details: {os.getenv('PORTAL_URL', '')}\n"


def deliver(notification: dict, user_manager) -> None:
    """Send one notification to its user's email address."""
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = user_manager.get_user(UUID(notification["user"])).email
    message["Subject"] = SUBJECTS.get(notification["kind"], "INN portal: an update on your data")
    message.set_content(_text(notification))
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=30) as server:
        if os.getenv("SMTP_STARTTLS", "true").lower() != "false":
            server.starttls()
        if os.getenv("SMTP_USER"):
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(message)


def channel() -> Callable[[dict], None] | None:
    """The email channel, or None while no relay is set."""
    if not os.getenv("SMTP_HOST"):
        return None

    def send_in_background(notification: dict) -> None:
        from core.services.injectors import get_user_manager

        def run():
            try:
                deliver(notification, get_user_manager())
            except Exception:
                logger.exception("notification email failed for %s", notification["_id"])

        threading.Thread(target=run, daemon=True).start()

    return send_in_background
