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
    filled = {sel: val for sel, val, _frame in driver.fills}
    # the full-name input is targeted by its id (<input id="fn" name="full_name">)
    assert filled['//*[@id="fn"]'] == "Ada Lovelace"
    assert ("I love APIs." in filled.values())
    assert driver.selects and driver.selects[0][1] == "3-5"
    # radio "Yes" + submit button clicked
    assert len(driver.clicks) >= 2
    # kvkk checkbox set to checked via idempotent set_checked (not a blind click)
    assert driver.checks and driver.checks[0][1] is True
    # the ATS PDF was attached to the file field
    assert driver.files and driver.files[0][1].endswith(".pdf")
    assert driver.closed is True


def test_submit_skips_one_unfillable_field(client, auth_headers):
    # a select_by_label that raises (option not on the live page) must not abort
    # the whole submission — the remaining fields still fill and submit happens.
    class FlakyDriver(FakeDriver):
        def select_by_label(self, xpath, label):
            raise RuntimeError("option not found")

    _use_driver(FlakyDriver([_html("greenhouse_like.html")]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "en", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"


def test_submit_browser_launch_failure_returns_failed(client, auth_headers):
    # make_driver raising must be a clean "failed", not a 500, and must not
    # leak the temp PDF (finally still runs).
    def boom(headed):
        raise RuntimeError("profile locked")

    app.dependency_overrides[get_driver_factory] = lambda: boom
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "en", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


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
