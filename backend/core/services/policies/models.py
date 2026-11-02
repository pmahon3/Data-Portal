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
    excluded: list[str] = []  # paths inside a folder policy that it leaves out (AC-10)
    endings: list[str] = []  # if any, a folder policy covers only files ending in one (AC-6)
    # if any, only these kinds of data (AC-6), as the standard of the dataset rooted at `dataset`
    # ("bucket/folder/") defines them
    kinds: list[str] = []
    dataset: Optional[str] = None
    standard: Optional[str] = None  # e.g. "BIDS"


Policies = list[Policy]


class Agreement(BaseModel):
    uuid: UUID
    policies: Policies
    lifespan: timedelta
    version: float
