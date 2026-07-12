from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas import CVData, EvaluationResult, JobCriteria
from app.services.llm import LLMClient, get_llm
from app.services.scorer import score_cv
from app.services.usage import check_usage

router = APIRouter(tags=["score"])


class ScoreRequest(BaseModel):
    cv: CVData
    job: JobCriteria


@router.post("/score", response_model=EvaluationResult)
def score(
    req: ScoreRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    return score_cv(req.cv, req.job, llm)
