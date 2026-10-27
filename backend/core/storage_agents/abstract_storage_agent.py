from abc import ABC, abstractmethod
from typing import Any, Dict


class AbstractStorageAgent(ABC):
    """
    AbstractStorageAgent

    Class representing an agent.

    Methods:
    - __init__()
    - generate_access_link()
    """

    FLAVOUR = None
    CONFIG = {
        'instance_url': str
    }
    def __init__(self, instance_url: str):
        """
        Initialize a new instance of the class.

        :param instance_name: The slug for the access point.
        :type instance_name: str
        :param instance_url: The instance_url for the access point.
        :type instance_url: str
        """
        self.instance_url = instance_url

    def generate_access_link(self, resource: str, method: str, ttl: int, subject: str | None = None):
        """
        Generate a presigned access URL for an asset.

        :param resource: The key/regex of the asset(s).
        :param method: The method to use for accessing the asset.
        :param ttl: The time-to-live for the URL.
        :param subject: The portal user the link is for. Agents whose links can carry it (POSIX) do;
            S3 presigned URLs can't and ignore it.
        :return: The presigned URL.
        """
        raise NotImplementedError

    def delete_object(self, resource: str, subject: str | None = None):
        """
        Delete an object identified by its storage resource path.

        :param subject: The portal user asking; recorded where the storage can carry it (POSIX).
        """
        raise NotImplementedError

    def delete_objects(self, resources: list[str]):
        """Delete objects identified by their storage resource paths."""
        raise NotImplementedError

    def get_object_metadata(self, resource: str):
        """Return metadata for an object identified by its storage resource path."""
        raise NotImplementedError

    def config(self, secrets: bool = False) -> Dict[str, Any]:
        """
        Return the configuration of the agent. 

        :return: The configuration of the agent.
        """
        config = {}
        secret_fields = self.secrets()

        for key in self.CONFIG or {}:
            if not secrets and key in secret_fields:
                continue

            config[key] = getattr(self, key)

        return config

    @classmethod
    def secrets(cls) -> set[str]:
        """
        Return the config field names that should be treated as secrets.

        :return: A set of secret config field names.
        """
        return set()

    def clear_secrets(self):
        """
        Remove plaintext secret values from this agent.
        """
        for field in self.secrets():
            setattr(self, field, None)

    @abstractmethod
    def connect(self):
        """
        Establish any external connections needed before the agent is used.
        """
        pass

    @abstractmethod
    def close(self):
        """
        Perform explicit cleanup of resources held by this agent.
        For instance, if the agent holds connections or open files, they
        should be closed here.
        """
        pass
