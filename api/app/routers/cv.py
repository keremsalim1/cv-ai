from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.services.cv_parser import parse_cv
from app.services.llm import LLMClient, get_llm
from app.services.pdf_extract import InvalidPdfError, ScannedPdfError, extract_text
from app.services.usage import check_usage

MAX_SIZE = 10 * 1024 * 1024

router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/parse")
async def cv_parse(
    file: UploadFile,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
):
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail={"code": "FILE_TOO_LARGE"})
    try:
        text = extract_text(data)
    except ScannedPdfError:
        raise HTTPException(status_code=400, detail={"code": "SCANNED_PDF"})
    except InvalidPdfError:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PDF"})
    cv = parse_cv(text, llm)
    return {"cv": cv}
