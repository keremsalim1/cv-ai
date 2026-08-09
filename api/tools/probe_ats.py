"""Run one real ATS rewrite against Gemini and print what came back.

Not a test: it costs a request against DAILY_AI_LIMIT and needs a live key.
Run it once after changing the engine to see whether the model actually obeys
the rules - the unit tests only prove the plumbing.

    cd api && .venv\\Scripts\\python -m tools.probe_ats

The source CV below is deliberately bad: an internship that invites promotion,
filler adjectives, a tool filed as a language, a soft skill among the technical
ones, and a certificate with no issuer or date.
"""
import json

from app.schemas import CVData
from app.services.ats import rewrite_ats
from app.services.llm import get_llm

SOURCE = CVData.model_validate({
    "full_name": "Ada Lovelace",
    "title": None,
    "email": "ada@example.com",
    "location": "London",
    "summary": "Hard-working and passionate developer seeking an opportunity.",
    "experiences": [{
        "title": "Intern", "company": "Analytical Engine Corp",
        "start_date": "2020", "end_date": "2021",
        "description": "Responsible for database operations and reporting.",
    }],
    "education": [{"degree": "BSc Mathematics", "school": "Cambridge", "year": "2019"}],
    "skills": ["Python", "SQL", "Docker", "teamwork"],
    "languages": ["English"],
    "certifications": ["AWS Solutions Architect"],
})

if __name__ == "__main__":
    out = rewrite_ats(SOURCE, "en", get_llm())
    print(json.dumps(out.model_dump(), indent=2, ensure_ascii=False))
