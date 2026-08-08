import pytest

from app.main import app
from app.services.inbox_connect import ConnectionError_
from app.services.inbox_sync import SyncReport
from app.services.supabase_db import get_db
from tests.test_inbox_sync import InboxDB


def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    return db


def test_status_requires_authentication(client):
    assert client.get("/inbox/status").status_code == 401


def test_status_reports_a_disconnected_mailbox(client, auth_headers):
    override_db(InboxDB())
    resp = client.get("/inbox/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "email": None,
                           "last_synced_at": None, "status": None}


def test_sync_returns_what_changed_for_the_authenticated_user(client, auth_headers,
                                                              monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    seen = {}

    def fake_sync(db, http, llm, user_id, **kwargs):
        seen["user_id"] = user_id
        return SyncReport(scanned=3, classified=2, created=1,
                          updated=[{"application_id": "a1"}], partial=False)

    monkeypatch.setattr(router_mod, "sync_user_inbox", fake_sync)

    resp = client.post("/inbox/sync", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"scanned": 3, "classified": 2, "created": 1,
                           "updated": [{"application_id": "a1"}], "partial": False}
    assert seen["user_id"] == "user-1"


def test_a_revoked_grant_is_a_named_error_the_ui_can_translate(client, auth_headers,
                                                               monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod

    def boom(*a, **k):
        raise ConnectionError_("gone")

    monkeypatch.setattr(router_mod, "sync_user_inbox", boom)
    resp = client.post("/inbox/sync", headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "GMAIL_DISCONNECTED"}


def test_googles_response_body_never_reaches_the_client(client, auth_headers,
                                                        monkeypatch):
    # ConnectionError_ messages embed Google's raw reply, which can name the
    # grant and the client id. The UI gets a code; the detail stays in the log.
    override_db(InboxDB())
    import app.routers.inbox as router_mod

    def boom(*a, **k):
        raise ConnectionError_(
            'Gmail grant is no longer valid: {"error":"invalid_grant",'
            '"client_id":"1234-secret.apps.googleusercontent.com"}')

    monkeypatch.setattr(router_mod, "sync_user_inbox", boom)
    resp = client.post("/inbox/sync", headers=auth_headers)

    assert "invalid_grant" not in resp.text
    assert "googleusercontent" not in resp.text


def test_connect_passes_the_code_and_redirect_through(client, auth_headers,
                                                      monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    seen = {}

    def fake_connect(db, http, user_id, code, redirect_uri):
        seen.update(user_id=user_id, code=code, redirect_uri=redirect_uri)
        return {"connected": True, "email": "ada@example.com"}

    monkeypatch.setattr(router_mod, "connect_gmail", fake_connect)
    resp = client.post("/inbox/connect", headers=auth_headers,
                       json={"code": "abc", "redirect_uri": "http://localhost:3000/cb"})

    assert resp.status_code == 200
    assert resp.json() == {"connected": True, "email": "ada@example.com"}
    assert seen["code"] == "abc"
    assert seen["redirect_uri"] == "http://localhost:3000/cb"
    assert seen["user_id"] == "user-1"


def test_a_refused_authorization_code_is_reported_as_such(client, auth_headers,
                                                          monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod

    def boom(*a, **k):
        raise ConnectionError_("no refresh token")

    monkeypatch.setattr(router_mod, "connect_gmail", boom)
    resp = client.post("/inbox/connect", headers=auth_headers,
                       json={"code": "abc", "redirect_uri": "http://x"})

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "GMAIL_DISCONNECTED"}


def test_connect_rejects_a_body_without_a_code(client, auth_headers):
    override_db(InboxDB())
    assert client.post("/inbox/connect", headers=auth_headers,
                       json={"redirect_uri": "http://x"}).status_code == 422


def test_disconnect_removes_the_connection(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    called = []
    monkeypatch.setattr(router_mod, "disconnect_gmail",
                        lambda db, http, user_id: called.append(user_id))

    assert client.delete("/inbox/connect", headers=auth_headers).status_code == 200
    assert called == ["user-1"]


def test_the_request_http_client_is_closed_when_the_request_ends():
    # One client per request is fine; one leaked socket pool per request is not.
    from app.routers.inbox import get_http

    gen = get_http()
    http = next(gen)
    assert not http.is_closed
    with pytest.raises(StopIteration):
        next(gen)
    assert http.is_closed


def test_the_database_http_client_is_closed_when_the_request_ends():
    gen = get_db()
    db = next(gen)
    assert not db._client.is_closed
    with pytest.raises(StopIteration):
        next(gen)
    assert db._client.is_closed
