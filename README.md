# CV-AI

AI-powered CV parsing, job-fit scoring, and ATS conversion.

- `api/` — FastAPI backend (Google Gemini for LLM work, Supabase JWT auth)
- `web/` — Next.js frontend (Supabase auth, next-intl EN/TR)

## Running the project

Open two terminals.

**Terminal 1 — API (http://localhost:8000):**

    cd api
    .venv\Scripts\uvicorn app.main:app --reload --port 8000

**Terminal 2 — Web (http://localhost:3000):**

    cd web
    npm run dev

Then open http://localhost:3000 in your browser. API docs are at http://localhost:8000/docs.

> **Windows note:** use the correct casing in paths (e.g. `C:\Users\ASUS\Desktop\cv-ai`, capital **D**) — a mismatched-case path can break the Next.js build.

First-time setup (dependencies, `.env` files) is documented in [api/README.md](api/README.md) and [web/README.md](web/README.md).

## Ports

If port 3000 is busy, Next.js falls back to 3001 and the frontend may fail to talk to the API. Kill the stale dev server and restart instead.
