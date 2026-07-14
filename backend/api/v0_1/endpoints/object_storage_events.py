import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.postgres.session import get_session
from core.services.object_storage_events import StorageEventService


router = APIRouter(prefix="/object-storage/events", tags=["Object Storage Events"])


def verify_webhook_secret(
    secret_header: str | None,
    secret_query: str | None,
) -> None:
    # Ceph calls this endpoint as a service, not as a logged-in user.
    # Use a shared secret for machine-to-machine webhook authentication.
    expected_secret = os.getenv("OBJECT_STORAGE_WEBHOOK_SECRET")
    if not expected_secret:
        return

    header_valid = (
        secret_header is not None
        and secrets.compare_digest(secret_header, expected_secret)
    )
    query_valid = (
        secret_query is not None
        and secrets.compare_digest(secret_query, expected_secret)
    )

    if header_valid or query_valid:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid object storage webhook secret",
    )


@router.post("")
async def receive_object_storage_event(
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    webhook_secret: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    verify_webhook_secret(x_webhook_secret, webhook_secret)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be a JSON object",
        )

    service = StorageEventService(session)
    try:
        events = await service.store_payload(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "received", "count": len(events)}
