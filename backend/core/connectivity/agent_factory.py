from core.connectivity.agents import S3StorageAgent, DummyStorageAgent
from core.connectivity.abstract_storage_agent import AbstractStorageAgent

AVAILABLE_FLAVOURS = {
    S3StorageAgent.FLAVOUR: S3StorageAgent,
    DummyStorageAgent.FLAVOUR: DummyStorageAgent  # For testing only
}

# Factory for instantiating the correct AbstractStorageAgent based on configuration
def agent_factory(config: dict) -> AbstractStorageAgent:
    """
    Factory function to create a storage agent based on the provided configuration.

    :param config: Configuration dictionary containing the flavour and agent details.
    :return: An instance of AbstractStorageAgent (S3StorageAgent, DummyStorageAgent, etc.).
    :raises ValueError: If the flavour is unknown.
    """

    flavour = config.get('flavour')

    if flavour not in AVAILABLE_FLAVOURS:
        raise ValueError(f"Unknown storage flavour '{flavour}'")

    try:
        return AVAILABLE_FLAVOURS[flavour](**config['agent'])
    
    except PermissionError as e:
        raise PermissionError(f"Permission denied during '{flavour}' storage agent initialization") from e
    
    except ConnectionError as e:
        raise ConnectionError(f"Connection failed during '{flavour}' storage agent initialization") from e
    
    except ValueError as e:
        raise ValueError(f"Invalid configuration or credentials during '{flavour}' storage agent initialization") from e
    
    except Exception as e:
        raise RuntimeError(f"Unexpected error initializing '{flavour}' storage agent") from e
