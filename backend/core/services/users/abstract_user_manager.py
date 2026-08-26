from abc import ABC, abstractmethod
from uuid import UUID

from core.services.users.models import User, UserCreate


class UserCreationError(ValueError):
    """Base class for expected user creation failures."""


class InvalidUserEmailError(UserCreationError):
    """Raised when a user's email address is invalid."""


class UsernameRequiredError(UserCreationError):
    """Raised when a username is not provided."""


class UserAlreadyExistsError(UserCreationError):
    """Raised when attempting to create a user that already exists."""


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
