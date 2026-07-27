"""Gmail connection lifecycle: OAuth exchange, token storage, revocation."""
import logging

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
