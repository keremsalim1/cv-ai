import base64
import json
from pathlib import Path

from app.main import app
from app.services.browser import get_driver_factory
from tests.conftest import SAMPLE_CV_JSON
from tests.fake_browser import FakeDriver

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _use_driver(driver: FakeDriver):
    app.dependency_overrides[get_driver_factory] = lambda: (lambda headed: driver)
    return driver


ANSWERS = [
    {"field_id": "full_name", "value": "Ada Lovelace"},
    {"field_id": "email", "value": "ada@example.com"},
    {"field_id": "motivation", "value": "I love APIs."},
    {"field_id": "experience", "value": "3-5"},
    {"field_id": "permit", "value": "Yes"},
    {"field_id": "kvkk", "value": "yes"},
]


def test_submit_fills_and_submits(client, auth_headers):
    driver = _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en", "answers": ANSWERS,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "submitted"
    assert base64.b64decode(body["screenshot"]).startswith(b"\x89PNG")
    filled = dict(driver.fills)
    assert any("full_name" in sel or "input[1]" in sel for sel in filled)
    assert ("I love APIs." in filled.values())
    assert driver.selects and driver.selects[0][1] == "3-5"
    # radio "Yes" + checkbox + submit button all clicked
    assert len(driver.clicks) >= 3
    # the ATS PDF was attached to the file field
    assert driver.files and driver.files[0][1].endswith(".pdf")
    assert driver.closed is True


def test_submit_captcha_stops(client, auth_headers):
    _use_driver(FakeDriver([_html("captcha_page.html")]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "tr", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "captcha"
    assert r.json().get("screenshot") is None


def test_submit_form_gone_fails(client, auth_headers):
    _use_driver(FakeDriver(["<html><body><p>gone</p></body></html>"]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "tr", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
