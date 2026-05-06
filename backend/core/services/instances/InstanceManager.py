import logging
from uuid import UUID
from pymongo.errors import DuplicateKeyError

from .abstract_instance_manager import AbstractInstanceManager
from .models import Instance
from core.utils.encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger("instance-manager")

class InstanceManager(AbstractInstanceManager):

    def __init__(self, collection=None, encryption_key: str = ""):
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

    def _encrypt_instance_doc(self, doc: dict, agent) -> dict:
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

    def _decrypt_agent_secrets(self, agent):
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

    def get_instances(self, instance_names: set = None) -> dict[str, Instance]:
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

    def save_instance(self, config) -> UUID:
        """
        Create and save an instance configuration to the MongoDB database.
        Raises an error if the instance already exists.

        :param config: The instance configuration model (InstanceCreate).
        :return: The created Instance's UUID.
        """
        from uuid import uuid4
        from core.storage_agents import agent_factory

        name_value = getattr(config, "instance_name", None)
        flavour = config.flavour
        
        # Generate UUID for the instance
        instance_uuid = uuid4()

        # Convert Pydantic model to dict for instance factory
        agent_cfg = config.dict(exclude={"flavour", "instance_name", "name"})
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
        try:
            db_config = self._encrypt_instance_doc(instance.config(secrets=True), agent)
            agent.connect()
            self._collection.insert_one(db_config)
            
            self._agents[str(instance.uuid)] = instance.agent
            
            return instance.uuid
        except DuplicateKeyError as e:
            if "name" in str(e):
                raise ValueError(f"Instance with name '{name_value}' already exists")
            else:
                instance_url = getattr(config, "instance_url", None)
                aws_access_key_id = getattr(config, "aws_access_key_id", None)
                if aws_access_key_id:
                    raise ValueError(f"Instance with URL '{instance_url}' and the provided access key already exists")
                else:
                    raise ValueError(f"Instance with URL '{instance_url}' already exists")

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
        except DuplicateKeyError:
            raise ValueError(f"Instance with name '{new_instance_name}' already exists")

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

    def teardown(self):
        """
        Clean up all active agent connections.
        """
        for agent in self._agents.values():
            try:
                agent.close()
            except Exception as e:
                logger.warning(f"Error closing agent: {e}")
        self._agents.clear()
