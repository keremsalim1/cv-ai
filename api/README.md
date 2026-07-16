# KRESUME.ai API

FastAPI backend: CV parsing, job-fit scoring, ATS conversion.

Uses Google Gemini (via its OpenAI-compatible endpoint) for the LLM work.

## Setup
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt

Create a `.env` file in this directory:

    GEMINI_API_KEY=...
    SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
    SUPABASE_JWT_SECRET=...   # legacy HS256 fallback; optional with JWKS

Get a free Gemini API key at https://aistudio.google.com/apikey.

## Run
    .venv\Scripts\uvicorn app.main:app --reload --port 8000

## Test
    .venv\Scripts\python -m pytest -v

Endpoints: POST /cv/parse, /job/fetch, /score, /ats/rewrite, /ats/pdf (all JWT-protected).
