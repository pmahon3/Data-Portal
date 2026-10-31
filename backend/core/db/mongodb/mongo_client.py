"""
MongoDB session management.

Provides a shared MongoClient singleton for the process lifetime.

Environment variables needed:
    MONGO_URI or (MONGO_HOST, MONGO_PORT, MONGO_INIT_ROOT_USERNAME, MONGO_INIT_ROOT_PASSWORD)
"""

import logging
import os

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure

logger = logging.getLogger('policy-manager')

_mongo_client: MongoClient | None = None

# The Casbin adapter's default collection name
POLICY_RULE_COLLECTION = "casbin_rule"

def get_mongo_client() -> MongoClient:
    """
    Return a shared MongoClient

    The client is created on first call and reused

    :returns: The shared ``MongoClient``.
    :raises ConnectionFailure: If the server cannot be reached.
    :raises KeyError: If required env vars are missing.
    """
    global _mongo_client

    if _mongo_client is None:
        if "MONGO_URI" in os.environ:
            _mongo_client = MongoClient(os.environ["MONGO_URI"])
        else:
            user = os.environ["MONGO_INIT_ROOT_USERNAME"]
            password = os.environ["MONGO_INIT_ROOT_PASSWORD"]
            host = os.getenv("MONGO_HOST", "")
            port = os.getenv("MONGO_PORT", "27017")
            _mongo_client = MongoClient(host=host, port=int(port), username=user, password=password)

        # Verify
        try:
            _mongo_client.admin.command("ping")
        except ConnectionFailure as e:
            logger.error('Failed to correct Mongo client')
            _mongo_client = None
            raise
        
        logger.info('Successfully connected to MongoDB')

    return _mongo_client


def get_mongo_database() -> Database:
    """
    Return the configured MongoDB database.
    """
    client = get_mongo_client()
    return client[os.getenv("MONGO_DB", "inn-mongo")]


def get_instance_collection() -> Collection:
    """
    Return the MongoDB collection used for storage instances.
    """
    db = get_mongo_database()
    return db[os.getenv("MONGO_INSTANCE_COLLECTION", "connection-storage-instances")]


def get_policy_rule_collection() -> Collection:
    """
    Return the MongoDB collection the Casbin adapter stores policy rules in.
    """
    db = get_mongo_database()
    return db[POLICY_RULE_COLLECTION]


def get_project_instance_association_collection() -> Collection:
    """
    Return the MongoDB collection used for project-instance associations.
    """
    db = get_mongo_database()
    return db[os.getenv("MONGO_PROJECT_INSTANCE_ASSOCIATION_COLLECTION", "project-instance-associations")]


_bundle_owner_index_ready = False


def get_bundle_owner_collection() -> Collection:
    """
    Return the MongoDB collection that records who asked for each bundle (keyed by bundle id).

    Records expire BUNDLE_OWNER_RETENTION_HOURS after they're made (default 192: a day after the
    bundler deletes a finished bundle, 168 hours by default), so they never outlive their use by long
    and never vanish before the bundle does.
    """
    global _bundle_owner_index_ready
    collection = get_mongo_database()[os.getenv("MONGO_BUNDLE_OWNER_COLLECTION", "bundle-owners")]
    if not _bundle_owner_index_ready:
        hours = int(os.getenv("BUNDLE_OWNER_RETENTION_HOURS", "192"))
        collection.create_index("created_at", expireAfterSeconds=hours * 3600)
        _bundle_owner_index_ready = True
    return collection
