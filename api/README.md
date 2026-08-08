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

Only needed for the inbox feature below:

    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_SERVICE_KEY=...   # service_role key; server-only, never in the web app
    EMAIL_TOKEN_KEY=...        # Fernet key encrypting stored Gmail refresh tokens
    GOOGLE_CLIENT_ID=...       # our own OAuth client, not Supabase's
    GOOGLE_CLIENT_SECRET=...

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

## Inbox status tracking

- `POST /inbox/connect` — exchange a Google authorization code for a stored,
  encrypted refresh token. Requires `access_type=offline&prompt=consent` on the
  consent URL, or Google returns no refresh token and the call fails.
- `DELETE /inbox/connect` — revoke at Google, then delete the row.
- `GET /inbox/status` — `{connected, email, last_synced_at, status}`.
- `POST /inbox/sync` — scan new mail, update application stages, return what
  changed. Returns 409 `GMAIL_DISCONNECTED` when the grant is gone.

Generate the token key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

`gmail.readonly` is a Google restricted scope: it works for test users added in
the Google Cloud console, but publishing to general users requires OAuth
verification and an annual CASA assessment.

The refresh token is the one secret here that is worth stealing. It is stored
Fernet-encrypted, never returned by any endpoint, and never logged. The
service-role key reaches `email_connections`, which no browser can read: RLS is
on and no policy grants anything.
