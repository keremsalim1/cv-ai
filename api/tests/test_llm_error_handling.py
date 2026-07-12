import json

from tests.conftest import SAMPLE_CV_JSON, override_llm

JOB = {"title": "Dev", "company": None, "requirements": [], "skills": []}


def test_llm_failure_returns_502(client, auth_headers):
    override_llm(["broken", "still broken"])  # both attempts invalid
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "AI_UNAVAILABLE"


def test_cors_preflight(client):
    r = client.options("/score", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
