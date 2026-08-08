import logging

import httpx
import trafilatura

from app.schemas import JobCriteria
from app.services.llm import MODEL_FAST, LLMClient

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Below this a page is a cookie banner or an auth wall, not a posting.
MIN_TEXT = 100

SYSTEM = (
    "You extract job posting criteria. Respond ONLY with JSON: "
    '{"title": str|null, "company": str|null, "requirements": [str], "skills": [str]}. '
    "requirements = qualifications/experience asked for; skills = concrete tools/technologies. "
    "If the text is not a job posting (login wall, cookie notice, error page), return null title."
)


def fetch_job_text(url: str) -> str | None:
    # Every path out of here is the same None to the caller, so the reason has
    # to be said out loud. A posting that will not load is reported by a user
    # hours later; the log is the only thing that still remembers why.
    try:
        resp = httpx.get(url, headers={"User-Agent": UA},
                         follow_redirects=True, timeout=15)
    except httpx.HTTPError as exc:
        logger.warning("[job] %s unreachable: %s", url, exc)
        return None
    if resp.status_code != 200:
        logger.warning("[job] %s refused the request: HTTP %d",
                       url, resp.status_code)
        return None
    text = trafilatura.extract(resp.text)
    if not text:
        logger.warning("[job] %s carried no text to extract (%d bytes of HTML)",
                       url, len(resp.text))
        return None
    if len(text) <= MIN_TEXT:
        logger.warning("[job] %s yielded only %d characters, under the %d needed",
                       url, len(text), MIN_TEXT)
        return None
    return text


def extract_criteria(text: str, llm: LLMClient) -> JobCriteria:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, JobCriteria)
