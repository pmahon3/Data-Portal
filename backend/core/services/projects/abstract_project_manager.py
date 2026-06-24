from abc import ABC, abstractmethod
from uuid import UUID


class ProjectAlreadyExistsError(ValueError):
    """Raised when attempting to create a project that already exists."""
    pass


class ProjectNotFoundError(ValueError):
    """Raised when attempting to access or modify a project that does not exist."""
    pass


class AbstractProjectManager(ABC):
    """
    Abstract base class defining the interface for project management.

    A **project** is a logical grouping that owns:
    - **Users** — members who can access the project's resources.
    - **Managers** — users with administrative privileges over the project.
    - **Storage instances** — data-storage backends associated with the project.

    All methods are abstract; subclasses must implement them with the appropriate
    storage and authorization backend.
    """

    @abstractmethod
    def get_all_projects(self) -> list[str]:
        """
        Retrieve the names of all existing projects.
        """
        pass

    @abstractmethod
    def get_project_id(self, project_name: str) -> str:
        """
        Look up the unique identifier for a given project by name.
        """
        pass

    @abstractmethod
    def create_project(self, project_name: str) -> str:
        """
        Create a new project with the given name.
        """
        pass

    @abstractmethod
    def delete_project(self, project_name: str) -> None:
        """
        Delete an existing project by name.
        """
        pass

    @abstractmethod
    def get_project_users(self, project_name: str) -> list[str]:
        """
        Retrieve the list of users who are members of a project.
        """
        pass

    @abstractmethod
    def add_project_user(self, project_name: str, username: str) -> None:
        """
        Add a user as a member of a project.
        """
        pass

    @abstractmethod
    def remove_project_user(self, project_name: str, username: str) -> None:
        """
        Remove a user from a project's membership.
        """
        pass

    @abstractmethod
    def is_project_manager(self, username: str, project_name: str) -> bool:
        """
        Check whether a given user is a manager of the specified project.
        """
        pass

    @abstractmethod
    def get_project_managers(self, project_name: str) -> list[str]:
        """
        Retrieve the list of managers for a project.
        """
        pass

    @abstractmethod
    def add_project_manager(self, project_name: str, username: str) -> None:
        """
        Promote a project member to manager status.
        """
        pass

    @abstractmethod
    def remove_project_manager(self, project_name: str, username: str) -> None:
        """
        Remove a project manager from a project
        """
        pass

    @abstractmethod
    def get_project_storage_instances(self, project_name: str) -> list[str]:
        """
        Retrieve the storage instances associated with a project.
        """
        pass

    @abstractmethod
    def add_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        """
        Associate a storage instance with a project.
        """
        pass

    @abstractmethod
    def remove_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        """
        Disassociate a storage instance from a project.
        """
        pass

    @abstractmethod
    def remove_instance_from_all_projects(self, instance_uuid: UUID) -> None:
        """
        Remove a storage instance from every project it belongs to.
        """
        pass

    @abstractmethod
    def can_manage_instance_for_user(self, current_user: dict, target_username: str, instance_uuid: UUID) -> bool:
        """
        Determine whether the current user has permission to manage a storage
        instance on behalf of another user.
        """
        pass
