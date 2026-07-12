# CV-AI API

FastAPI backend: CV parsing, job-fit scoring, ATS conversion.

## Setup
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env   # fill in OPENAI_API_KEY, SUPABASE_JWT_SECRET

## Run
    .venv\Scripts\uvicorn app.main:app --reload --port 8000

## Test
    .venv\Scripts\python -m pytest -v

Endpoints: POST /cv/parse, /job/fetch, /score, /ats/rewrite, /ats/pdf (all JWT-protected).
