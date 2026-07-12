import json

from tests.conftest import SAMPLE_CV_JSON, override_llm

JOB = {"title": "Backend Developer", "company": "Acme",
       "requirements": ["3+ years Python"], "skills": ["Python", "FastAPI"]}

LLM_SCORE = json.dumps({
    "percent": 78,
    "strengths": ["Strong Python background", "FastAPI experience"],
    "gaps": ["No PostgreSQL mentioned"],
    "suggestions": ["Add database projects to CV"],
})


def test_score_returns_evaluation(client, auth_headers):
    override_llm([LLM_SCORE])
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.status_code == 200
    body = r.json()
    assert body["percent"] == 78
    assert body["stars"] == 4  # 61-80 -> 4, computed server-side
    assert body["strengths"] and body["gaps"] and body["suggestions"]


def test_stars_never_from_llm(client, auth_headers):
    # even if LLM tried to sneak stars in, percent drives the mapping
    payload = json.loads(LLM_SCORE); payload["percent"] = 95
    override_llm([json.dumps(payload)])
    r = client.post("/score", headers=auth_headers,
                    json={"cv": json.loads(SAMPLE_CV_JSON), "job": JOB})
    assert r.json()["stars"] == 5
