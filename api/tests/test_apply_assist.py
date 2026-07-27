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

# What the collector reports for FORM_HTML. The second entry is the page as it
# looks AFTER filling, which is what the verification probe reads.
FORM_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "textarea", "role": "textbox",
     "name": "motivation", "label_text": "Motivation"},
    {"ref": "0-2", "frame": 0, "tag": "input", "type": "email", "role": "textbox",
     "name": "email", "label_text": "Email"},
]
FORM_INVENTORY_AFTER = [
    {**FORM_INVENTORY[0], "value": "I love APIs."},
    {**FORM_INVENTORY[1], "value": ""},
]


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
    _use_session(FakeDriver([FORM_HTML], evaluations=[FORM_INVENTORY]))
    sid = _start(client, auth_headers)
    assert sid
    assert sid in session_manager._sessions


def test_assist_fill_fills_and_charges_one_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([FORM_HTML],
                            evaluations=[FORM_INVENTORY, FORM_INVENTORY_AFTER]))
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


LINKS_HTML = (
    "<html><body><h1>Apply</h1><form>"
    "<label>LinkedIn URL<input name='linkedin' id='li'></label>"
    "<label>GitHub URL<input name='github' id='gh'></label>"
    "<label>Portfolio URL<input name='portfolio' id='pf'></label>"
    "<button type='submit'>Send</button></form></body></html>"
)
LINKS_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "input", "role": "textbox",
     "name": "linkedin", "label_text": "LinkedIn URL"},
    {"ref": "0-2", "frame": 0, "tag": "input", "role": "textbox",
     "name": "github", "label_text": "GitHub URL"},
    {"ref": "0-3", "frame": 0, "tag": "input", "role": "textbox",
     "name": "portfolio", "label_text": "Portfolio URL"},
]
LINKS_INVENTORY_AFTER = [
    {**LINKS_INVENTORY[0], "value": "https://linkedin.com/in/ada"},
    {**LINKS_INVENTORY[1], "value": "https://github.com/ada"},
    {**LINKS_INVENTORY[2], "value": "https://ada.dev"},
]


def test_assist_fill_answers_profile_link_fields_from_the_cv(client, auth_headers):
    # Lever/Greenhouse ask for these on nearly every form; they must come
    # straight from the CV instead of being left blank for the user.
    driver = FakeDriver([LINKS_HTML],
                        evaluations=[LINKS_INVENTORY, LINKS_INVENTORY_AFTER])
    _use_session(driver)
    fake = override_llm([json.dumps({"answers": [
        {"field_id": "linkedin", "value": "https://linkedin.com/in/ada"},
        {"field_id": "github", "value": "https://github.com/ada"},
        {"field_id": "portfolio", "value": "https://ada.dev"},
    ]})])
    cv = json.loads(SAMPLE_CV_JSON)
    cv["linkedin"] = "https://linkedin.com/in/ada"
    cv["github"] = "https://github.com/ada"
    cv["website"] = "https://ada.dev"
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": cv, "language": "en"})
    assert r.status_code == 200
    filled = {sel: val for sel, val, _frame in driver.fills}
    assert filled['[data-cvai-ref="0-1"]'] == "https://linkedin.com/in/ada"
    assert filled['[data-cvai-ref="0-2"]'] == "https://github.com/ada"
    assert filled['[data-cvai-ref="0-3"]'] == "https://ada.dev"
    # the links must actually reach the model, not just the form
    sent = json.loads(fake.calls[0]["messages"][1]["content"])
    assert sent["cv"]["linkedin"] == "https://linkedin.com/in/ada"
    assert sent["cv"]["github"] == "https://github.com/ada"
    assert sent["cv"]["website"] == "https://ada.dev"


def test_assist_fill_survives_a_locked_temp_pdf(client, auth_headers, monkeypatch):
    # The assisted browser stays open and keeps the uploaded PDF locked (Windows),
    # so deleting it right after the fill fails. A successful fill must still be
    # reported as filled instead of surfacing as an unexpected error.
    import app.services.apply as apply_mod

    def locked(self, missing_ok=False):
        raise PermissionError(32, "file in use by another process")

    monkeypatch.setattr(apply_mod.Path, "unlink", locked)
    _use_session(FakeDriver([FORM_HTML],
                            evaluations=[FORM_INVENTORY, FORM_INVENTORY_AFTER]))
    override_llm([ASSIST_OUT])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    assert r.json()["status"] == "filled"


