from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import apply as apply_router
from app.routers import ats as ats_router
from app.routers import cv as cv_router
from app.routers import job as job_router
from app.routers import score as score_router
from app.services.llm import LLMError

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Assisted-apply sessions own real browser processes; never leak them.
    from app.services.session import session_manager
    session_manager.close_all()


app = FastAPI(title="KRESUME.ai API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMError)
def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=502,
                        content={"detail": {"code": "AI_UNAVAILABLE"}})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cv_router.router)
app.include_router(job_router.router)
app.include_router(score_router.router)
app.include_router(ats_router.router)
app.include_router(apply_router.router)
