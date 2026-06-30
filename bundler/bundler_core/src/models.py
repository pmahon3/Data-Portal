from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from bundler_core.failures import FailureKind
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

# Canonical URL string type: trim surrounding whitespace and reject empty values.
NonEmptyUrlString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BundleState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[BundleState, frozenset[BundleState]] = {
    BundleState.PENDING: frozenset({BundleState.PROCESSING, BundleState.FAILED}),
    BundleState.PROCESSING: frozenset({BundleState.COMPLETE, BundleState.FAILED}),
    BundleState.COMPLETE: frozenset(),
    BundleState.FAILED: frozenset({BundleState.PENDING}),
}


def can_transition(current: BundleState, new_state: BundleState) -> bool:
    return new_state in _ALLOWED_TRANSITIONS.get(current, frozenset[BundleState]())


class CreateBundleRequest(BaseModel):
    # Allow both Python field names (folder_name) and JSON aliases (folderName)
    # when constructing/validating this model.
    model_config = ConfigDict(populate_by_name=True)

    folder_name: str | None = Field(default=None, alias="folderName")
    urls: list[NonEmptyUrlString] = Field(..., min_length=1)
    compression: str = "zip"


@dataclass
class BundleRecord:
    id: str
    key: str
    status: BundleState
    created_at: datetime
    updated_at: datetime
    folder_name: str
    compression: str
    urls: list[str]
    result_url: str | None = None
    error_message: str | None = None
    archive_path: str | None = None
    archive_size_bytes: int | None = None
    content_type: str | None = None
    retry_count: int = 0
    failure_kind: FailureKind | None = None
