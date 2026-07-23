from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.schemas import CVData, FieldAnswer
from app.services.apply import prepare_application, submit_application
from app.services.browser import get_driver_factory
from app.services.llm import LLMClient, get_llm

router = APIRouter(prefix="/apply", tags=["apply"])


class PrepareRequest(BaseModel):
    cv: CVData
    url: str
    language: str = "tr"
    headed: bool = False


@router.post("/prepare")
def prepare(
    req: PrepareRequest,
    user_id: str = Depends(get_current_user),
    llm: LLMClient = Depends(get_llm),
    make_driver=Depends(get_driver_factory),
):
    # Auth up front; the daily-AI-limit charge happens inside the service, only
    # once we actually reach the LLM call (not on login/captcha/no-form pages).
    return prepare_application(req.cv, req.url, req.language, req.headed,
                               llm, make_driver, user_id)


class SubmitRequest(BaseModel):
    cv: CVData
    url: str
    language: str = "tr"
    answers: list[FieldAnswer] = []
    headed: bool = False


@router.post("/submit")
def submit(
    req: SubmitRequest,
    user_id: str = Depends(get_current_user),
    make_driver=Depends(get_driver_factory),
):
    return submit_application(req.cv, req.url, req.language, req.answers,
                              req.headed, make_driver)
