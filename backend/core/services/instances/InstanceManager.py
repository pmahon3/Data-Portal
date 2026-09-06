import logging
from typing import Any
from uuid import UUID

from pymongo.errors import DuplicateKeyError
from pymongo.collection import Collection
from sqlalchemy.ext.asyncio import AsyncSession

from .abstract_instance_manager import AbstractInstanceManager, InstanceConfig
from .models import Instance
from core.storage_agents import AbstractStorageAgent
from core.utils.encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger("instance-manager")


class BucketNameConflictError(ValueError):
    def __init__(self, bucket_names: list[str]) -> None:
        self.bucket_names = bucket_names
        super().__init__(
            f"Bucket name(s) already used by another storage instance: {', '.join(bucket_names)}"
        )


class InstanceNameConflictError(ValueError):
    """Raised when an instance name is already in use."""


class InstanceConnectionConflictError(ValueError):
    """Raised when an instance connection configuration is already in use."""


class InstanceManager(AbstractInstanceManager):

    def __init__(
        self,
        collection: Collection[dict[str, Any]] | None = None,
        encryption_key: str = "",
    ) -> None:
        self._collection = collection
        self._encryption_key = encryption_key
        # Dictionary of instance uuid to agent object
        self._agents = {}
        
        # For every instance, create a agent connection on startup
        if self._collection is not None:
            from core.storage_agents import agent_factory

            for doc in self._collection.find():
                instance_label = doc.get('name') or doc.get('uuid') or "Unknown"
                try:
                    # Initialize the agent, decrypt its secrets, then establish connections.
                    agent = agent_factory(doc)
                    self._decrypt_agent_secrets(agent)
                    agent.connect()
                    self._agents[str(doc["uuid"])] = agent
                except Exception as e:
                    logger.error(f"Failed to initialize instance '{instance_label}': {e}. Skipping agent.")

    def _encrypt_instance_doc(
        self, doc: dict[str, Any], agent: AbstractStorageAgent
    ) -> dict[str, Any]:
        """
        Encrypt the fields the storage agent declares as secrets.
        """
        agent_config = doc["agent"]
        secret_fields = agent.secrets()

        # Go through all fields and encrypt if it is secret
        for field, value in agent_config.items():
            if field not in secret_fields or value is None:
                continue

            agent_config[field] = encrypt_secret(value, self._encryption_key)
        return doc

    def _decrypt_agent_secrets(
        self, agent: AbstractStorageAgent
    ) -> AbstractStorageAgent:
        """
        Decrypt persisted secret values on an instantiated storage agent.
        """
        for field in agent.secrets():
            value = getattr(agent, field, None)
            if value is None:
                continue
            
            # Decrypt and set field as the decrypted value
            # The agent will clear this value after it connects
            setattr(agent, field, decrypt_secret(value, self._encryption_key))
        return agent

    @staticmethod
    async def get_existing_bucket_names(session: AsyncSession) -> set[str]:
        """
        Query PostgreSQL for all distinct bucket names currently tracked in the
        folder tree.  This is the authoritative source for bucket uniqueness
        enforcement. It does not depend on any storage instance being reachable.
        """
        from sqlalchemy import select
        from core.services.filetree.models.folder import Folder

        result = await session.execute(select(Folder.bucket).distinct())
        return set(result.scalars())

    def _validate_unique_bucket_names(
        self,
        new_agent: AbstractStorageAgent,
        existing_buckets: set[str] | None = None,
    ) -> None:
        """
        Reject bucket-backed instances that expose buckets already used elsewhere.
        """
        if not hasattr(new_agent, "fetch_all_buckets"):
            return

        try:
            new_buckets = set(new_agent.fetch_all_buckets())
        except Exception as e:
            logger.error(f"Could not fetch buckets from new agent: {e}.")
            raise RuntimeError(
                "Unable to verify bucket names for the new storage instance. "
                "The storage service may be unreachable. Please try again later."
            ) from e

        if not new_buckets:
            return

        # Resolve the set of already-known bucket names.
        if existing_buckets is None:
            # Legacy path — requires every existing agent to be online.
            existing_buckets = set()
            for existing_agent in self._agents.values():
                if hasattr(existing_agent, "fetch_all_buckets"):
                    try:
                        existing_buckets.update(existing_agent.fetch_all_buckets())
                    except Exception as e:
                        logger.error(f"Could not fetch buckets from agent: {e}.")
                        raise RuntimeError(
                            "Unable to verify bucket names against existing "
                            "storage instances. The storage service "
                            "may be unreachable."
                        ) from e

        conflicts = sorted(new_buckets & existing_buckets)
        if conflicts:
            raise BucketNameConflictError(conflicts)

    @property
    def instances(self) -> list[Instance]:
        """
        Dynamically fetch all instances from the MongoDB collection.
        This ensures the manager always uses the latest state from the database.
        """
        all_instances = []
        for doc in self._collection.find():
            agent = self._agents.get(str(doc["uuid"]))
            if agent:
                all_instances.append(Instance(
                    uuid=UUID(str(doc["uuid"])),
                    name=doc["name"],
                    flavour=doc["flavour"],
                    agent=agent
                ))
        return all_instances

    def get_instances(
        self, instance_names: set[str] | None = None
    ) -> dict[str, Instance]:
        """
        Get instances filtered by instance names.

        :param instance_names: Set of instance names to filter by. If None, returns all instances.
        :return: Dictionary mapping instance names to Instance objects.
        """
        query = {}
        if instance_names is not None:
            query = {"name": {"$in": list(instance_names)}}

        result = {}
        for doc in self._collection.find(query):
            agent = self._agents.get(str(doc["uuid"]))
            if agent:
                instance = Instance(
                    uuid=UUID(str(doc["uuid"])),
                    name=doc["name"],
                    flavour=doc["flavour"],
                    agent=agent
                )
                result[instance.name] = instance
        return result

    async def save_instance(
        self, config: InstanceConfig, session: AsyncSession
    ) -> UUID:
        """Fetch known buckets, then create the instance with validation."""
        existing_buckets = await self.get_existing_bucket_names(session)
        return self._save_instance(config, existing_buckets=existing_buckets)

    def _save_instance(
        self,
        config: InstanceConfig,
        existing_buckets: set[str] | None = None,
    ) -> UUID:
        """
        Create and save an instance configuration to the MongoDB database.
        Raises an error if the instance already exists.

        :param config: The instance configuration model (InstanceCreate).
        :param existing_buckets: Pre-fetched set of bucket names already
            tracked in the database (used for bucket-uniqueness validation).
            When *None*, the validation falls back to querying every live
            storage agent — which requires all instances to be reachable.
        :return: The created Instance's UUID.
        """
        from uuid import uuid4
        from core.storage_agents import agent_factory

        name_value = getattr(config, "instance_name", None)
        flavour = config.flavour
        
        # Generate UUID for the instance
        instance_uuid = uuid4()

        # Convert Pydantic model to dict for instance factory
        agent_cfg = config.dict(exclude={"flavour", "instance_name", "name", "project_names"})
        config_dict = {"agent": agent_cfg, "flavour": flavour}

        # Create and connect the storage agent for the instance (letting specific errors propagate up)
        agent = agent_factory(config_dict)

        # Create the instance object
        instance = Instance(
            uuid=instance_uuid,
            name=name_value,
            flavour=flavour,
            agent=agent
        )
        # Save instance to MongoDB
        connected = False
        try:
            db_config = self._encrypt_instance_doc(instance.config(secrets=True), agent)
            agent.connect()
            connected = True
            self._validate_unique_bucket_names(agent, existing_buckets=existing_buckets)
            self._collection.insert_one(db_config)
            
            self._agents[str(instance.uuid)] = instance.agent
            
            return instance.uuid
        except DuplicateKeyError as e:
            if connected and str(instance.uuid) not in self._agents and hasattr(agent, "close"):
                try:
                    agent.close()
                except Exception as close_error:
                    logger.warning(f"Error closing unsaved agent for instance '{name_value}': {close_error}")

            # MongoDB's keyPattern identifies the fields in the unique index that was violated.
            duplicate_key = (e.details or {}).get("keyPattern", {})
            if "name" in duplicate_key:
                raise InstanceNameConflictError(
                    f"Instance with name '{name_value}' already exists"
                ) from e

            instance_url = getattr(config, "instance_url", None)
            aws_access_key_id = getattr(config, "aws_access_key_id", None)
            if aws_access_key_id:
                message = f"Instance with URL '{instance_url}' and the provided access key already exists"
            else:
                message = f"Instance with URL '{instance_url}' already exists"
            raise InstanceConnectionConflictError(message) from e
        except Exception:
            if connected and str(instance.uuid) not in self._agents and hasattr(agent, "close"):
                try:
                    agent.close()
                except Exception as e:
                    logger.warning(f"Error closing unsaved agent for instance '{name_value}': {e}")
            raise

    def update_instance(self, instance_id: UUID, new_instance_name: str) -> bool:
        """
        Update an existing instance configuration.

        :param instance_id: The UUID of the instance to update.
        :param new_instance_name: The new name for the instance.
        :return: True if successful, False if the instance was not found.
        """
        if not new_instance_name or not new_instance_name.strip():
            return False
            
        try:
            result = self._collection.update_one(
                {"uuid": str(instance_id)},
                {"$set": {"name": new_instance_name}} 
            )
            return result.modified_count > 0 or result.matched_count > 0
        except DuplicateKeyError as e:
            raise InstanceNameConflictError(
                f"Instance with name '{new_instance_name}' already exists"
            ) from e

    def get_instances_by_uuid(self, uuids: list[UUID]) -> list[Instance]:
        """
        Get instances by UUID.

        :param uuids: UUID or list of UUIDs to search for.
        :return: List of matching instances.
        """
        if isinstance(uuids, UUID):
            uuids = [uuids]

        matching_instances = []
        uuid_strs = [str(u) for u in uuids]

        for doc in self._collection.find({"uuid": {"$in": uuid_strs}}):
            agent = self._agents.get(str(doc["uuid"]))
            if agent:
                matching_instances.append(Instance(
                    uuid=UUID(str(doc["uuid"])),
                    name=doc["name"],
                    flavour=doc["flavour"],
                    agent=agent
                ))
        return matching_instances

    def get_instance_uuid(self, instance_name: str) -> UUID:
        """
        Get the UUID of an instance by its name.

        :param instance_name: The name of the instance.
        :return: The UUID of the instance.
        :raises KeyError: If instance with the given name is not found.
        """
        doc = self._collection.find_one({"name": instance_name}, {"uuid": 1})
        if doc and "uuid" in doc:
            return UUID(str(doc["uuid"]))
        raise KeyError(f"Instance with name '{instance_name}' not found.")

    def get_instance_by_uuid(self, uuid: UUID) -> Instance:
        """
        Get an instance by its UUID.

        :param uuid: The UUID of the instance.
        :return: The Instance object.
        :raises ValueError: If the instance is not found.
        """
        doc = self._collection.find_one({"uuid": str(uuid)})
        if doc:
            agent = self._agents.get(str(doc["uuid"]))
            return Instance(
                uuid=UUID(str(doc["uuid"])),
                name=doc["name"],
                flavour=doc["flavour"],
                agent=agent
            )
        raise ValueError(f"Instance with UUID '{uuid}' not found.")

    def get_instance_by_name(self, instance_name: str) -> Instance:
        """
        Get an instance by its name in a single query.

        Equivalent to ``get_instance_by_uuid(get_instance_uuid(name))`` but
        without the second round trip: the agent comes from the in-memory
        ``_agents`` map, so the extra document read served no purpose.

        :param instance_name: The name of the instance.
        :return: The Instance object.
        :raises KeyError: If no instance with that name exists.
        """
        doc = self._collection.find_one({"name": instance_name})
        if not doc:
            raise KeyError(f"Instance with name '{instance_name}' not found.")

        return Instance(
            uuid=UUID(str(doc["uuid"])),
            name=doc["name"],
            flavour=doc["flavour"],
            agent=self._agents.get(str(doc["uuid"]))
        )

    def delete_instance(self, instance_uuid: UUID) -> bool:
        """
        Delete an instance from the database.

        :param instance_uuid: The UUID of the instance to delete.
        :return: True if successful.
        :raises KeyError: If the instance is not found.
        """
        result = self._collection.delete_one({"uuid": str(instance_uuid)})
        if result.deleted_count == 0:
            raise KeyError(f"Instance {str(instance_uuid)} not found.")
        
        # Remove agent from memory and close connection
        agent = self._agents.pop(str(instance_uuid), None)
        if agent and hasattr(agent, 'close'):
            try:
                agent.close()
            except Exception as e:
                logger.error(f"Error closing agent for instance {str(instance_uuid)}: {e}")

        return True

    def teardown(self) -> None:
        """
        Clean up all active agent connections.
        """
        for agent in self._agents.values():
            try:
                agent.close()
            except Exception as e:
                logger.warning(f"Error closing agent: {e}")
        self._agents.clear()
