"""
Dummy Storage Agent for Testing

A minimal storage agent implementation that doesn't require actual
storage connectivity. Used exclusively for testing policy CRUD operations.
"""

from core.storage_agents.abstract_storage_agent import AbstractStorageAgent


class DummyStorageAgent(AbstractStorageAgent):
    """
    Dummy storage agent for testing purposes.

    Does not connect to any real storage - useful for testing
    policy operations without requiring actual storage infrastructure.
    """

    FLAVOUR: str = 'dummy'
    CONFIG: dict = {
        "instance_url": str
    }
    def __init__(self, instance_url: str):
        """Initialize dummy storage agent."""
        super().__init__(instance_url)

    @classmethod
    def secrets(cls) -> set[str]:
        """Return the secret config field names for this agent."""
        return set()

    def get_object(self, object_name: str):
        """Dummy implementation - not used in policy tests."""
        raise NotImplementedError("Dummy agent does not support get_object")

    def put_object(self, object_name: str, data):
        """Dummy implementation - not used in policy tests."""
        raise NotImplementedError("Dummy agent does not support put_object")

    def delete_object(self, object_name: str):
        """Dummy implementation - not used in policy tests."""
        raise NotImplementedError("Dummy agent does not support delete_object")

    def list_objects(self, prefix: str = ""):
        """Dummy implementation - not used in policy tests."""
        return []

    def fetch_all_buckets(self):
        """Return no buckets because the dummy agent has no backing storage."""
        return []

    def connect(self):
        """Dummy implementation - no connection to establish."""
        self.clear_secrets()

    def close(self):
        """Dummy implementation - no resources to clean up."""
        pass
