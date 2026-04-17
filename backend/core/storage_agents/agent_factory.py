from core.storage_agents.abstract_storage_agent import AbstractStorageAgent
from core.storage_agents.s3_agent import S3StorageAgent
from core.storage_agents.dummy_agent import DummyStorageAgent

AVAILABLE_FLAVOURS = {
    S3StorageAgent.FLAVOUR: S3StorageAgent,
    DummyStorageAgent.FLAVOUR: DummyStorageAgent  # For testing only
}

# Factory for instantiating the correct AbstractStorageAgent based on configuration
def agent_factory(config: dict) -> AbstractStorageAgent:
    """
    Initializes a storage agent based on the provided configuration.

    This factory handles the instantiation of specific storage backends (e.g., S3 or Dummy)
    used to manage INN-owned or partner-owned research data. The factory is backend-agnostic
    and delegates backend-specific error handling to the concrete storage agents.

    :param config: A dictionary containing the 'flavour' (type) and 'agent' (credentials/path) details.
    :return: An initialized instance of a subclass of AbstractStorageAgent.
    :raises ValueError: If the requested storage type is unsupported or the configuration is invalid.
    :raises PermissionError: If the provided credentials lack the necessary access rights (raised by agents).
    :raises ConnectionError: If the storage service is unreachable or overloaded (raised by agents).
    :raises RuntimeError: If an unexpected system error occurs during initialization.
    """

    flavour = config.get('flavour')

    if flavour not in AVAILABLE_FLAVOURS:
        raise ValueError(f"The storage type '{flavour}' is not recognized by the system. Please select a supported storage flavour.")

    try:
        return AVAILABLE_FLAVOURS[flavour](**config.get('agent', {}))

    except Exception as e:
        # Propagrate error from storage agent
        raise