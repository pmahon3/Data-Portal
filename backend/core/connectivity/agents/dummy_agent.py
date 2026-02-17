"""
Dummy Storage Agent for Testing

A minimal storage agent implementation that doesn't require actual
storage connectivity. Used exclusively for testing policy CRUD operations.
"""

from ..abstract_storage_agent import AbstractStorageAgent


class DummyStorageAgent(AbstractStorageAgent):
    """
    Dummy storage agent for testing purposes.

    Does not connect to any real storage - useful for testing
    policy operations without requiring actual storage infrastructure.
    """

    FLAVOUR: str = 'dummy'
    CONFIG: dict = {}  # No additional config required

    def __init__(self, instance_url: str):
        """Initialize dummy storage agent."""
        super().__init__(instance_url)

    def _secrets(self):
        """Return empty secrets dict for dummy agent."""
        return {}

    # Implement required abstract methods with no-op or minimal implementations
    # These won't be called during policy testing
    
    def smart_refresh_file_tree(self):
        """Dummy implementation - not used in policy tests."""
        raise NotImplementedError("Dummy agent does not support smart_refresh_file_tree")

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

    def refresh_connection(self):
        """Dummy implementation - no connection to refresh."""
        pass

    def close(self):
        """Dummy implementation - no resources to clean up."""
        pass
