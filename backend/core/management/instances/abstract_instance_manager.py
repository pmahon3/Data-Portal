from abc import abstractmethod, ABC
from uuid import UUID

from .models import Instance


class AbstractInstanceManager(ABC):

    @property
    @abstractmethod
    def instances(self) -> list[Instance]:
        """Return all instances."""

    @abstractmethod
    def get_instances(self, instance_names: set = None) -> dict[str, Instance]:
        """
        Get instances filtered by instance names.

        :param instance_names: Set of instance names to filter by. If None, returns all instances.
        :return: Dictionary mapping instance names to Instance objects.
        """

    @abstractmethod
    def save_instance(self, config) -> UUID:
        """
        Create and save an instance configuration.

        :param config: The instance configuration model (InstanceCreate).
        :return: The created Instance's UUID.
        """

    @abstractmethod
    def get_instances_by_uuid(self, uuids: list[UUID]) -> list[Instance]:
        """
        Get instances by UUID.

        :param uuids: UUID or list of UUIDs to search for.
        :return: List of matching instances.
        """

    @abstractmethod
    def get_instance_uuid(self, instance_name: str) -> UUID:
        """
        Get the UUID of an instance by its name.

        :param instance_name: The name of the instance.
        :return: The UUID of the instance.
        :raises KeyError: If instance with the given name is not found.
        """

    @abstractmethod
    def get_instance_by_uuid(self, uuid: UUID) -> Instance:
        """
        Get an instance by its UUID.

        :param uuid: The UUID of the instance.
        :return: The Instance object.
        :raises ValueError: If the instance is not found.
        """

    @abstractmethod
    def delete_instance(self, instance_uuid: UUID) -> bool:
        """
        Delete an instance.

        :param instance_uuid: The UUID of the instance to delete.
        :return: True if successful.
        :raises KeyError: If the instance is not found.
        """
