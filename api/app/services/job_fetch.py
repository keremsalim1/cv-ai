import httpx
import trafilatura

from app.schemas import JobCriteria
from app.services.llm import MODEL_FAST, LLMClient

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SYSTEM = (
    "You extract job posting criteria. Respond ONLY with JSON: "
    '{"title": str|null, "company": str|null, "requirements": [str], "skills": [str]}. '
    "requirements = qualifications/experience asked for; skills = concrete tools/technologies. "
    "If the text is not a job posting (login wall, cookie notice, error page), return null title."
)


def fetch_job_text(url: str) -> str | None:
    try:
        resp = httpx.get(url, headers={"User-Agent": UA},
                         follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return None
        text = trafilatura.extract(resp.text)
        return text if text and len(text) > 100 else None
    except httpx.HTTPError:
        return None


def extract_criteria(text: str, llm: LLMClient) -> JobCriteria:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, JobCriteria)
