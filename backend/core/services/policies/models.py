from datetime import timedelta
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel


class Policy(BaseModel):
    user_uuid: Union[UUID, None] = None
    instance_uuid: Union[UUID, None] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    username: Optional[str] = None
    instance_name: Optional[str] = None


Policies = list[Policy]


class Agreement(BaseModel):
    uuid: UUID
    policies: Policies
    lifespan: timedelta
    version: float
