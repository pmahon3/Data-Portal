from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.v0_1.endpoints.auth import decode_token
from core.services import notifications
from core.services.injectors import get_user_manager
from core.services.users import AbstractUserManager

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: str
    kind: str
    message: str
    created_at: datetime
    file_id: int | None = None
    folder_id: int | None = None
    completed: int | None = None
    failed: int | None = None


@router.get("/", response_model=list[NotificationOut])
def list_notifications(
    user: dict = Depends(decode_token),
    user_manager: AbstractUserManager = Depends(get_user_manager),
) -> list[NotificationOut]:
    """The caller's own notifications, newest first."""
    user_uuid = str(user_manager.get_user_uuid(user["preferred_username"]))
    # MongoDB returns UTC times without a zone; mark them, or browsers read them as local time.
    return [NotificationOut(id=n["_id"], **{k: v for k, v in n.items() if k not in ("_id", "user", "created_at")},
                            created_at=n["created_at"].replace(tzinfo=UTC))
            for n in notifications.for_user(user_uuid)]
