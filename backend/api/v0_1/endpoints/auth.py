from fastapi import status, Depends, APIRouter
from fastapi.responses import JSONResponse

from api.v0_1.common import decode_token

auth_router = APIRouter(prefix='/auth', tags=["Authentication"])


@auth_router.get("/validate", response_class=JSONResponse)
def validate_token(user: dict = Depends(decode_token)) -> JSONResponse:
    """
    Validate the bearer token and return user information.
    For React frontend token validation.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"valid": True, "user": user}
    )
