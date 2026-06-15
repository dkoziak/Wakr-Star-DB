from typing import Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import settings

_bearer = HTTPBearer(auto_error=False)


def _has_required_scope(payload: dict, required: str) -> bool:
    """Return True if the token payload grants *required* scope.

    Handles both the space-delimited string form ("wakr:read wakr:write")
    and the list form (["wakr:read", "wakr:write"]) that some IdPs emit.
    """
    scope: Union[str, list, None] = payload.get("scope")
    if scope is None:
        return False
    if isinstance(scope, list):
        return required in scope
    return required in scope.split()


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    # Debug mode: no token required — never enable in production
    if settings.debug:
        return credentials.credentials if credentials else "debug"

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Valid Bearer token required."}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    if not settings.jwt_public_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "INTERNAL", "message": "Auth not configured."}},
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=["RS256"],
            audience=settings.token_audience,
            issuer=settings.token_issuer,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Valid Bearer token required."}},
        )

    if not _has_required_scope(payload, "wakr:read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Token does not have the required scope: wakr:read.",
                }
            },
        )

    return token
