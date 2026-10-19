"""
MongoDB schema initialization helpers.

Defines and ensures indexes required by the application.
"""

import logging

from pymongo import ASCENDING, IndexModel

from .mongo_client import (
    get_instance_collection,
    get_policy_rule_collection,
    get_project_instance_association_collection,
)

logger = logging.getLogger(__name__)

INSTANCE_INDEXES = [
    IndexModel(
        [("name", ASCENDING)],
        unique=True,
        sparse=True,
    ),
    IndexModel(
        [("agent.instance_url", ASCENDING), ("agent.aws_access_key_id", ASCENDING)],
        unique=True,
        sparse=True,
    ),
]

PROJECT_INSTANCE_ASSOCIATION_INDEXES = [
    IndexModel(
        [("project_id", ASCENDING), ("instance_uuid", ASCENDING)],
        unique=True,
    ),
]

# Each request reads one user's rules on one instance (policy type, user, instance)
POLICY_RULE_INDEXES = [
    IndexModel([("ptype", ASCENDING), ("v0", ASCENDING), ("v1", ASCENDING)]),
]


def ensure_instance_indexes() -> None:
    """
    Ensure indexes exist for the instance collection.
    """
    collection = get_instance_collection()

    logger.info("Ensuring MongoDB instance indexes")
    collection.create_indexes(INSTANCE_INDEXES)
    logger.info("MongoDB instance indexes are ready")


def ensure_project_instance_association_indexes() -> None:
    """
    Ensure unique indexes exist for the project-instance association collection.
    """
    collection = get_project_instance_association_collection()

    logger.info("Ensuring MongoDB project-instance association indexes")
    collection.create_indexes(PROJECT_INSTANCE_ASSOCIATION_INDEXES)
    logger.info("MongoDB project-instance association indexes are ready")


def ensure_policy_rule_indexes() -> None:
    """
    Ensure the index used to load a user's policy rules exists.
    """
    collection = get_policy_rule_collection()

    logger.info("Ensuring MongoDB policy rule indexes")
    collection.create_indexes(POLICY_RULE_INDEXES)
    logger.info("MongoDB policy rule indexes are ready")
