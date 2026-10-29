from typing import Any

import jwt
from fastapi import APIRouter, Header, HTTPException, Response, status

from core.services.storage_links import bundle_list, get_link_signer


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


@router.get("/bundles/{grant}")
def storage_link_bundle(grant: str, authorization: str = Header("")) -> Response:
    """
    The file list of an approved multi-file download, for the file service that streams it. The file
    service presents the download's own link, so no other credential is needed.
    """
    scheme, _, token = authorization.partition(" ")
    try:
        claims = get_link_signer().verify(token)
    except (RuntimeError, jwt.PyJWTError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired link")
    if scheme.lower() != "bearer" or claims["op"] != "bundle" or claims.get("grant") != grant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Link doesn't allow this request")
    body = bundle_list(grant)
    if body is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such download")
    return Response(content=body, media_type="application/json")
