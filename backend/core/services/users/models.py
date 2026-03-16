from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    username: str
    uuid: UUID
    email: str
    roles: list[str]


class UserCreate(BaseModel):
    username: str
    email: str
    roles: list[str]
