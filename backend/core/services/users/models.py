from uuid import UUID

from pydantic import BaseModel, field_validator

DEFAULT_USER_ROLE = "user"

# Realm roles an admin or project manager may assign through the portal. Each must exist
# in the Keycloak realm. The realm also defines data-manager, but nothing in the portal uses it.
ASSIGNABLE_ROLES = ("user", "admin")


def normalize_roles(roles: list[str]) -> list[str]:
    """Default an empty role list and reject roles the portal doesn't assign.

    Keycloak role names are case-sensitive, so the check is exact. Rejecting here,
    before the account is created, avoids leaving a user with no application role
    behind when Keycloak can't find a requested role.
    """
    if not roles:
        return [DEFAULT_USER_ROLE]
    unknown = [role for role in roles if role not in ASSIGNABLE_ROLES]
    if unknown:
        raise ValueError(
            f"Unknown role(s): {', '.join(unknown)}. Allowed roles: {', '.join(ASSIGNABLE_ROLES)}"
        )
    return roles


class User(BaseModel):
    username: str
    uuid: UUID
    email: str
    roles: list[str]


class UserCreate(BaseModel):
    username: str
    email: str
    roles: list[str] = [DEFAULT_USER_ROLE]
    password: str

    @field_validator("roles")
    @classmethod
    def default_empty_roles(cls, roles: list[str]) -> list[str]:
        """Fall back to the default role when no roles are supplied, and reject unknown roles.

        The admin UI sends an empty list when its roles field is left blank, so
        a plain default on the field alone would not cover that case and the
        account would be created with no application role at all.
        """
        return normalize_roles(roles)
