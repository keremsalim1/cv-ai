import json

import pytest

from app.main import app
from app.services.session import get_session_factory, session_manager
from tests.conftest import SAMPLE_CV_JSON, make_token, override_llm
from tests.fake_browser import FakeDriver
from tests.fake_session import FakeSession

FORM_HTML = (
    "<html><body><h1>Apply</h1>"
    "<form><label>Motivation<textarea name='motivation'></textarea></label>"
    "<label>Email<input type='email' name='email'></label>"
    "<button type='submit'>Send</button></form></body></html>"
)
NO_FORM_HTML = "<html><body><h1>Step 1</h1><p>Choose a method to continue.</p></body></html>"
ASSIST_OUT = json.dumps({"answers": [{"field_id": "motivation", "value": "I love APIs."}]})


@pytest.fixture(autouse=True)
def _clear_sessions():
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def _use_session(driver: FakeDriver):
    session = FakeSession(driver)
    app.dependency_overrides[get_session_factory] = lambda: (lambda url: session)
    return session


def _start(client, auth_headers) -> str:
    r = client.post("/apply/assist/start", headers=auth_headers,
                    json={"url": "https://jobs.siemens.com/x"})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_assist_start_opens_a_session(client, auth_headers):
    _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    assert sid
    assert sid in session_manager._sessions


def test_assist_fill_fills_and_charges_one_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([FORM_HTML]))
    override_llm([ASSIST_OUT])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "filled"
    assert body["field_count"] >= 2
    assert body["screenshot"]
    assert sum(usage_store._counts.values()) == 1


def test_assist_fill_no_form_costs_no_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([NO_FORM_HTML]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.json()["status"] == "no_form"
    assert sum(usage_store._counts.values()) == 0


def test_assist_fill_rejects_other_users_session(client, auth_headers):
    _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    other = {"Authorization": f"Bearer {make_token('user-2')}"}
    r = client.post("/apply/assist/fill", headers=other,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 403


def test_assist_close_removes_the_session(client, auth_headers):
    session = _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/close", headers=auth_headers, json={"session_id": sid})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert session.closed is True
    assert sid not in session_manager._sessions
