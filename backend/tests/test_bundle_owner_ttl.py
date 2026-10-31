"""
Bundle-owner records (INN-272) expire with their bundles, a day after the bundler's own retention
(168 hours by default), so they don't pile up and never vanish before the bundle does: a bundle
without its owner record can't be fetched by anyone, its creator included.

Verifies: AC-3.
"""
from core.db.mongodb import mongo_client


class FakeCollection:
    def __init__(self):
        self.indexes = []

    def create_index(self, key, **options):
        self.indexes.append((key, options))


def test_owner_records_expire_a_day_after_the_bundlers_retention(monkeypatch):
    fake = FakeCollection()
    monkeypatch.setattr(mongo_client, "get_mongo_database", lambda: {"bundle-owners": fake})
    monkeypatch.delenv("BUNDLE_OWNER_RETENTION_HOURS", raising=False)
    mongo_client._bundle_owner_index_ready = False
    assert mongo_client.get_bundle_owner_collection() is fake
    assert fake.indexes == [("created_at", {"expireAfterSeconds": 192 * 3600})]


def test_the_retention_is_a_setting_and_the_index_is_made_once(monkeypatch):
    fake = FakeCollection()
    monkeypatch.setattr(mongo_client, "get_mongo_database", lambda: {"bundle-owners": fake})
    monkeypatch.setenv("BUNDLE_OWNER_RETENTION_HOURS", "48")
    mongo_client._bundle_owner_index_ready = False
    mongo_client.get_bundle_owner_collection()
    mongo_client.get_bundle_owner_collection()
    assert fake.indexes == [("created_at", {"expireAfterSeconds": 48 * 3600})]
