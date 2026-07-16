from app.schemas import CVData
from app.services.llm import MODEL_FAST, LLMClient

SYSTEM = (
    "You are a CV parser. Extract structured data from the CV text. "
    "Respond ONLY with JSON matching this schema: "
    '{"full_name": str, "title": str|null, "email": str|null, "phone": str|null, '
    '"location": str|null, "summary": str|null, '
    '"experiences": [{"title": str, "company": str, "start_date": str|null, '
    '"end_date": str|null, "description": str|null}], '
    '"education": [{"degree": str|null, "school": str, "year": str|null}], '
    '"skills": [str], "languages": [str], "certifications": [str]}. '
    '"title" is the professional headline shown under the name, if any. '
    "Keep the CV's original language. Do not invent information."
)


def parse_cv(text: str, llm: LLMClient) -> CVData:
    return llm.chat_json(MODEL_FAST, SYSTEM, text, CVData)
