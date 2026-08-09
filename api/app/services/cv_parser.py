from app.schemas import CVData
from app.services.llm import MODEL_FAST, LLMClient

SYSTEM = (
    "You are a CV parser. Extract structured data from the CV text. "
    "Respond ONLY with JSON matching this schema: "
    '{"full_name": str, "title": str|null, "email": str|null, "phone": str|null, '
    '"location": str|null, "linkedin": str|null, "github": str|null, '
    '"website": str|null, "summary": str|null, '
    '"experiences": [{"title": str, "company": str, "location": str|null, '
    '"start_date": str|null, "end_date": str|null, "description": str|null, '
    '"bullets": [str]}], '
    '"education": [{"degree": str|null, "school": str, "location": str|null, '
    '"start_date": str|null, "year": str|null, "details": [str]}], '
    '"projects": [{"name": str, "kind": str|null, "technologies": [str], '
    '"bullets": [str]}], '
    '"skills": [str], "achievements": [str], "languages": [str], '
    '"certifications": [{"name": str, "issuer": str|null, "date": str|null}]}. '
    '"title" is the professional headline shown under the name, if any. '
    "linkedin/github/website are the person's profile URLs wherever they appear "
    "(header, contact block, or a hyperlink); keep them as full URLs. "
    '"website" is a personal site or portfolio. '
    "experiences[].bullets: one entry per bullet the CV lists under that role; "
    "leave it empty and use description when the CV writes a paragraph instead. "
    'projects[].kind: "academic", "personal", "freelance" or "professional", only '
    "when the CV makes it clear; null otherwise. Never upgrade a project's kind. "
    "education[].details: GPA, honours, scholarship or thesis, when stated. "
    "achievements: awards, competitions, volunteering and activities that are not "
    "jobs, projects or certificates. "
    "Keep the CV's original language. Do not invent information."
)


def parse_cv(text: str, llm: LLMClient) -> CVData:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, CVData)
