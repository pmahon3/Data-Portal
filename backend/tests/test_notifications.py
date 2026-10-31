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
