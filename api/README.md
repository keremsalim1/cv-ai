# CV-AI API

FastAPI backend: CV parsing, job-fit scoring, ATS conversion.

Uses Google Gemini (via its OpenAI-compatible endpoint) for the LLM work.

## Setup
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env   # fill in GEMINI_API_KEY, SUPABASE_JWT_SECRET

Get a free Gemini API key at https://aistudio.google.com/apikey.

## Run
    .venv\Scripts\uvicorn app.main:app --reload --port 8000

## Test
    .venv\Scripts\python -m pytest -v

Endpoints: POST /cv/parse, /job/fetch, /score, /ats/rewrite, /ats/pdf (all JWT-protected).
