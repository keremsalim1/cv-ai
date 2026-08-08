import json
import logging

import httpx

from app.services import job_fetch
from tests.conftest import override_llm

CRITERIA_JSON = json.dumps({
    "title": "Backend Developer",
    "company": "Acme",
    "requirements": ["3+ years Python", "REST API design"],
    "skills": ["Python", "FastAPI", "PostgreSQL"],
})


def test_fetch_from_url(client, auth_headers, monkeypatch):
    monkeypatch.setattr(job_fetch, "fetch_job_text",
                        lambda url: "We are hiring a Backend Developer...")
    override_llm([CRITERIA_JSON])
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"url": "https://example.com/job/1"})
    assert r.status_code == 200
    body = r.json()
    assert body["fetch_method"] == "url"
    assert body["criteria"]["title"] == "Backend Developer"


def test_fetch_failure_returns_code(client, auth_headers, monkeypatch):
    monkeypatch.setattr(job_fetch, "fetch_job_text", lambda url: None)
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"url": "https://linkedin.com/jobs/1"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "FETCH_FAILED"


def test_manual_text(client, auth_headers):
    override_llm([CRITERIA_JSON])
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"text": "We are hiring a Backend Developer..."})
    assert r.status_code == 200
    assert r.json()["fetch_method"] == "manual"


def test_no_input(client, auth_headers):
    r = client.post("/job/fetch", headers=auth_headers, json={})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NO_INPUT"


# fetch_job_text collapses four different failures into one silent None. When a
# posting will not load, the log is the only place that can say which one it was
# — without it the next report is as undiagnosable as the last.
class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_refused_page_logs_its_status(monkeypatch, caplog):
    monkeypatch.setattr(job_fetch.httpx, "get", lambda *a, **k: _Resp(403, ""))
    with caplog.at_level(logging.WARNING):
        assert job_fetch.fetch_job_text("https://linkedin.com/jobs/1") is None
    assert "403" in caplog.text


def test_page_with_nothing_to_extract_says_so(monkeypatch, caplog):
    monkeypatch.setattr(job_fetch.httpx, "get", lambda *a, **k: _Resp(200, "<html></html>"))
    monkeypatch.setattr(job_fetch.trafilatura, "extract", lambda html: None)
    with caplog.at_level(logging.WARNING):
        assert job_fetch.fetch_job_text("https://example.com/j") is None
    assert "no text" in caplog.text.lower()


def test_thin_page_logs_how_thin(monkeypatch, caplog):
    monkeypatch.setattr(job_fetch.httpx, "get", lambda *a, **k: _Resp(200, "<html>x</html>"))
    monkeypatch.setattr(job_fetch.trafilatura, "extract", lambda html: "too short")
    with caplog.at_level(logging.WARNING):
        assert job_fetch.fetch_job_text("https://example.com/j") is None
    assert "9" in caplog.text


def test_unreachable_page_logs_the_error(monkeypatch, caplog):
    def timeout(*a, **k):
        raise httpx.ConnectTimeout("connection timed out")

    monkeypatch.setattr(job_fetch.httpx, "get", timeout)
    with caplog.at_level(logging.WARNING):
        assert job_fetch.fetch_job_text("https://example.com/j") is None
    assert "timed out" in caplog.text


def test_unparseable_page_returns_code(client, auth_headers, monkeypatch):
    monkeypatch.setattr(job_fetch, "fetch_job_text",
                        lambda url: "Cookie notice. Accept all cookies to continue.")
    override_llm([json.dumps({
        "title": None, "company": None, "requirements": [], "skills": [],
    })])
    r = client.post("/job/fetch", headers=auth_headers,
                    json={"url": "https://example.com/job/1"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "JOB_PARSE_FAILED"
