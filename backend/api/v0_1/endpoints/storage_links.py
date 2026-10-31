from typing import Any

from fastapi import APIRouter, HTTPException, status

from core.services.storage_links import get_link_signer


router = APIRouter(prefix="/storage-links", tags=["Storage Links"])


@router.get("/jwks.json")
def storage_link_jwks() -> dict[str, Any]:
    """Public key that POSIX file services use to check links signed by the portal."""
    # File services call this as a service, not as a logged-in user: it only publishes a public key.
    try:
        return get_link_signer().jwks()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage link signing isn't configured.",
        )
