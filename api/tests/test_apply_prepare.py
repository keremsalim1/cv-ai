import json
from pathlib import Path

from app.main import app
from app.services.browser import get_driver_factory
from tests.conftest import SAMPLE_CV_JSON, override_llm
from tests.fake_browser import FakeDriver

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _use_driver(driver: FakeDriver):
    app.dependency_overrides[get_driver_factory] = lambda: (lambda headed: driver)
    return driver


PREPARE_OUT = json.dumps({
    "cv": json.loads(SAMPLE_CV_JSON),
    "changes": ["Reordered skills to match the posting"],
    "cover_letter": "I am excited to apply...",
    "answers": [
        {"field_id": "full_name", "value": "Ada Lovelace"},
        {"field_id": "motivation", "value": "I love building APIs."},
        {"field_id": "experience", "value": "3-5"},
    ],
})


def test_prepare_ready(client, auth_headers):
    driver = _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert any(f["id"] == "motivation" for f in body["form"])
    assert body["answers"][2]["value"] == "3-5"
    assert body["cover_letter"].startswith("I am excited")
    assert "Backend Developer" in body["job_text"]
    assert driver.gotos == ["https://jobs.example.com/1"]
    assert driver.closed is True


def test_prepare_login_required(client, auth_headers):
    _use_driver(FakeDriver([_html("login_wall.html")]))
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "login_required"


def test_prepare_captcha(client, auth_headers):
    _use_driver(FakeDriver([_html("captcha_page.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "captcha"
    # captcha still optimizes so delivery mode has content
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["cover_letter"].startswith("I am excited")
    assert any(f["id"] == "full_name" for f in body["form"])


def test_prepare_form_not_found(client, auth_headers):
    _use_driver(FakeDriver(["<html><body><h1>Job</h1><p>" + "desc " * 60 + "</p></body></html>"]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "form_not_found"
    assert body["form"] == []
    # no form, but the optimized CV + cover letter are still delivered
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["cover_letter"].startswith("I am excited")


def test_prepare_optional_login_delivers(client, auth_headers):
    # Page offers a sign-in but the posting is readable and there is no
    # application form on it (Siemens/Avature-style method chooser). We must
    # optimize and deliver, NOT loop on login_required.
    html = (
        "<html><body><h1>Part-time Student</h1>"
        "<p>" + "We are looking for a motivated student. " * 20 + "</p>"
        "<form action='/login'>"
        "<input type='email' name='u'><input type='password' name='p'>"
        "<button type='submit'>Log in</button></form>"
        "</body></html>"
    )
    _use_driver(FakeDriver([html]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.siemens.com/x",
        "language": "en",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "form_not_found"
    assert body["form"] == []
    # login was optional, so the optimized CV + cover letter are delivered
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["cover_letter"].startswith("I am excited")


def test_prepare_login_required_does_not_consume_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_driver(FakeDriver([_html("login_wall.html")]))
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.json()["status"] == "login_required"
    # no LLM call happened, so the daily counter must stay empty
    assert sum(usage_store._counts.values()) == 0


def test_prepare_ready_consumes_one_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "en",
    })
    assert r.json()["status"] == "ready"
    assert sum(usage_store._counts.values()) == 1


def test_prepare_headed_waits_for_login(client, auth_headers):
    # first snapshot: login wall; second: the real form (user logged in meanwhile)
    driver = _use_driver(FakeDriver([_html("login_wall.html"), _html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "en",
        "headed": True,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert driver.closed is True
