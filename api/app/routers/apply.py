from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.schemas import CVData, FieldAnswer
from app.services.apply import assist_fill, prepare_application, submit_application
from app.services.browser import get_driver_factory
from app.services.llm import LLMClient, get_llm
from app.services.session import get_session_factory, session_manager

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


# --- Assisted apply: a persistent headed browser the user drives themselves ---


class AssistStartRequest(BaseModel):
    url: str


@router.post("/assist/start")
def assist_start(
    req: AssistStartRequest,
    user_id: str = Depends(get_current_user),
    make_session=Depends(get_session_factory),
):
    sid = session_manager.start(make_session, req.url, user_id)
    return {"session_id": sid}


class AssistFillRequest(BaseModel):
    session_id: str
    cv: CVData
    language: str = "tr"


@router.post("/assist/fill")
def assist_fill_route(
    req: AssistFillRequest,
    user_id: str = Depends(get_current_user),
    llm: LLMClient = Depends(get_llm),
):
    session = session_manager.get(req.session_id, user_id)
    return assist_fill(session, req.cv, req.language, llm, user_id)


class AssistCloseRequest(BaseModel):
    session_id: str


@router.post("/assist/close")
def assist_close(
    req: AssistCloseRequest,
    user_id: str = Depends(get_current_user),
):
    session_manager.close(req.session_id, user_id)
    return {"ok": True}