def test_assist_fill_no_form_costs_no_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([NO_FORM_HTML], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.json()["status"] == "no_form"
    assert sum(usage_store._counts.values()) == 0


COUNTRY_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "input", "role": "textbox",
     "name": "motivation", "label_text": "Motivation"},
    {"ref": "0-2", "frame": 0, "tag": "div", "role": "combobox",
     "name": "country", "label_text": "Country"},
]


def test_assist_fill_reports_the_fields_it_could_not_fill(client, auth_headers):
    """A partial fill is normal with custom widgets, and staying silent about it
    is what made the tool claim success it had not earned."""
    # the combobox opens but its popup never offers "Türkiye", so the option
    # lookup finds nothing and the field is reported back to the user
    driver = FakeDriver([FORM_HTML], evaluations=[
        COUNTRY_INVENTORY,      # discovery
        [],                     # the popup after clicking the combobox
        # verification: the textbox took its value, the combobox is untouched
        [{**COUNTRY_INVENTORY[0], "value": "I love APIs."}, COUNTRY_INVENTORY[1]],
    ])
    _use_session(driver)
    override_llm([json.dumps({"answers": [
        {"field_id": "motivation", "value": "I love APIs."},
        {"field_id": "country", "value": "Türkiye"},
    ]})])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "filled"
    assert [f["label"] for f in body["unfilled"]] == ["Country"]


def test_assist_fill_says_why_it_found_no_form(client, auth_headers):
    _use_session(FakeDriver([NO_FORM_HTML], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    body = r.json()
    assert body["status"] == "no_form"
    assert body["reason"] == "no_controls"


def test_a_browser_the_user_closed_is_reported_not_raised(client, auth_headers):
    """The probe already tolerates a page that is gone; the reason lookup right
    after it must not turn the same failure into a 500."""
    class DeadDriver(FakeDriver):
        def content(self):
            raise RuntimeError(
                "Page.content: Target page, context or browser has been closed")

    _use_session(DeadDriver([NO_FORM_HTML], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_form"
    assert body["reason"] == "browser_closed"


def test_assist_fill_names_a_login_wall_as_the_reason(client, auth_headers):
    login_html = "<html><body><form><input type='password'></form></body></html>"
    _use_session(FakeDriver([login_html], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.json()["reason"] == "login_wall"


def test_a_registered_platform_overrides_the_generic_scope(client, auth_headers,
                                                           monkeypatch):
    import app.services.platforms as platforms_mod
    monkeypatch.setattr(platforms_mod, "REGISTRY", (platforms_mod.Platform(
        name="test", hosts=("jobs.example.com",), scope_landmark="main"),))
    # generic rules would scope to the dialog; the platform pins main
    inventory = [
        {"ref": "0-1", "frame": 0, "role": "textbox", "name": "consent",
         "label_text": "Cookie consent", "landmark": "dialog"},
        {"ref": "0-2", "frame": 0, "role": "textbox", "name": "motivation",
         "label_text": "Motivation", "landmark": "main"},
    ]
    _use_session(FakeDriver([FORM_HTML], evaluations=[
        inventory,
        [{**inventory[0]}, {**inventory[1], "value": "I love APIs."}],
    ]))
    override_llm([json.dumps({"answers": [
        {"field_id": "motivation", "value": "I love APIs."}]})])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.json()["field_count"] == 1


def test_assist_fill_rejects_other_users_session(client, auth_headers):
    _use_session(FakeDriver([FORM_HTML], evaluations=[FORM_INVENTORY]))
    sid = _start(client, auth_headers)
    other = {"Authorization": f"Bearer {make_token('user-2')}"}
    r = client.post("/apply/assist/fill", headers=other,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 403


def test_assist_close_removes_the_session(client, auth_headers):
    session = _use_session(FakeDriver([FORM_HTML], evaluations=[FORM_INVENTORY]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/close", headers=auth_headers, json={"session_id": sid})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert session.closed is True
    assert sid not in session_manager._sessions
