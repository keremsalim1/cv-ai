# KRESUME.ai API

FastAPI backend: CV parsing, job-fit scoring, ATS conversion.

Uses Google Gemini (via its OpenAI-compatible endpoint) for the LLM work.

## Setup
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    .venv\Scripts\playwright install chromium   # for /apply automation

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

## Apply automation

- `POST /apply/prepare` — opens the application URL (headless; `headed: true`
  opens a visible window so the user can log in), extracts the form, and asks
  the LLM to optimize the CV and draft answers. Statuses: ready,
  login_required, captcha, form_not_found.
- `POST /apply/submit` — re-opens the page, fills the approved answers,
  uploads the ATS PDF, clicks submit, returns a screenshot. Statuses:
  submitted, failed, login_required, captcha.
- Browser state lives in `.browser-profile/` (git-ignored). CAPTCHAs are
  never bypassed; nothing is submitted without the user-approved answers.
