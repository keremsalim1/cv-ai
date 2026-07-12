from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services import job_fetch
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/job", tags=["job"])


class JobFetchRequest(BaseModel):
    url: str | None = None
    text: str | None = None


@router.post("/fetch")
def fetch(
    req: JobFetchRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    if req.text:
        description, method = req.text, "manual"
    elif req.url:
        fetched = job_fetch.fetch_job_text(req.url)
        if fetched is None:
            raise HTTPException(status_code=422, detail={"code": "FETCH_FAILED"})
        description, method = fetched, "url"
    else:
        raise HTTPException(status_code=422, detail={"code": "NO_INPUT"})
    criteria = job_fetch.extract_criteria(description, llm)
    return {"criteria": criteria, "description": description, "fetch_method": method}
