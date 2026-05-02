"""FastAPI Depends providers."""
import logging

from fastapi import Header, HTTPException, Request

from services.token_service import verify_token, track_auth_failure

logger = logging.getLogger(__name__)


async def require_token(
    request: Request,
    authorization: str | None = Header(None),
) -> dict:
    """Verify Authorization: Bearer <token>. Raises 401 on miss/invalid.

    On failure, tracks the client IP for Discord ops-burst notification.
    """
    client_ip = request.client.host if request.client else "unknown"

    if not authorization or not authorization.startswith("Bearer "):
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = authorization[len("Bearer "):].strip()
    record = verify_token(token)
    if record is None:
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    return record
