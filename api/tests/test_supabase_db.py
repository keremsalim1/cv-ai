import httpx
import pytest

from app.services.supabase_db import SupabaseDB


def make_db(handler) -> SupabaseDB:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseDB(client, "https://proj.supabase.co", "service-key")


def test_select_sends_the_service_key_and_returns_rows():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["apikey"] = request.headers["apikey"]
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=[{"id": "a1"}])

    rows = make_db(handler).select("applications", {"user_id": "eq.u1", "select": "*"})

    assert rows == [{"id": "a1"}]
    assert seen["path"] == "/rest/v1/applications"
    assert seen["params"] == {"user_id": "eq.u1", "select": "*"}
    assert seen["apikey"] == "service-key"
    assert seen["auth"] == "Bearer service-key"


def test_insert_returns_the_created_row():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Prefer"] == "return=representation"
        return httpx.Response(201, json=[{"id": "new"}])

    assert make_db(handler).insert("applications", {"url": "x"}) == {"id": "new"}


def test_insert_with_on_conflict_returns_none_when_the_row_already_existed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["on_conflict"] == "user_id,message_id"
        assert "resolution=ignore-duplicates" in request.headers["Prefer"]
        return httpx.Response(201, json=[])   # PostgREST returns [] on ignore

    result = make_db(handler).insert(
        "application_events", {"message_id": "m1"}, on_conflict="user_id,message_id"
    )
    assert result is None


def test_update_returns_the_patched_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(200, json=[{"id": "a1", "stage": "rejected"}])

    rows = make_db(handler).update(
        "applications", {"id": "eq.a1"}, {"stage": "rejected"}
    )
    assert rows == [{"id": "a1", "stage": "rejected"}]


def test_an_error_response_raises_with_the_body_visible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "column does not exist"})

    with pytest.raises(RuntimeError, match="column does not exist"):
        make_db(handler).select("applications", {})


def test_empty_response_body_returns_empty_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)  # No body, like DELETE without Prefer: return=representation

    rows = make_db(handler).select("applications", {})
    assert rows == []


def test_bare_object_response_is_wrapped_in_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x"})

    rows = make_db(handler).select("applications", {})
    assert rows == [{"id": "x"}]


def test_delete_sends_delete_request_with_params():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert dict(request.url.params) == {"id": "eq.a1"}
        return httpx.Response(204)

    make_db(handler).delete("applications", {"id": "eq.a1"})
