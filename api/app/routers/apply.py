from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas import CVData, FieldAnswer
from app.services.apply import prepare_application
from app.services.browser import get_driver_factory
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/apply", tags=["apply"])


class PrepareRequest(BaseModel):
    cv: CVData
    url: str
    language: str = "tr"
    headed: bool = False


@router.post("/prepare")
def prepare(
    req: PrepareRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
    make_driver=Depends(get_driver_factory),
):
    return prepare_application(req.cv, req.url, req.language, req.headed,
                               llm, make_driver)
