import json

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
