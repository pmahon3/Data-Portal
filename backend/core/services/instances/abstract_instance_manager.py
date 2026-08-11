from abc import abstractmethod, ABC
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Instance


class InstanceConfig(Protocol):
    flavour: str
    instance_name: str

    def dict(self, *, exclude: set[str]) -> dict[str, Any]: ...


class AbstractInstanceManager(ABC):

    @property
    @abstractmethod
    def instances(self) -> list[Instance]:
        """Return all instances."""

    @abstractmethod
    def get_instances(
        self, instance_names: set[str] | None = None
    ) -> dict[str, Instance]:
        """
        Get instances filtered by instance names.

        :param instance_names: Set of instance names to filter by. If None, returns all instances.
        :return: Dictionary mapping instance names to Instance objects.
        """

    @abstractmethod
    async def save_instance(
        self, config: InstanceConfig, session: AsyncSession
    ) -> UUID:
        """
        Fetch known buckets, validate, and save an instance configuration.
        :return: The created Instance's UUID.
        """

    @abstractmethod
    def _save_instance(
        self,
        config: InstanceConfig,
        existing_buckets: set[str] | None = None,
    ) -> UUID:
        """Create and save an instance using a pre-fetched bucket set."""

    @abstractmethod
    def update_instance(self, instance_id: UUID, new_instance_name: str) -> bool:
        """
        Update an existing instance configuration.

        :param instance_id: The UUID of the instance to update.
        :param new_instance_name: The new name for the instance.
        :return: True if successful, False if the instance was not found.
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
