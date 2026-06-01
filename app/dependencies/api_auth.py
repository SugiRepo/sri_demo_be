import secrets

from fastapi import Header, HTTPException

from app.config import API_AUTH_ENABLED, API_KEYS


def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    if not API_AUTH_ENABLED:
        return

    if not API_KEYS:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "api_auth_misconfigured",
                "message": "API_AUTH_ENABLED is true but API_KEYS is empty.",
            },
        )

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_api_key",
                "message": "Missing X-API-Key header.",
            },
        )

    for valid_key in API_KEYS:
        if secrets.compare_digest(x_api_key, valid_key):
            return

    raise HTTPException(
        status_code=401,
        detail={
            "code": "invalid_api_key",
            "message": "Invalid or unauthorized API key.",
        },
    )
