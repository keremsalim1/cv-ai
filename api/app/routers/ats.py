from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.auth import get_current_user
from app.schemas import CVData
from app.services.ats import render_pdf, rewrite_ats
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/ats", tags=["ats"])


class AtsRequest(BaseModel):
    cv: CVData
    language: str = "tr"


@router.post("/rewrite")
def rewrite(
    req: AtsRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    return {"cv": rewrite_ats(req.cv, req.language, llm)}


@router.post("/pdf")
def pdf(req: AtsRequest, user_id: str = Depends(get_current_user)):
    data = render_pdf(req.cv, req.language)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="cv-ats.pdf"'})
