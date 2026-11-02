from datetime import date, timedelta
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
    ends: Optional[date] = None  # the last day the policy applies (AC-8); None for no end


Policies = list[Policy]


class Agreement(BaseModel):
    uuid: UUID
    policies: Policies
    lifespan: timedelta
    version: float
