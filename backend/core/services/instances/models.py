from uuid import UUID

from pydantic import BaseModel

from core.storage_agents import AbstractStorageAgent


# todo incorporate model
class Instance(BaseModel):
    """
    Instance
    Class representing a storage instance.

    Attributes:
    - uuid: UUID
    - name: str
    - agent: AbstractStorageAgent
    """
    uuid: UUID
    name: str
    flavour: str
    agent: AbstractStorageAgent

    class Config:
        arbitrary_types_allowed = True

    def config(self, secrets: bool = False):
        """
        Returns the configuration of the instance.
        This is a placeholder for the actual implementation.
        """
        return {
            "uuid": str(self.uuid),
            "name": self.name,
            "flavour": self.agent.FLAVOUR,
            "agent": self.agent.config(secrets) if self.agent else None
        }

    def close(self):
        """
        Perform explicit cleanup of resources held by this instance.
        For instance, if the agent holds connections or open files, they
        should be closed here.
        """
        if self.agent:
            # Assuming your AbstractStorageAgent implements a method like close() to free resources.
            self.agent.close()

    def __del__(self):
        """
        Destructor to try to ensure cleanup.
        Note: __del__ is not guaranteed to be called deterministically,
        so you should explicitly call close() when you know the Instance is no longer needed.
        """
        self.close()

    def __str__(self):
        """
        String representation of the Instance.
        """
        return f"Instance(uuid={self.uuid}, name={self.name}, agent={self.agent.__str__()})"

    def __eq__(self, other):
        """
        Equality check based on UUID.
        """
        if isinstance(other, Instance):
            return self.uuid == other.uuid
        return False
