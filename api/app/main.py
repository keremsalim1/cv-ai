from fastapi import FastAPI

app = FastAPI(title="CV-AI API")

@app.get("/health")
def health():
    return {"status": "ok"}


from app.routers import cv as cv_router
from app.routers import job as job_router

app.include_router(cv_router.router)
app.include_router(job_router.router)
