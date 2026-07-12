from pydantic import BaseModel, Field

from app.schemas import CVData, EvaluationResult, JobCriteria, stars_from_percent
from app.services.llm import MODEL_SMART, LLMClient

SYSTEM = (
    "You score how well a CV fits a job posting. Use this fixed rubric: "
    "skills match 40%, experience relevance 35%, education/other 25%. "
    "Respond ONLY with JSON: "
    '{"percent": int 0-100, "strengths": [str], "gaps": [str], "suggestions": [str]}. '
    "strengths = where the CV matches the criteria; gaps = missing criteria; "
    "suggestions = concrete CV improvements. "
    "Write strengths/gaps/suggestions in the CV's language."
)


class _ScoreOut(BaseModel):
    percent: int = Field(ge=0, le=100)
    strengths: list[str] = []
    gaps: list[str] = []
    suggestions: list[str] = []


def score_cv(cv: CVData, job: JobCriteria, llm: LLMClient) -> EvaluationResult:
    user = f"CV:\n{cv.model_dump_json()}\n\nJOB POSTING:\n{job.model_dump_json()}"
    out = llm.chat_json(MODEL_SMART, SYSTEM, user, _ScoreOut)
    return EvaluationResult(
        percent=out.percent,
        stars=stars_from_percent(out.percent),
        strengths=out.strengths,
        gaps=out.gaps,
        suggestions=out.suggestions,
    )
