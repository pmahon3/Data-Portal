"""
Notifications to researchers (strategy 5.1 step 5): what's recorded, who sees it, and that a channel
plugs in. MongoDB is replaced by an in-memory collection.

Verifies: NT-1.
"""
import pytest

from core.services import notifications
from api.v0_1.endpoints import notifications as endpoint


class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query):
        return FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs = sorted(self.docs, key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)


@pytest.fixture
def store(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(notifications.store, "_collection", lambda: collection)
    monkeypatch.setattr(notifications.store, "CHANNELS", [])
    return collection


def test_a_stored_upload_is_recorded_for_its_researcher(store):
    notifications.notify("u-1", "stored", "Stored scan.nii.gz", file_id=7)
    (n,) = notifications.for_user("u-1")
    assert n["kind"] == "stored" and n["file_id"] == 7 and n["message"] == "Stored scan.nii.gz"
    assert notifications.for_user("u-2") == []


def test_newest_first_and_capped(store):
    for i in range(60):
        notifications.notify("u-1", "stored", f"n{i}")
    listed = notifications.for_user("u-1")
    assert len(listed) == 50 and listed[0]["message"] == "n59"


def test_a_channel_plugs_in(store, monkeypatch):
    sent = []
    monkeypatch.setattr(notifications.store, "CHANNELS", [sent.append])
    notifications.notify("u-1", "stored", "Stored")
    assert [n["user"] for n in sent] == ["u-1"]


def test_a_failing_channel_never_fails_the_upload(store, monkeypatch):
    def broken(notification):
        raise RuntimeError("mail server down")

    monkeypatch.setattr(notifications.store, "CHANNELS", [broken])
    notifications.notify("u-1", "stored", "Stored")
    assert len(notifications.for_user("u-1")) == 1


def test_the_endpoint_lists_only_the_callers_own(store):
    notifications.notify("u-1", "stored", "mine", file_id=1)
    notifications.notify("u-2", "stored", "theirs", file_id=2)

    class Users:
        def get_user_uuid(self, username):
            return {"alice": "u-1"}[username]

    listed = endpoint.list_notifications(user={"preferred_username": "alice"}, user_manager=Users())
    assert [n.message for n in listed] == ["mine"] and listed[0].file_id == 1


def test_a_folder_upload_is_one_notification_with_its_counts(store):
    notifications.folder_stored("u-1", folder_id=3, completed=2998, failed=2)
    (n,) = notifications.for_user("u-1")
    assert (n["kind"], n["folder_id"], n["completed"], n["failed"]) == ("stored_with_failures", 3, 2998, 2)


# --- email (N-NOTIFY: told both in the portal and by email) ---

from uuid import UUID  # noqa: E402

from core.services.notifications import email_channel  # noqa: E402

ALICE = "6a1f1c2e-0000-4000-8000-000000000001"


class Users:
    def get_user(self, uuid):
        assert uuid == UUID(ALICE)
        return type("User", (), {"email": "alice@example.org"})()


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        pass

    def send_message(self, message):
        FakeSMTP.sent.append((self, message))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(email_channel.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "relay.example.org")
    monkeypatch.setenv("SMTP_FROM", "portal@example.org")
    monkeypatch.setenv("PORTAL_URL", "https://portal.example.org")
    return FakeSMTP.sent


def test_an_email_tells_the_researcher_without_naming_files(smtp):
    note = {"user": ALICE, "kind": "stored", "message": "Stored P0042_scan.nii.gz", "file_id": 7}
    email_channel.deliver(note, Users())
    ((server, message),) = smtp
    body = message.get_content()
    assert message["To"] == "alice@example.org" and message["From"] == "portal@example.org"
    assert "P0042" not in body and "P0042" not in message["Subject"]  # file names can identify participants
    assert "https://portal.example.org" in body and server.tls


def test_an_email_says_when_files_failed(smtp):
    email_channel.deliver({"user": ALICE, "kind": "stored_with_failures", "message": "x",
                           "completed": 98, "failed": 2}, Users())
    ((_, message),) = smtp
    assert "2" in message["Subject"] + message.get_content() and "weren't stored" in message.get_content()


def test_email_is_off_until_a_relay_is_set(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert email_channel.channel() is None
    monkeypatch.setenv("SMTP_HOST", "relay.example.org")
    assert callable(email_channel.channel())
