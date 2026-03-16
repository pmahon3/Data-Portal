"""
MongoDB session management.

Provides a shared MongoClient singleton for the process lifetime.

Environment variables needed:
    MONGO_HOST
    MONGO_PORT
    MONGO_INIT_ROOT_USERNAME
    MONGO_INIT_ROOT_PASSWORD
"""

import logging
import os

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger('policy-manager')

_mongo_client: MongoClient | None = None

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
        user = os.environ["MONGO_INIT_ROOT_USERNAME"]
        password = os.environ["MONGO_INIT_ROOT_PASSWORD"]
        host = os.getenv("MONGO_HOST", "")
        port = os.getenv("MONGO_PORT", "27017")


        # Singleton synchronous shared MongoDB client connection. Using a singleton ensures that all consumers are ACID. 
        # If there are multiple instances of the client (e.g., multiple backends), the synchronous client does not 
        # guarantee asynchronous and thread-safe operations (across all instances) when interacting with MongoDB.
        _mongo_client = MongoClient(host=host, port=int(port), username=user, password=password)

        # Verify
        try:
            _mongo_client.admin.command("ping")
        except ConnectionFailure as e:
            logger.error('Failed to correct Mongo client')
            _mongo_client = None
            raise
        
        logger.info('Initialized Mongo client connection')

    return _mongo_client
