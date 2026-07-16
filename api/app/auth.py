from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def _decode(token: str) -> dict:
    """Verify a Supabase access token.

    Modern projects sign with an asymmetric key (ES256) published at the
    project's JWKS endpoint; legacy projects use the shared HS256 secret.
    Dispatch on the token's alg header so both keep working.
    """
    settings = get_settings()
    header = jwt.get_unverified_header(token)
    if header.get("alg") == "ES256" and settings.supabase_jwks_url:
        key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token).key
        algorithms = ["ES256"]
    else:
        key = settings.supabase_jwt_secret
        algorithms = ["HS256"]
    return jwt.decode(
        token,
        key,
        algorithms=algorithms,
        audience="authenticated",
        options={"require": ["exp", "sub"]},
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = _decode(creds.credentials)
    except (jwt.PyJWTError, jwt.exceptions.PyJWKClientError):
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload["sub"]
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    return sub
