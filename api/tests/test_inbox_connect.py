import pytest
from cryptography.fernet import Fernet

from app.services.inbox_connect import TokenError, decrypt_token, encrypt_token


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


def test_a_token_survives_a_round_trip():
    assert decrypt_token(encrypt_token("1//refresh-abc")) == "1//refresh-abc"


def test_the_ciphertext_does_not_contain_the_token():
    assert "refresh-abc" not in encrypt_token("1//refresh-abc")


def test_two_encryptions_of_the_same_token_differ():
    # Fernet embeds a random IV; identical ciphertexts would leak equality
    assert encrypt_token("same") != encrypt_token("same")


def test_a_tampered_blob_is_refused_rather_than_returning_garbage():
    blob = encrypt_token("1//refresh-abc")
    tampered = blob[:-4] + ("aaaa" if not blob.endswith("aaaa") else "bbbb")
    with pytest.raises(TokenError):
        decrypt_token(tampered)


def test_a_missing_key_is_a_clear_error_not_a_crash(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", "")
    with pytest.raises(TokenError, match="EMAIL_TOKEN_KEY"):
        encrypt_token("anything")
    get_settings.cache_clear()
