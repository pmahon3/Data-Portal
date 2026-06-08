from abc import ABC, abstractmethod
from uuid import UUID

from core.services.users.models import User, UserCreate


class ProjectAlreadyExistsError(ValueError):
    pass


class ProjectNotFoundError(ValueError):
    pass


class AbstractUserManager(ABC):
    @abstractmethod
    def create_user(self, user_details: UserCreate) -> User:
        pass

    @abstractmethod
    def get_user(self, uuid: UUID) -> User:
        pass

    @abstractmethod
    def delete_user(self, uuid: UUID) -> bool:
        pass

    @abstractmethod
    def get_all_users(self) -> list[User]:
        pass

    @abstractmethod
    def user_exists(self, user_slug: str) -> bool:
        pass

    @abstractmethod
    def get_user_slug(self, uuid: UUID) -> str:
        pass

    @abstractmethod
    def get_user_roles(self, uuid: UUID) -> list[str]:
        pass

    @abstractmethod
    def get_user_uuid(self, user_slug: str) -> UUID:
        pass

    @abstractmethod
    def get_user_uuids(self) -> list[UUID]:
        pass

    @abstractmethod
    def get_all_projects(self) -> list[str]:
        pass

    @abstractmethod
    def get_project_id(self, project_name: str) -> str:
        pass

    @abstractmethod
    def create_project(self, project_name: str) -> str:
        pass

    @abstractmethod
    def delete_project(self, project_name: str) -> None:
        pass

    @abstractmethod
    def is_project_manager(self, username: str, project_name: str) -> bool:
        pass

    @abstractmethod
    def get_project_users(self, project_name: str) -> list[str]:
        pass

    @abstractmethod
    def get_project_managers(self, project_name: str) -> list[str]:
        pass

    @abstractmethod
    def get_project_storage_instances(self, project_name: str) -> list[str]:
        pass

    @abstractmethod
    def add_project_user(self, project_name: str, username: str) -> None:
        pass

    @abstractmethod
    def remove_project_user(self, project_name: str, username: str) -> None:
        pass

    @abstractmethod
    def add_project_manager(self, project_name: str, username: str) -> None:
        pass

    @abstractmethod
    def remove_project_manager(self, project_name: str, username: str) -> None:
        pass

    @abstractmethod
    def add_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        pass

    @abstractmethod
    def remove_project_storage_instance(self, project_name: str, instance_name: str) -> None:
        pass

    @abstractmethod
    def remove_instance_from_all_projects(self, instance_uuid: UUID) -> None:
        pass

    @abstractmethod
    def can_manage_instance_for_user(self, current_user: dict, target_username: str, instance_uuid: UUID) -> bool:
        pass
