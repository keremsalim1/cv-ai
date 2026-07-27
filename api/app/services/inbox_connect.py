"""Gmail connection lifecycle: OAuth exchange, token storage, revocation."""
import logging

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)


class TokenError(Exception):
    pass


def _cipher() -> Fernet:
    key = get_settings().email_token_key
    if not key:
        raise TokenError("EMAIL_TOKEN_KEY is not set; cannot store Gmail tokens")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenError(f"EMAIL_TOKEN_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_token(plain: str) -> str:
    return _cipher().encrypt(plain.encode()).decode()


def decrypt_token(blob: str) -> str:
    try:
        return _cipher().decrypt(blob.encode()).decode()
    except InvalidToken as exc:
        raise TokenError("stored Gmail token could not be decrypted") from exc


TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class ConnectionError_(Exception):
    """The Gmail grant is missing, revoked, or was never completed."""


def _connection(db, user_id: str) -> dict | None:
    rows = db.select("email_connections",
                     {"user_id": f"eq.{user_id}", "select": "*"})
    return rows[0] if rows else None


def connect_gmail(db, http, user_id: str, code: str, redirect_uri: str) -> dict:
    settings = get_settings()
    resp = http.post(TOKEN_URL, data={
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    if resp.status_code >= 400:
        raise ConnectionError_(f"Google refused the authorization code: {resp.text}")
    payload = resp.json()

    refresh = payload.get("refresh_token")
    if not refresh:
        # Happens when consent was already granted and prompt=consent was
        # omitted. Without it we could sync once and then go silent forever.
        raise ConnectionError_("Google returned no refresh token; re-consent required")

    access = payload["access_token"]
    profile = http.get(PROFILE_URL, headers={"Authorization": f"Bearer {access}"})
    if profile.status_code >= 400:
        raise ConnectionError_(f"Gmail profile unreadable: {profile.text}")
    info = profile.json()

    db.delete("email_connections", {"user_id": f"eq.{user_id}"})
    db.insert("email_connections", {
        "user_id": user_id,
        "provider": "gmail",
        "email_address": info["emailAddress"],
        "refresh_token_enc": encrypt_token(refresh),
        "last_history_id": info.get("historyId"),
        "status": "active",
    })
    return {"connected": True, "email": info["emailAddress"]}


def disconnect_gmail(db, http, user_id: str) -> None:
    row = _connection(db, user_id)
    if row:
        try:
            http.post(REVOKE_URL, params={"token": decrypt_token(row["refresh_token_enc"])})
        except (TokenError, httpx.HTTPError) as exc:
            # Already revoked, or unreachable. Keeping our row would advertise a
            # connection that cannot work, so delete it regardless.
            logger.warning("[inbox] revoke failed for %s: %s", user_id, exc)
    db.delete("email_connections", {"user_id": f"eq.{user_id}"})


def connection_status(db, user_id: str) -> dict:
    row = _connection(db, user_id)
    if not row:
        return {"connected": False, "email": None,
                "last_synced_at": None, "status": None}
    return {
        "connected": True,
        "email": row["email_address"],
        "last_synced_at": row.get("last_synced_at"),
        "status": row.get("status"),
    }


def access_token_for(db, http, user_id: str) -> str:
    row = _connection(db, user_id)
    if not row:
        raise ConnectionError_("no Gmail connection for this user")
    settings = get_settings()
    resp = http.post(TOKEN_URL, data={
        "refresh_token": decrypt_token(row["refresh_token_enc"]),
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    })
    if resp.status_code >= 400:
        # invalid_grant means the user revoked us at Google. Record that, so the
        # UI can say so instead of silently returning stale stages forever.
        db.update("email_connections", {"user_id": f"eq.{user_id}"},
                  {"status": "revoked"})
        raise ConnectionError_(f"Gmail grant is no longer valid: {resp.text}")
    return resp.json()["access_token"]
