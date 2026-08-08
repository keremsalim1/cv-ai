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


import httpx

from app.services.inbox_connect import (
    ConnectionError_, access_token_for, connect_gmail, connection_status,
    disconnect_gmail,
)


class FakeDB:
    """Records writes; serves whatever rows the test seeded.

    Mirrors the real SupabaseDB's safety contract: the service-role client
    bypasses RLS, so every select/update/delete must filter on user_id. This
    fake refuses (via AssertionError) any call that omits that filter, and
    only matches rows belonging to the filtered user_id — so a caller that
    forgets the filter fails a test here instead of leaking another user's
    row in production.
    """

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict, dict]] = []
        self.deleted: list[tuple[str, dict]] = []

    @staticmethod
    def _user_id(params):
        value = params.get("user_id")
        assert value, "query must filter on user_id"
        assert value.startswith("eq."), "user_id filter must be an eq. filter"
        return value[len("eq."):]

    def select(self, table, params):
        user_id = self._user_id(params)
        return [r for r in self.rows if r.get("user_id") == user_id]

    def insert(self, table, row, *, on_conflict=None):
        self.inserted.append((table, row))
        self.rows.append(row)
        return row

    def update(self, table, params, patch):
        user_id = self._user_id(params)
        self.updated.append((table, params, patch))
        matched = [r for r in self.rows if r.get("user_id") == user_id]
        for r in matched:
            r.update(patch)
        return matched

    def delete(self, table, params):
        user_id = self._user_id(params)
        self.deleted.append((table, params))
        self.rows = [r for r in self.rows if r.get("user_id") != user_id]


def http_returning(*responses):
    queue = list(responses)
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_connecting_stores_an_encrypted_token_and_the_address(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    from app.config import get_settings
    get_settings.cache_clear()

    db = FakeDB()
    http = http_returning(
        (200, {"access_token": "at", "refresh_token": "1//rt"}),
        (200, {"emailAddress": "ada@example.com", "historyId": "9001"}),
    )

    result = connect_gmail(db, http, "u1", code="auth-code",
                           redirect_uri="http://localhost:3000/auth/gmail/callback")

    assert result == {"connected": True, "email": "ada@example.com"}
    table, row = db.inserted[0]
    assert table == "email_connections"
    assert row["user_id"] == "u1"
    assert row["email_address"] == "ada@example.com"
    assert row["last_history_id"] == "9001"
    assert "1//rt" not in row["refresh_token_enc"]   # stored encrypted
    get_settings.cache_clear()


def test_connecting_without_a_refresh_token_is_an_error_not_a_half_connection():
    # Google omits refresh_token when the user already granted consent and we
    # forgot prompt=consent. Storing nothing is better than storing a dead row.
    db = FakeDB()
    http = http_returning((200, {"access_token": "at"}))
    with pytest.raises(ConnectionError_, match="refresh token"):
        connect_gmail(db, http, "u1", code="c", redirect_uri="r")
    assert db.inserted == []


def test_status_reports_a_missing_connection_without_raising():
    assert connection_status(FakeDB(), "u1") == {
        "connected": False, "email": None, "last_synced_at": None, "status": None,
    }


def test_status_reports_an_existing_connection():
    db = FakeDB([{"user_id": "u1", "email_address": "ada@example.com",
                  "last_synced_at": "2026-07-27T10:00:00Z", "status": "active"}])
    assert connection_status(db, "u1") == {
        "connected": True, "email": "ada@example.com",
        "last_synced_at": "2026-07-27T10:00:00Z", "status": "active",
    }


def test_reconnecting_replaces_an_existing_connection_without_ever_deleting_it(monkeypatch):
    # connect_gmail must never delete-then-insert: if the insert failed after
    # a successful delete, the user would be left with a dead connection and
    # nothing to show for it. user_id is the table's primary key, so an
    # existing row must be updated in place instead.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    from app.config import get_settings
    get_settings.cache_clear()

    db = FakeDB([{"user_id": "u1", "provider": "gmail",
                  "email_address": "old@example.com",
                  "refresh_token_enc": encrypt_token("1//old-rt"),
                  "last_history_id": "1", "status": "active"}])
    http = http_returning(
        (200, {"access_token": "at", "refresh_token": "1//new-rt"}),
        (200, {"emailAddress": "new@example.com", "historyId": "9002"}),
    )

    result = connect_gmail(db, http, "u1", code="auth-code",
                           redirect_uri="http://localhost:3000/auth/gmail/callback")

    assert result == {"connected": True, "email": "new@example.com"}
    assert db.inserted == []          # replaced in place, not re-inserted
    assert db.deleted == []           # never deleted, not even transiently
    assert len(db.rows) == 1          # never zero rows, never duplicated
    assert db.rows[0]["email_address"] == "new@example.com"
    assert db.rows[0]["last_history_id"] == "9002"
    assert "1//new-rt" not in db.rows[0]["refresh_token_enc"]
    get_settings.cache_clear()


def test_disconnecting_revokes_at_google_before_deleting_the_row():
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt")}])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    disconnect_gmail(db, httpx.Client(transport=httpx.MockTransport(handler)), "u1")

    assert any("oauth2.googleapis.com/revoke" in c for c in calls)
    assert db.deleted == [("email_connections", {"user_id": "eq.u1"})]


def test_disconnecting_deletes_the_row_even_if_google_refuses_the_revoke():
    # A grant the user already revoked at Google returns 400. Leaving our row
    # behind would show a connection that cannot work.
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt")}])
    http = http_returning((400, {"error": "invalid_token"}))
    disconnect_gmail(db, http, "u1")
    assert db.deleted


def test_a_revoked_grant_marks_the_connection_and_raises():
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt"),
                  "status": "active"}])
    http = http_returning((400, {"error": "invalid_grant"}))

    with pytest.raises(ConnectionError_):
        access_token_for(db, http, "u1")

    assert db.updated[0][2] == {"status": "revoked"}


def test_a_transient_google_error_does_not_mark_the_connection_revoked():
    # A 503 (or any error that isn't invalid_grant) is Google having a bad
    # moment, not proof the user revoked us. Marking the connection revoked
    # here would force a needless re-consent on a real, working connection.
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt"),
                  "status": "active"}])
    http = http_returning((503, {"error": "backend_error"}))

    with pytest.raises(ConnectionError_):
        access_token_for(db, http, "u1")

    assert db.updated == []


def test_an_undecryptable_stored_token_raises_connection_error_not_token_error():
    # Every caller of access_token_for catches ConnectionError_ to mean
    # "reconnect needed". A bare TokenError would surface as an unhandled
    # 500 instead of that explanation.
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": "not-a-valid-fernet-token"}])
    http = http_returning((200, {"access_token": "fresh-at"}))
    with pytest.raises(ConnectionError_):
        access_token_for(db, http, "u1")


def test_an_access_token_is_minted_from_the_stored_refresh_token():
    db = FakeDB([{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt")}])
    http = http_returning((200, {"access_token": "fresh-at"}))
    assert access_token_for(db, http, "u1") == "fresh-at"
