"""
Failing tests of Casbin MongoDB migration

These tests define the expected behaviour of a MongoDB Casbin adapter.

  * They are designed to FAIL with the current file-based CasbinPolicyManager.
  * They should PASS once the migration to a MongoDB database adapter is complete.

Two behaviours are verified:

  1. No local .policies files are created / modified — all persistence happens
     inside MongoDB.

  2. Manager __init__ does not need a UUID list or local .policies files.
     All state is loaded directly from MongoDB on startup.

All tests should show FAILED.  After migration every test should show PASSED.
"""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from core.injection import get_policy_manager
from core.management.policies.models import Policy

# --- Test fixtures -----------------------------------------------------------

@pytest.fixture()
def policy_dir():
    """Return the USER_POLICIES directory already set in the environment."""
    return Path(os.environ["USER_POLICIES"])


@pytest.fixture(autouse=True)
def cleanup_policies(sample_policy):
    """Delete policies from the database created during the test."""
    yield
    manager = get_policy_manager()
    try:
        manager.remove_user_policy_store(sample_policy.user_uuid)
    except Exception:
        pass


@pytest.fixture()
def sample_policy():
    """A minimal valid Policy object with random UUIDs."""
    return Policy(
        user_uuid=uuid4(),
        instance_uuid=uuid4(),
        resource="bucket/folder/",
        action="read",
    )


def test_add_policy_does_not_create_policy_file(policy_dir, sample_policy):
    """
    Test that add_policy() does not write a .policies file to disk.

    WHY IT FAILS NOW:
        add_policy() calls _write_user_policy(), which opens
        '{user_uuid}.policies' in append mode, creating the file.

    WHY IT PASSES AFTER MIGRATION:
        The MongoDB adapter stores the policy as a document; it never
        touches the filesystem.
    """
    manager = get_policy_manager()
    manager.add_policy(sample_policy)

    policy_files = list(policy_dir.glob("*.policies"))
    assert policy_files == [], (
        f"Files found on disk: {[f.name for f in policy_files]}"
    )


def test_remove_policy_does_not_write_policy_file(policy_dir, sample_policy):
    """
    Test that remove_policy() does not write a .policies file to disk.

    WHY IT FAILS NOW:
        remove_policy() calls _write_user_policies(), which rewrites
        '{user_uuid}.policies' to reflect the remaining policies.

    WHY IT PASSES AFTER MIGRATION:
        The MongoDB adapter deletes the corresponding document;
        no file is created or modified.
    """
    manager = get_policy_manager()
    manager.add_policy(sample_policy)
    manager.remove_policy(sample_policy)

    policy_files = list(policy_dir.glob("*.policies"))
    assert policy_files == [], (
        f"Files still on disk: {[f.name for f in policy_files]}"
    )


def test_remove_user_policy_store_does_not_require_file():
    """
    Test that remove_user_policy_store() does not raise when no file exists.
    Assuming we keep remove_user_policy_store to remove all of a user's policies

    WHY IT FAILS NOW:
        remove_user_policy_store() calls Path.unlink() to delete the
        '{user_uuid}.policies' file. 

    WHY IT PASSES AFTER MIGRATION:
        The MongoDB adapter deletes the user's documents from the
        database; it never calls Path.unlink() 
    """
    manager = get_policy_manager()
    user_uuid = uuid4()

    try:
        manager.remove_user_policy_store(user_uuid)
    except FileNotFoundError as exc:
        pytest.fail(
            "MongoDB adapter must NOT access the filesystem in "
            f"remove_user_policy_store().  Got FileNotFoundError: {exc}"
        )


def test_init_loads_previous_policies(sample_policy):
    """
    Test that a new manager instance loads all policies from MongoDB on init.

    WHY IT FAILS NOW:
        With uuids=[], __init__ reads no .policies files from disk, so
        the internal enforcer has no policies.

    WHY IT PASSES AFTER MIGRATION:
        The MongoDB adapter always loads ALL existing policies from the
        database during __init__
    """
    # Manager 1 — persist a policy
    manager1 = get_policy_manager()
    manager1.add_policy(sample_policy)

    # Manager 2 — cold-start, no uuid list supplied
    manager2 = get_policy_manager()

    result = manager2.validate_policy(sample_policy)
    assert result is True, (
        "MongoDB adapter must load all stored policies from the database"
    )