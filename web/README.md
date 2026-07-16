# KRESUME.ai Web

Next.js 16 frontend for KRESUME.ai: upload a PDF CV, score it against a job posting,
convert to an ATS-ready PDF. TR/EN via next-intl. Auth + data + files on Supabase
(RLS); AI endpoints served by `../api` (FastAPI).

## Setup

    npm install
    copy .env.example .env.local   # fill in Supabase URL/anon key + API URL

Apply `../supabase/migrations/0001_init.sql` to your Supabase project
(SQL Editor or `supabase db push`). Enable the Google provider in
Supabase Auth and add `<origin>/auth/callback` to the redirect allowlist.

## Run (with the API)

    # terminal 1:  ..\api>  .venv\Scripts\uvicorn app.main:app --reload --port 8000
    npm run dev

## Test

    npm run test        # unit (vitest)
    npm run typecheck   # tsc --noEmit
    npm run e2e         # needs E2E_BASE_URL (and `npm run dev` running)

Routes: `/`, `/login`, `/register`, `/dashboard`, `/cv/[id]`, `/cv/[id]/score`.

## Windows note

Run all commands from the correctly-cased path (`C:\Users\<you>\Desktop\cv-ai\web`,
capital `D`). A lowercase `desktop` working directory loads duplicate copies of
Next.js modules and `next build` fails with
`Invariant: Expected workStore to be initialized`.
