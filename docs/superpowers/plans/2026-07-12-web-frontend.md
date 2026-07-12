# CV-AI Web Frontend + Supabase Persistence Implementation Plan (Plan 2/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js 15 web app (`web/`) with TR/EN i18n, Supabase auth + persistence (RLS), wired to the Plan 1 FastAPI backend: upload CV → parse → score against a job posting → convert to ATS PDF.

**Architecture:** Client-heavy App Router app. Interactive pages are client components using a browser Supabase client; a middleware refreshes sessions and gates protected routes. All AI work goes through the Plan 1 API (`/cv/parse`, `/job/fetch`, `/score`, `/ats/rewrite`, `/ats/pdf`) via one typed API client that attaches the Supabase JWT. Persistence (cvs, job_postings, evaluations) is written directly from the browser through Supabase with Row Level Security; PDFs live in a private `cvs` Storage bucket.

**Tech Stack:** Next.js 15 (App Router, src dir, `@/*` alias), TypeScript strict, Tailwind + shadcn/ui, next-intl (cookie-based locale, no URL prefix), @supabase/supabase-js + @supabase/ssr, Vitest + React Testing Library (jsdom), Playwright (gated smoke).

## Global Constraints

- Working directory for all commands: `C:\Users\ASUS\desktop\cv-ai\web` unless stated otherwise (PowerShell).
- Node 18.18+ required (Next 15 floor).
- TypeScript strict mode (create-next-app default) — `npm run typecheck` must stay clean.
- Default locale `tr`; locale stored in a `locale` cookie; supported locales exactly `tr`, `en`.
- Upload limit 10 MB, PDF only — client pre-validates; API re-checks (`FILE_TOO_LARGE`).
- Storage bucket `cvs` (private); object path `<user_id>/<uuid>.pdf` — first folder MUST be the user id (RLS depends on it).
- Browser uses only the anon key (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`); the service-role key never appears in `web/`.
- API base URL: `NEXT_PUBLIC_API_URL`, default `http://localhost:8000`.
- Backend error codes to localize: `SCANNED_PDF`, `INVALID_PDF`, `FILE_TOO_LARGE`, `FETCH_FAILED`, `NO_INPUT`, `DAILY_LIMIT_REACHED`, `AI_UNAVAILABLE` (+ client-side `NOT_AUTHENTICATED`, fallback `UNKNOWN`).
- Repeated score for the same CV+job pair must come from the `evaluations` table, not a new `/score` call (evaluations has `unique (cv_id, job_id)`).
- ATS conversion never mutates the original CV row; it inserts a new `cvs` row with `is_ats=true`, `source_cv_id=<original>`.

---

### Task 1: Next.js scaffold + Vitest + first component (StarRating)

**Files:**
- Create (generated): `web/` via create-next-app, shadcn/ui `src/components/ui/{button,card,input,textarea}.tsx`
- Create: `web/vitest.config.ts`, `web/vitest.setup.ts`, `web/.env.example`, `web/src/lib/constants.ts`, `web/src/components/StarRating.tsx`
- Test: `web/src/components/__tests__/StarRating.test.tsx`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `StarRating({ stars }: { stars: number })` React component (aria-label `"{stars}/5"`); `MAX_FILE_SIZE: number` (bytes) from `@/lib/constants`; working `npm run test` (vitest) and `npm run typecheck` (tsc --noEmit); shadcn `Button`, `Card`, `Input`, `Textarea` under `@/components/ui/*`.

- [ ] **Step 1: Scaffold the app**

From `C:\Users\ASUS\desktop\cv-ai` (repo root):

```powershell
npx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir --turbopack --import-alias "@/*" --use-npm
cd web
npx shadcn@latest init -d
npx shadcn@latest add button card input textarea
npm i next-intl @supabase/supabase-js @supabase/ssr
npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
```

- [ ] **Step 2: Configure Vitest and scripts**

`web/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
})
```

`web/vitest.setup.ts`:
```ts
import '@testing-library/jest-dom/vitest'

process.env.NEXT_PUBLIC_SUPABASE_URL ||= 'http://localhost:54321'
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||= 'test-anon-key'
process.env.NEXT_PUBLIC_API_URL ||= 'http://localhost:8000'
```

Add to `web/package.json` `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest",
"typecheck": "tsc --noEmit"
```

`web/.env.example`:
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

`web/src/lib/constants.ts`:
```ts
export const MAX_FILE_SIZE = 10 * 1024 * 1024 // bytes; API enforces the same limit
```

- [ ] **Step 3: Write the failing test**

`web/src/components/__tests__/StarRating.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { StarRating } from '@/components/StarRating'

it('renders filled and empty stars', () => {
  render(<StarRating stars={4} />)
  const el = screen.getByLabelText('4/5')
  expect(el).toHaveTextContent('★★★★☆')
})

it('renders one star minimum', () => {
  render(<StarRating stars={1} />)
  expect(screen.getByLabelText('1/5')).toHaveTextContent('★☆☆☆☆')
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `npm run test`
Expected: FAIL — cannot resolve `@/components/StarRating`

- [ ] **Step 5: Write minimal implementation**

`web/src/components/StarRating.tsx`:
```tsx
export function StarRating({ stars }: { stars: number }) {
  const n = Math.min(5, Math.max(1, Math.round(stars)))
  return (
    <span aria-label={`${n}/5`} className="text-xl tracking-wide">
      {'★'.repeat(n)}
      {'☆'.repeat(5 - n)}
    </span>
  )
}
```

- [ ] **Step 6: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: both clean

- [ ] **Step 7: Commit**

```powershell
git add web
git commit -m "feat(web): scaffold Next.js app with Vitest and StarRating"
```

---

### Task 2: Supabase schema (SQL + RLS) and shared TypeScript types

**Files:**
- Create: `supabase/migrations/0001_init.sql` (repo root), `web/src/types/api.ts`, `web/src/types/db.ts`
- Test: `web/src/types/__tests__/schema.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (used by every later task):
  - `types/api.ts`: `Experience`, `Education`, `CVData`, `JobCriteria`, `EvaluationResult`, `JobFetchResult` — field-for-field mirrors of the Plan 1 Pydantic schemas.
  - `types/db.ts`: `ProfileRow`, `CvRow`, `NewCv`, `JobPostingRow`, `NewJobPosting`, `EvaluationRow`, `NewEvaluation`.
  - SQL migration creating `profiles`, `cvs`, `job_postings`, `evaluations` (+ RLS, signup trigger, `cvs` storage bucket + policy, `unique (cv_id, job_id)`).

- [ ] **Step 1: Write the failing test**

`web/src/types/__tests__/schema.test.ts`:
```ts
import fs from 'node:fs'
import path from 'node:path'
import type { CvRow, EvaluationRow, JobPostingRow, NewCv } from '@/types/db'
import type { CVData } from '@/types/api'

const sql = () =>
  fs.readFileSync(path.resolve(process.cwd(), '../supabase/migrations/0001_init.sql'), 'utf-8')

it('migration enables RLS on all four tables', () => {
  const matches = sql().match(/enable row level security/g) ?? []
  expect(matches.length).toBeGreaterThanOrEqual(4)
})

it('migration enforces one evaluation per cv+job pair', () => {
  expect(sql()).toMatch(/unique\s*\(cv_id,\s*job_id\)/)
})

it('row types accept well-formed values', () => {
  const cv: CVData = {
    full_name: 'Ada Lovelace', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: ['Python'], languages: [], certifications: [],
  }
  const row: NewCv = { user_id: 'u1', file_path: 'u1/a.pdf', parsed_data: cv, is_ats: false, source_cv_id: null }
  const full: CvRow = { ...row, id: 'c1', created_at: '2026-07-12T00:00:00Z' }
  const job: JobPostingRow = {
    id: 'j1', user_id: 'u1', url: null, title: 'Dev', company: null,
    description: 'desc', fetch_method: 'manual', created_at: '2026-07-12T00:00:00Z',
  }
  const ev: EvaluationRow = {
    id: 'e1', cv_id: full.id, job_id: job.id, percent: 78, stars: 4,
    strengths: [], gaps: [], suggestions: [], created_at: '2026-07-12T00:00:00Z',
  }
  expect(ev.stars).toBe(4)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- schema`
Expected: FAIL — migration file not found / cannot resolve `@/types/db`

- [ ] **Step 3: Write the migration**

`supabase/migrations/0001_init.sql`:
```sql
-- CV-AI initial schema (MVP Phase 1)

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  language text not null default 'tr' check (language in ('tr', 'en'))
);

create table public.cvs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  file_path text not null,
  parsed_data jsonb not null,
  is_ats boolean not null default false,
  source_cv_id uuid references public.cvs (id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.job_postings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  url text,
  title text not null,
  company text,
  description text not null,
  fetch_method text not null check (fetch_method in ('url', 'manual')),
  created_at timestamptz not null default now()
);

create table public.evaluations (
  id uuid primary key default gen_random_uuid(),
  cv_id uuid not null references public.cvs (id) on delete cascade,
  job_id uuid not null references public.job_postings (id) on delete cascade,
  percent int not null check (percent between 0 and 100),
  stars int not null check (stars between 1 and 5),
  strengths jsonb not null default '[]',
  gaps jsonb not null default '[]',
  suggestions jsonb not null default '[]',
  created_at timestamptz not null default now(),
  unique (cv_id, job_id)
);

-- Row Level Security: every user sees only their own data (KVKK/GDPR baseline)
alter table public.profiles enable row level security;
alter table public.cvs enable row level security;
alter table public.job_postings enable row level security;
alter table public.evaluations enable row level security;

create policy "own profile" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

create policy "own cvs" on public.cvs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own job postings" on public.job_postings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own evaluations" on public.evaluations
  for all
  using (exists (select 1 from public.cvs c where c.id = cv_id and c.user_id = auth.uid()))
  with check (exists (select 1 from public.cvs c where c.id = cv_id and c.user_id = auth.uid()));

-- Auto-create a profile row on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data ->> 'full_name');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Private storage bucket for CV PDFs; first path folder must equal the user id
insert into storage.buckets (id, name, public) values ('cvs', 'cvs', false);

create policy "own cv files" on storage.objects
  for all
  using (bucket_id = 'cvs' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'cvs' and (storage.foldername(name))[1] = auth.uid()::text);
```

Apply it to the Supabase project (dashboard → SQL Editor → paste & run, or `supabase db push` if the CLI is linked). The unit suite does not need a live database.

- [ ] **Step 4: Write the shared types**

`web/src/types/api.ts`:
```ts
// Mirrors api/app/schemas.py (Plan 1). Keep in sync by hand.

export interface Experience {
  title: string
  company: string
  start_date: string | null
  end_date: string | null
  description: string | null
}

export interface Education {
  degree: string
  school: string
  year: string | null
}

export interface CVData {
  full_name: string
  email: string | null
  phone: string | null
  location: string | null
  summary: string | null
  experiences: Experience[]
  education: Education[]
  skills: string[]
  languages: string[]
  certifications: string[]
}

export interface JobCriteria {
  title: string
  company: string | null
  requirements: string[]
  skills: string[]
}

export interface EvaluationResult {
  percent: number
  stars: number
  strengths: string[]
  gaps: string[]
  suggestions: string[]
}

export interface JobFetchResult {
  criteria: JobCriteria
  description: string
  fetch_method: 'url' | 'manual'
}
```

`web/src/types/db.ts`:
```ts
import type { CVData } from './api'

export interface ProfileRow {
  id: string
  full_name: string | null
  language: 'tr' | 'en'
}

export interface CvRow {
  id: string
  user_id: string
  file_path: string
  parsed_data: CVData
  is_ats: boolean
  source_cv_id: string | null
  created_at: string
}
export type NewCv = Omit<CvRow, 'id' | 'created_at'>

export interface JobPostingRow {
  id: string
  user_id: string
  url: string | null
  title: string
  company: string | null
  description: string
  fetch_method: 'url' | 'manual'
  created_at: string
}
export type NewJobPosting = Omit<JobPostingRow, 'id' | 'created_at'>

export interface EvaluationRow {
  id: string
  cv_id: string
  job_id: string
  percent: number
  stars: number
  strengths: string[]
  gaps: string[]
  suggestions: string[]
  created_at: string
}
export type NewEvaluation = Omit<EvaluationRow, 'id' | 'created_at'>
```

- [ ] **Step 5: Verify tests + typecheck pass**

Run: `npm run test -- schema` then `npm run typecheck`
Expected: both clean

- [ ] **Step 6: Commit**

```powershell
git add ..\supabase web\src\types
git commit -m "feat(web): Supabase schema with RLS + shared TS types"
```

---

### Task 3: i18n (next-intl, cookie locale) + LocaleSwitcher + test utils

**Files:**
- Create: `web/src/i18n/request.ts`, `web/src/messages/tr.json`, `web/src/messages/en.json`, `web/src/components/LocaleSwitcher.tsx`, `web/src/test/utils.tsx`
- Modify: `web/next.config.ts`, `web/src/app/layout.tsx`
- Test: `web/src/messages/__tests__/parity.test.ts`, `web/src/components/__tests__/LocaleSwitcher.test.tsx`

**Interfaces:**
- Consumes: scaffold from Task 1.
- Produces: `renderWithIntl(ui: ReactNode)` test helper from `@/test/utils` (wraps `NextIntlClientProvider` locale `tr` + `tr.json`); message namespaces `nav`, `landing`, `auth`, `dashboard`, `cv`, `score`, `errors`, `common` (all later UI tasks call `useTranslations()` with these exact keys); `LocaleSwitcher` component; root layout providing messages to client components.

- [ ] **Step 1: Write the failing tests**

`web/src/messages/__tests__/parity.test.ts`:
```ts
import tr from '@/messages/tr.json'
import en from '@/messages/en.json'

function flat(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? flat(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]
  )
}

it('tr and en have identical message keys', () => {
  expect(flat(tr).sort()).toEqual(flat(en).sort())
})

it('all backend error codes are localized', () => {
  const codes = ['SCANNED_PDF', 'INVALID_PDF', 'FILE_TOO_LARGE', 'FETCH_FAILED',
    'NO_INPUT', 'DAILY_LIMIT_REACHED', 'AI_UNAVAILABLE', 'NOT_AUTHENTICATED', 'UNKNOWN']
  for (const code of codes) {
    expect(tr.errors).toHaveProperty(code)
    expect(en.errors).toHaveProperty(code)
  }
})
```

`web/src/components/__tests__/LocaleSwitcher.test.tsx`:
```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { LocaleSwitcher } from '@/components/LocaleSwitcher'

const refresh = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}))

it('shows the other locale and sets the cookie on click', async () => {
  renderWithIntl(<LocaleSwitcher />)
  const btn = screen.getByRole('button', { name: 'switch language' })
  expect(btn).toHaveTextContent('EN')
  await userEvent.click(btn)
  expect(document.cookie).toContain('locale=en')
  expect(refresh).toHaveBeenCalled()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- parity LocaleSwitcher`
Expected: FAIL — missing message files / components

- [ ] **Step 3: Write messages, i18n config, switcher, test utils**

`web/src/messages/tr.json`:
```json
{
  "nav": {
    "appName": "CV-AI",
    "dashboard": "Panel",
    "login": "Giriş",
    "register": "Kayıt Ol",
    "logout": "Çıkış"
  },
  "landing": {
    "title": "CV'nizi yapay zeka ile işe hazırlayın",
    "subtitle": "PDF CV'nizi yükleyin, ilana uygunluğunuzu görün, tek tıkla ATS uyumlu CV indirin.",
    "cta": "Ücretsiz Başla"
  },
  "auth": {
    "loginTitle": "Giriş Yap",
    "registerTitle": "Kayıt Ol",
    "fullNameLabel": "Ad Soyad",
    "emailLabel": "E-posta",
    "passwordLabel": "Şifre",
    "loginButton": "Giriş Yap",
    "registerButton": "Kayıt Ol",
    "googleButton": "Google ile devam et",
    "noAccount": "Hesabınız yok mu? Kayıt olun",
    "haveAccount": "Zaten hesabınız var mı? Giriş yapın",
    "checkEmail": "Doğrulama bağlantısı için e-postanızı kontrol edin."
  },
  "dashboard": {
    "title": "CV'lerim",
    "upload": "CV Yükle (PDF)",
    "uploading": "Yükleniyor ve okunuyor…",
    "empty": "Henüz CV yüklemediniz. PDF CV'nizi yükleyerek başlayın.",
    "atsBadge": "ATS",
    "viewAction": "Görüntüle",
    "scoreAction": "Skorla"
  },
  "cv": {
    "title": "CV Detayı",
    "contact": "İletişim",
    "summary": "Özet",
    "experience": "İş Deneyimi",
    "education": "Eğitim",
    "skills": "Beceriler",
    "languages": "Diller",
    "certifications": "Sertifikalar",
    "convertAts": "ATS'ye Dönüştür",
    "converting": "Dönüştürülüyor…",
    "downloadPdf": "PDF İndir",
    "scoreCta": "İlana Göre Skorla"
  },
  "score": {
    "title": "Uygunluk Skoru",
    "urlLabel": "İş ilanı bağlantısı",
    "pasteLabel": "İlan metni",
    "pasteFallbackNotice": "İlan sayfası çekilemedi. Lütfen ilan metnini aşağıya yapıştırın.",
    "scoreButton": "Skorla",
    "scoring": "Skorlanıyor…",
    "cached": "Bu CV ve ilan için önceki sonuç gösteriliyor.",
    "strengths": "Güçlü Yönler",
    "gaps": "Eksikler",
    "suggestions": "Öneriler"
  },
  "errors": {
    "SCANNED_PDF": "Bu PDF taranmış görünüyor. Lütfen metin tabanlı bir PDF yükleyin.",
    "INVALID_PDF": "Geçersiz dosya. Lütfen bir PDF yükleyin.",
    "FILE_TOO_LARGE": "Dosya 10 MB sınırını aşıyor.",
    "FETCH_FAILED": "İlan sayfası çekilemedi.",
    "NO_INPUT": "Bir ilan bağlantısı girin veya ilan metnini yapıştırın.",
    "DAILY_LIMIT_REACHED": "Günlük AI kullanım limitine ulaştınız. Yarın tekrar deneyin.",
    "AI_UNAVAILABLE": "AI servisi şu anda yanıt vermiyor. Birazdan tekrar deneyin.",
    "NOT_AUTHENTICATED": "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.",
    "UNKNOWN": "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."
  },
  "common": {
    "loading": "Yükleniyor…"
  }
}
```

`web/src/messages/en.json`:
```json
{
  "nav": {
    "appName": "CV-AI",
    "dashboard": "Dashboard",
    "login": "Log in",
    "register": "Sign up",
    "logout": "Log out"
  },
  "landing": {
    "title": "Get your CV job-ready with AI",
    "subtitle": "Upload your PDF CV, see how well you fit a job posting, and download an ATS-ready CV in one click.",
    "cta": "Start for free"
  },
  "auth": {
    "loginTitle": "Log in",
    "registerTitle": "Sign up",
    "fullNameLabel": "Full name",
    "emailLabel": "Email",
    "passwordLabel": "Password",
    "loginButton": "Log in",
    "registerButton": "Sign up",
    "googleButton": "Continue with Google",
    "noAccount": "No account? Sign up",
    "haveAccount": "Already have an account? Log in",
    "checkEmail": "Check your email for the confirmation link."
  },
  "dashboard": {
    "title": "My CVs",
    "upload": "Upload CV (PDF)",
    "uploading": "Uploading and parsing…",
    "empty": "No CVs yet. Upload your PDF CV to get started.",
    "atsBadge": "ATS",
    "viewAction": "View",
    "scoreAction": "Score"
  },
  "cv": {
    "title": "CV Detail",
    "contact": "Contact",
    "summary": "Summary",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "languages": "Languages",
    "certifications": "Certifications",
    "convertAts": "Convert to ATS",
    "converting": "Converting…",
    "downloadPdf": "Download PDF",
    "scoreCta": "Score against a job"
  },
  "score": {
    "title": "Fit Score",
    "urlLabel": "Job posting URL",
    "pasteLabel": "Job posting text",
    "pasteFallbackNotice": "Could not fetch the posting page. Please paste the job text below.",
    "scoreButton": "Score",
    "scoring": "Scoring…",
    "cached": "Showing the previous result for this CV and posting.",
    "strengths": "Strengths",
    "gaps": "Gaps",
    "suggestions": "Suggestions"
  },
  "errors": {
    "SCANNED_PDF": "This PDF looks scanned. Please upload a text-based PDF.",
    "INVALID_PDF": "Invalid file. Please upload a PDF.",
    "FILE_TOO_LARGE": "File exceeds the 10 MB limit.",
    "FETCH_FAILED": "Could not fetch the posting page.",
    "NO_INPUT": "Enter a posting URL or paste the job text.",
    "DAILY_LIMIT_REACHED": "You reached today's AI usage limit. Try again tomorrow.",
    "AI_UNAVAILABLE": "The AI service is not responding right now. Please retry shortly.",
    "NOT_AUTHENTICATED": "Your session expired. Please log in again.",
    "UNKNOWN": "Something went wrong. Please try again."
  },
  "common": {
    "loading": "Loading…"
  }
}
```

`web/src/i18n/request.ts`:
```ts
import { getRequestConfig } from 'next-intl/server'
import { cookies } from 'next/headers'

export default getRequestConfig(async () => {
  const store = await cookies()
  const locale = store.get('locale')?.value === 'en' ? 'en' : 'tr'
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
```

`web/next.config.ts` (replace file):
```ts
import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts')

const nextConfig: NextConfig = {}

export default withNextIntl(nextConfig)
```

`web/src/app/layout.tsx` (replace file):
```tsx
import type { Metadata } from 'next'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import './globals.css'

export const metadata: Metadata = {
  title: 'CV-AI',
  description: 'AI-powered CV analysis and ATS conversion',
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <html lang={locale}>
      <body className="min-h-screen antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

`web/src/components/LocaleSwitcher.tsx`:
```tsx
'use client'
import { useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'

export function LocaleSwitcher() {
  const locale = useLocale()
  const router = useRouter()
  const next = locale === 'tr' ? 'en' : 'tr'

  function toggle() {
    document.cookie = `locale=${next};path=/;max-age=31536000`
    router.refresh()
  }

  return (
    <button onClick={toggle} aria-label="switch language" className="text-sm font-medium">
      {next.toUpperCase()}
    </button>
  )
}
```

`web/src/test/utils.tsx`:
```tsx
import { render } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import type { ReactNode } from 'react'
import tr from '@/messages/tr.json'

export function renderWithIntl(ui: ReactNode) {
  return render(
    <NextIntlClientProvider locale="tr" messages={tr}>
      {ui}
    </NextIntlClientProvider>
  )
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): TR/EN i18n with next-intl and locale switcher"
```

---

### Task 4: Supabase clients + protected-route middleware

**Files:**
- Create: `web/src/lib/supabase/client.ts`, `web/src/lib/supabase/server.ts`, `web/src/lib/protected.ts`, `web/src/middleware.ts`
- Test: `web/src/lib/__tests__/protected.test.ts`

**Interfaces:**
- Consumes: env vars from Task 1 setup.
- Produces: `createClient()` from `@/lib/supabase/client` (browser `SupabaseClient`); `createClient()` from `@/lib/supabase/server` (async, cookie-bound, for route handlers); `isProtectedPath(pathname: string): boolean` from `@/lib/protected`; middleware that refreshes the session and redirects anonymous users to `/login` for `/dashboard` and `/cv/*`.

- [ ] **Step 1: Write the failing test**

`web/src/lib/__tests__/protected.test.ts`:
```ts
import { isProtectedPath } from '@/lib/protected'

it.each([
  ['/dashboard', true],
  ['/dashboard/anything', true],
  ['/cv/abc', true],
  ['/cv/abc/score', true],
  ['/', false],
  ['/login', false],
  ['/register', false],
  ['/auth/callback', false],
  ['/cvsomething', false],
])('%s -> %s', (path, expected) => {
  expect(isProtectedPath(path)).toBe(expected)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- protected`
Expected: FAIL — cannot resolve `@/lib/protected`

- [ ] **Step 3: Write the implementation**

`web/src/lib/protected.ts`:
```ts
const PROTECTED_PREFIXES = ['/dashboard', '/cv']

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))
}
```

`web/src/lib/supabase/client.ts`:
```ts
import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

`web/src/lib/supabase/server.ts`:
```ts
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (toSet) => {
          try {
            toSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
          } catch {
            // Called from a Server Component; the middleware refreshes sessions instead.
          }
        },
      },
    }
  )
}
```

`web/src/middleware.ts`:
```ts
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { isProtectedPath } from '@/lib/protected'

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (toSet) => {
          toSet.forEach(({ name, value }) => request.cookies.set(name, value))
          response = NextResponse.next({ request })
          toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options))
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  if (!user && isProtectedPath(request.nextUrl.pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): Supabase clients and protected-route middleware"
```

---

### Task 5: Error mapping + typed API client

**Files:**
- Create: `web/src/lib/errors.ts`, `web/src/lib/api.ts`
- Test: `web/src/lib/__tests__/errors.test.ts`, `web/src/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: `createClient` from `@/lib/supabase/client` (Task 4), types from Task 2.
- Produces (used by all page tasks):
  - `class ApiError extends Error { code: string; status: number }`
  - `messageKeyForCode(code: string): string` → `'errors.<CODE>'` for known codes, `'errors.UNKNOWN'` otherwise.
  - `parseCv(file: File): Promise<CVData>`
  - `fetchJob(input: { url?: string; text?: string }): Promise<JobFetchResult>`
  - `scoreCv(cv: CVData, job: JobCriteria): Promise<EvaluationResult>`
  - `atsRewrite(cv: CVData, language: string): Promise<CVData>`
  - `atsPdf(cv: CVData, language: string): Promise<Blob>`

- [ ] **Step 1: Write the failing tests**

`web/src/lib/__tests__/errors.test.ts`:
```ts
import { messageKeyForCode } from '@/lib/errors'

it('maps known codes to their message key', () => {
  expect(messageKeyForCode('SCANNED_PDF')).toBe('errors.SCANNED_PDF')
  expect(messageKeyForCode('DAILY_LIMIT_REACHED')).toBe('errors.DAILY_LIMIT_REACHED')
})

it('falls back to UNKNOWN for unrecognized codes', () => {
  expect(messageKeyForCode('SOMETHING_ELSE')).toBe('errors.UNKNOWN')
})
```

`web/src/lib/__tests__/api.test.ts`:
```ts
import { vi, type Mock } from 'vitest'

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'tok-123' } } }),
    },
  }),
}))

import { ApiError, fetchJob, parseCv, scoreCv } from '@/lib/api'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const CV = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

beforeEach(() => {
  global.fetch = vi.fn()
})

it('parseCv posts multipart with bearer token and unwraps cv', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { cv: CV }))
  const file = new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' })
  const cv = await parseCv(file)
  expect(cv.full_name).toBe('Ada')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/cv/parse')
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123')
  expect(init.body).toBeInstanceOf(FormData)
})

it('maps API error codes into ApiError', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(400, { detail: { code: 'SCANNED_PDF' } }))
  const file = new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' })
  await expect(parseCv(file)).rejects.toMatchObject({ code: 'SCANNED_PDF', status: 400 })
})

it('fetchJob sends JSON body', async () => {
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    criteria: { title: 'Dev', company: null, requirements: [], skills: [] },
    description: 'text', fetch_method: 'manual',
  }))
  const out = await fetchJob({ text: 'text' })
  expect(out.fetch_method).toBe('manual')
  const [, init] = (global.fetch as Mock).mock.calls[0]
  expect(JSON.parse(init.body as string)).toEqual({ text: 'text' })
})

it('scoreCv returns the evaluation and non-JSON errors become UNKNOWN', async () => {
  ;(global.fetch as Mock).mockResolvedValue(new Response('boom', { status: 500 }))
  await expect(
    scoreCv(CV, { title: 'Dev', company: null, requirements: [], skills: [] })
  ).rejects.toMatchObject({ code: 'UNKNOWN', status: 500 })
  expect(new ApiError('X', 1)).toBeInstanceOf(Error)
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- errors api`
Expected: FAIL — cannot resolve `@/lib/errors` / `@/lib/api`

- [ ] **Step 3: Write the implementation**

`web/src/lib/errors.ts`:
```ts
const KNOWN_CODES = new Set([
  'SCANNED_PDF', 'INVALID_PDF', 'FILE_TOO_LARGE', 'FETCH_FAILED',
  'NO_INPUT', 'DAILY_LIMIT_REACHED', 'AI_UNAVAILABLE', 'NOT_AUTHENTICATED', 'UNKNOWN',
])

export function messageKeyForCode(code: string): string {
  return `errors.${KNOWN_CODES.has(code) ? code : 'UNKNOWN'}`
}
```

`web/src/lib/api.ts`:
```ts
import { createClient } from '@/lib/supabase/client'
import type { CVData, EvaluationResult, JobCriteria, JobFetchResult } from '@/types/api'

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code)
    this.name = 'ApiError'
  }
}

function apiUrl(path: string): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + path
}

async function authHeaders(): Promise<Record<string, string>> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new ApiError('NOT_AUTHENTICATED', 401)
  return { Authorization: `Bearer ${session.access_token}` }
}

async function ensureOk(res: Response): Promise<Response> {
  if (res.ok) return res
  let code = 'UNKNOWN'
  try {
    const body = await res.json()
    if (typeof body?.detail?.code === 'string') code = body.detail.code
  } catch {
    // non-JSON error body
  }
  throw new ApiError(code, res.status)
}

export async function parseCv(file: File): Promise<CVData> {
  const form = new FormData()
  form.append('file', file)
  const res = await ensureOk(
    await fetch(apiUrl('/cv/parse'), { method: 'POST', headers: await authHeaders(), body: form })
  )
  return (await res.json()).cv
}

export async function fetchJob(input: { url?: string; text?: string }): Promise<JobFetchResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/job/fetch'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  )
  return res.json()
}

export async function scoreCv(cv: CVData, job: JobCriteria): Promise<EvaluationResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/score'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, job }),
    })
  )
  return res.json()
}

export async function atsRewrite(cv: CVData, language: string): Promise<CVData> {
  const res = await ensureOk(
    await fetch(apiUrl('/ats/rewrite'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, language }),
    })
  )
  return (await res.json()).cv
}

export async function atsPdf(cv: CVData, language: string): Promise<Blob> {
  const res = await ensureOk(
    await fetch(apiUrl('/ats/pdf'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, language }),
    })
  )
  return res.blob()
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): typed API client with JWT auth and error mapping"
```

---

### Task 6: Data access layer (db.ts)

**Files:**
- Create: `web/src/lib/db.ts`
- Test: `web/src/lib/__tests__/db.test.ts`

**Interfaces:**
- Consumes: types from Task 2; callers pass a `SupabaseClient` (from `createClient()` of Task 4).
- Produces (used by page tasks):
  - `listCvs(sb): Promise<CvRow[]>` — newest first
  - `getCv(sb, id: string): Promise<CvRow | null>`
  - `insertCv(sb, row: NewCv): Promise<CvRow>`
  - `findJobByUrl(sb, url: string): Promise<JobPostingRow | null>`
  - `insertJob(sb, row: NewJobPosting): Promise<JobPostingRow>`
  - `findEvaluation(sb, cvId: string, jobId: string): Promise<EvaluationRow | null>`
  - `insertEvaluation(sb, row: NewEvaluation): Promise<EvaluationRow>`

- [ ] **Step 1: Write the failing test**

`web/src/lib/__tests__/db.test.ts`:
```ts
import { vi } from 'vitest'
import { findEvaluation, insertCv, listCvs } from '@/lib/db'
import type { SupabaseClient } from '@supabase/supabase-js'

// Chainable stub: every method returns the stub; awaiting it resolves `result`.
function stubClient(result: unknown) {
  const q: Record<string, unknown> = {}
  for (const m of ['select', 'insert', 'order', 'eq', 'maybeSingle', 'single']) {
    q[m] = vi.fn(() => q)
  }
  ;(q as { then: unknown }).then = (resolve: (v: unknown) => void) => resolve(result)
  const from = vi.fn(() => q)
  return { sb: { from } as unknown as SupabaseClient, from, q }
}

it('listCvs queries cvs newest first', async () => {
  const rows = [{ id: 'c1' }]
  const { sb, from, q } = stubClient({ data: rows, error: null })
  await expect(listCvs(sb)).resolves.toEqual(rows)
  expect(from).toHaveBeenCalledWith('cvs')
  expect(q.order).toHaveBeenCalledWith('created_at', { ascending: false })
})

it('insertCv returns the inserted row', async () => {
  const row = { id: 'c2' }
  const { sb } = stubClient({ data: row, error: null })
  const newCv = {
    user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
    parsed_data: {
      full_name: 'Ada', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  }
  await expect(insertCv(sb, newCv)).resolves.toEqual(row)
})

it('findEvaluation filters by cv and job and can return null', async () => {
  const { sb, q } = stubClient({ data: null, error: null })
  await expect(findEvaluation(sb, 'c1', 'j1')).resolves.toBeNull()
  expect(q.eq).toHaveBeenCalledWith('cv_id', 'c1')
  expect(q.eq).toHaveBeenCalledWith('job_id', 'j1')
})

it('throws on supabase error', async () => {
  const { sb } = stubClient({ data: null, error: new Error('db down') })
  await expect(listCvs(sb)).rejects.toThrow('db down')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- db`
Expected: FAIL — cannot resolve `@/lib/db`

- [ ] **Step 3: Write the implementation**

`web/src/lib/db.ts`:
```ts
import type { SupabaseClient } from '@supabase/supabase-js'
import type {
  CvRow, EvaluationRow, JobPostingRow, NewCv, NewEvaluation, NewJobPosting,
} from '@/types/db'

export async function listCvs(sb: SupabaseClient): Promise<CvRow[]> {
  const { data, error } = await sb.from('cvs').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return (data ?? []) as CvRow[]
}

export async function getCv(sb: SupabaseClient, id: string): Promise<CvRow | null> {
  const { data, error } = await sb.from('cvs').select('*').eq('id', id).maybeSingle()
  if (error) throw error
  return data as CvRow | null
}

export async function insertCv(sb: SupabaseClient, row: NewCv): Promise<CvRow> {
  const { data, error } = await sb.from('cvs').insert(row).select().single()
  if (error) throw error
  return data as CvRow
}

export async function findJobByUrl(sb: SupabaseClient, url: string): Promise<JobPostingRow | null> {
  const { data, error } = await sb.from('job_postings').select('*').eq('url', url).maybeSingle()
  if (error) throw error
  return data as JobPostingRow | null
}

export async function insertJob(sb: SupabaseClient, row: NewJobPosting): Promise<JobPostingRow> {
  const { data, error } = await sb.from('job_postings').insert(row).select().single()
  if (error) throw error
  return data as JobPostingRow
}

export async function findEvaluation(
  sb: SupabaseClient, cvId: string, jobId: string
): Promise<EvaluationRow | null> {
  const { data, error } = await sb
    .from('evaluations').select('*').eq('cv_id', cvId).eq('job_id', jobId).maybeSingle()
  if (error) throw error
  return data as EvaluationRow | null
}

export async function insertEvaluation(
  sb: SupabaseClient, row: NewEvaluation
): Promise<EvaluationRow> {
  const { data, error } = await sb.from('evaluations').insert(row).select().single()
  if (error) throw error
  return data as EvaluationRow
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): Supabase data access layer"
```

---

### Task 7: Auth pages (login, register, OAuth callback) + NavBar

**Files:**
- Create: `web/src/app/login/page.tsx`, `web/src/app/register/page.tsx`, `web/src/app/auth/callback/route.ts`, `web/src/components/NavBar.tsx`
- Modify: `web/src/app/layout.tsx` (mount NavBar)
- Test: `web/src/app/login/__tests__/page.test.tsx`, `web/src/app/register/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `createClient` (browser, Task 4), `createClient` (server, Task 4), `renderWithIntl` (Task 3), `LocaleSwitcher` (Task 3), shadcn `Button`, `Card`, `Input` (Task 1).
- Produces: routes `/login`, `/register`, `/auth/callback`; `NavBar` component (locale switcher + auth-aware links); Google OAuth redirect target is `<origin>/auth/callback`, post-login destination `/dashboard`.

- [ ] **Step 1: Write the failing tests**

`web/src/app/login/__tests__/page.test.tsx`:
```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}))

const signInWithPassword = vi.fn(async () => ({ error: null }))
const signInWithOAuth = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { signInWithPassword, signInWithOAuth } }),
}))

import LoginPage from '@/app/login/page'

it('logs in with email and password then routes to dashboard', async () => {
  renderWithIntl(<LoginPage />)
  await userEvent.type(screen.getByLabelText('E-posta'), 'a@b.co')
  await userEvent.type(screen.getByLabelText('Şifre'), 'secret123')
  await userEvent.click(screen.getByRole('button', { name: 'Giriş Yap' }))
  expect(signInWithPassword).toHaveBeenCalledWith({ email: 'a@b.co', password: 'secret123' })
  expect(push).toHaveBeenCalledWith('/dashboard')
})

it('starts Google OAuth', async () => {
  renderWithIntl(<LoginPage />)
  await userEvent.click(screen.getByRole('button', { name: 'Google ile devam et' }))
  expect(signInWithOAuth).toHaveBeenCalledWith(
    expect.objectContaining({ provider: 'google' })
  )
})
```

`web/src/app/register/__tests__/page.test.tsx`:
```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

const signUp = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { signUp, signInWithOAuth: vi.fn(async () => ({ error: null })) } }),
}))

import RegisterPage from '@/app/register/page'

it('signs up with full name metadata and shows confirmation notice', async () => {
  renderWithIntl(<RegisterPage />)
  await userEvent.type(screen.getByLabelText('Ad Soyad'), 'Ada Lovelace')
  await userEvent.type(screen.getByLabelText('E-posta'), 'a@b.co')
  await userEvent.type(screen.getByLabelText('Şifre'), 'secret123')
  await userEvent.click(screen.getByRole('button', { name: 'Kayıt Ol' }))
  expect(signUp).toHaveBeenCalledWith(expect.objectContaining({
    email: 'a@b.co',
    password: 'secret123',
    options: expect.objectContaining({ data: { full_name: 'Ada Lovelace' } }),
  }))
  expect(await screen.findByText('Doğrulama bağlantısı için e-postanızı kontrol edin.')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test -- login register`
Expected: FAIL — pages do not exist

- [ ] **Step 3: Write the implementation**

`web/src/app/login/page.tsx`:
```tsx
'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export default function LoginPage() {
  const t = useTranslations('auth')
  const router = useRouter()
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      return
    }
    router.push('/dashboard')
    router.refresh()
  }

  async function google() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${location.origin}/auth/callback` },
    })
  }

  return (
    <main className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-16">
      <Card className="flex flex-col gap-4 p-6">
        <h1 className="text-xl font-semibold">{t('loginTitle')}</h1>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('emailLabel')}
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('passwordLabel')}
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit">{t('loginButton')}</Button>
        </form>
        <Button variant="outline" onClick={google}>{t('googleButton')}</Button>
        <Link href="/register" className="text-sm underline">{t('noAccount')}</Link>
      </Card>
    </main>
  )
}
```

`web/src/app/register/page.tsx`:
```tsx
'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export default function RegisterPage() {
  const t = useTranslations('auth')
  const supabase = createClient()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: `${location.origin}/auth/callback`,
      },
    })
    if (error) {
      setError(error.message)
      return
    }
    setDone(true)
  }

  async function google() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${location.origin}/auth/callback` },
    })
  }

  return (
    <main className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-16">
      <Card className="flex flex-col gap-4 p-6">
        <h1 className="text-xl font-semibold">{t('registerTitle')}</h1>
        {done ? (
          <p className="text-sm">{t('checkEmail')}</p>
        ) : (
          <>
            <form onSubmit={onSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm">
                {t('fullNameLabel')}
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t('emailLabel')}
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t('passwordLabel')}
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
              </label>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <Button type="submit">{t('registerButton')}</Button>
            </form>
            <Button variant="outline" onClick={google}>{t('googleButton')}</Button>
            <Link href="/login" className="text-sm underline">{t('haveAccount')}</Link>
          </>
        )}
      </Card>
    </main>
  )
}
```

`web/src/app/auth/callback/route.ts`:
```ts
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  if (code) {
    const supabase = await createClient()
    await supabase.auth.exchangeCodeForSession(code)
  }
  return NextResponse.redirect(`${origin}/dashboard`)
}
```

`web/src/components/NavBar.tsx`:
```tsx
'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import type { User } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/client'
import { LocaleSwitcher } from '@/components/LocaleSwitcher'
import { Button } from '@/components/ui/button'

export function NavBar() {
  const t = useTranslations('nav')
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function logout() {
    await supabase.auth.signOut()
    router.push('/')
    router.refresh()
  }

  return (
    <header className="flex items-center justify-between border-b px-6 py-3">
      <Link href="/" className="font-semibold">{t('appName')}</Link>
      <nav className="flex items-center gap-4 text-sm">
        <LocaleSwitcher />
        {user ? (
          <>
            <Link href="/dashboard">{t('dashboard')}</Link>
            <Button variant="outline" size="sm" onClick={logout}>{t('logout')}</Button>
          </>
        ) : (
          <>
            <Link href="/login">{t('login')}</Link>
            <Link href="/register">{t('register')}</Link>
          </>
        )}
      </nav>
    </header>
  )
}
```

`web/src/app/layout.tsx` (replace file — Task 3 version plus NavBar):
```tsx
import type { Metadata } from 'next'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { NavBar } from '@/components/NavBar'
import './globals.css'

export const metadata: Metadata = {
  title: 'CV-AI',
  description: 'AI-powered CV analysis and ATS conversion',
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <html lang={locale}>
      <body className="min-h-screen antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <NavBar />
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): auth pages, OAuth callback, and navbar"
```

---

### Task 8: Landing page

**Files:**
- Modify: `web/src/app/page.tsx` (replace scaffold content)
- Test: `web/src/app/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: messages (Task 3), shadcn `Button` (Task 1).
- Produces: `/` landing with product pitch and register CTA.

- [ ] **Step 1: Write the failing test**

`web/src/app/__tests__/page.test.tsx`:
```tsx
import { screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/utils'
import Home from '@/app/page'

it('renders the pitch and a register CTA', () => {
  renderWithIntl(<Home />)
  expect(screen.getByRole('heading', { name: "CV'nizi yapay zeka ile işe hazırlayın" })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Ücretsiz Başla' })).toHaveAttribute('href', '/register')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- src/app/__tests__/page`
Expected: FAIL — scaffold page has no such heading

- [ ] **Step 3: Write the implementation**

`web/src/app/page.tsx` (replace file):
```tsx
'use client'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

export default function Home() {
  const t = useTranslations('landing')
  return (
    <main className="mx-auto flex max-w-2xl flex-col items-center gap-6 px-4 py-24 text-center">
      <h1 className="text-4xl font-bold">{t('title')}</h1>
      <p className="text-lg text-muted-foreground">{t('subtitle')}</p>
      <Button asChild size="lg">
        <Link href="/register">{t('cta')}</Link>
      </Button>
    </main>
  )
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): landing page"
```

---

### Task 9: Dashboard — CV list + upload flow

**Files:**
- Create: `web/src/app/dashboard/page.tsx`, `web/src/components/CvCard.tsx`
- Test: `web/src/app/dashboard/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `listCvs`, `insertCv` (Task 6); `parseCv`, `ApiError` (Task 5); `messageKeyForCode` (Task 5); `MAX_FILE_SIZE` (Task 1); `createClient` (Task 4); messages (Task 3).
- Produces: `/dashboard` route; `CvCard({ cv }: { cv: CvRow })` linking to `/cv/<id>` and `/cv/<id>/score`, showing an "ATS" badge when `cv.is_ats`.
- Upload order (deliberate): 1) `parseCv(file)` — fail fast, no orphan files; 2) Storage upload to `<user_id>/<uuid>.pdf`; 3) `insertCv` row; 4) refresh list.

- [ ] **Step 1: Write the failing test**

`web/src/app/dashboard/__tests__/page.test.tsx`:
```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CVData } from '@/types/api'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

const upload = vi.fn(async () => ({ data: { path: 'p' }, error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

vi.mock('@/lib/db', () => ({
  listCvs: vi.fn(async () => []),
  insertCv: vi.fn(async () => ({ id: 'c1' })),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, parseCv: vi.fn() }
})

import { listCvs, insertCv } from '@/lib/db'
import { parseCv, ApiError } from '@/lib/api'
import DashboardPage from '@/app/dashboard/page'

const CV: CVData = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

beforeEach(() => vi.clearAllMocks())

it('shows the empty state when there are no CVs', async () => {
  renderWithIntl(<DashboardPage />)
  expect(await screen.findByText(/Henüz CV yüklemediniz/)).toBeInTheDocument()
})

it('parses, uploads to storage, and inserts a row on file pick', async () => {
  ;(parseCv as Mock).mockResolvedValue(CV)
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  const file = new File([new Uint8Array([1, 2])], 'cv.pdf', { type: 'application/pdf' })
  await userEvent.upload(input, file)
  await waitFor(() => expect(insertCv).toHaveBeenCalled())
  expect(parseCv).toHaveBeenCalledWith(file)
  expect(upload).toHaveBeenCalled()
  const insertedRow = (insertCv as Mock).mock.calls[0][1]
  expect(insertedRow).toMatchObject({ user_id: 'u1', is_ats: false, parsed_data: CV })
  expect(insertedRow.file_path.startsWith('u1/')).toBe(true)
  expect(listCvs).toHaveBeenCalledTimes(2) // initial load + refresh
})

it('shows a localized error when the API rejects the PDF', async () => {
  ;(parseCv as Mock).mockRejectedValue(new ApiError('SCANNED_PDF', 400))
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  await userEvent.upload(input, new File([new Uint8Array([1])], 'cv.pdf', { type: 'application/pdf' }))
  expect(await screen.findByText(/taranmış görünüyor/)).toBeInTheDocument()
  expect(insertCv).not.toHaveBeenCalled()
})

it('rejects oversized files client-side', async () => {
  renderWithIntl(<DashboardPage />)
  const input = await screen.findByLabelText('CV Yükle (PDF)')
  const big = new File([new ArrayBuffer(10 * 1024 * 1024 + 1)], 'cv.pdf', { type: 'application/pdf' })
  await userEvent.upload(input, big)
  expect(await screen.findByText(/10 MB/)).toBeInTheDocument()
  expect(parseCv).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- dashboard`
Expected: FAIL — page does not exist

- [ ] **Step 3: Write the implementation**

`web/src/components/CvCard.tsx`:
```tsx
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import type { CvRow } from '@/types/db'
import { Card } from '@/components/ui/card'

export function CvCard({ cv }: { cv: CvRow }) {
  const t = useTranslations('dashboard')
  return (
    <Card className="flex items-center justify-between p-4">
      <div className="flex items-center gap-2">
        <span className="font-medium">{cv.parsed_data.full_name}</span>
        {cv.is_ats && (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-semibold text-emerald-800">
            {t('atsBadge')}
          </span>
        )}
      </div>
      <div className="flex gap-3 text-sm">
        <Link className="underline" href={`/cv/${cv.id}`}>{t('viewAction')}</Link>
        <Link className="underline" href={`/cv/${cv.id}/score`}>{t('scoreAction')}</Link>
      </div>
    </Card>
  )
}
```

`web/src/app/dashboard/page.tsx`:
```tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { insertCv, listCvs } from '@/lib/db'
import { ApiError, parseCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { MAX_FILE_SIZE } from '@/lib/constants'
import type { CvRow } from '@/types/db'
import { CvCard } from '@/components/CvCard'

export default function DashboardPage() {
  const t = useTranslations()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setCvs(await listCvs(supabase))
  }, [supabase])

  useEffect(() => {
    load()
  }, [load])

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setError(null)
    if (file.type !== 'application/pdf') {
      setError(t('errors.INVALID_PDF'))
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setError(t('errors.FILE_TOO_LARGE'))
      return
    }
    setBusy(true)
    try {
      const parsed = await parseCv(file) // parse first: a rejected PDF leaves no orphan file
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)
      const path = `${user.id}/${crypto.randomUUID()}.pdf`
      const { error: upErr } = await supabase.storage.from('cvs').upload(path, file)
      if (upErr) throw upErr
      await insertCv(supabase, {
        user_id: user.id, file_path: path, parsed_data: parsed, is_ats: false, source_cv_id: null,
      })
      await load()
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('dashboard.title')}</h1>
        <label className="cursor-pointer rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
          {busy ? t('dashboard.uploading') : t('dashboard.upload')}
          <input
            type="file"
            accept="application/pdf"
            className="sr-only"
            aria-label={t('dashboard.upload')}
            disabled={busy}
            onChange={onFile}
          />
        </label>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {cvs === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : cvs.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('dashboard.empty')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {cvs.map((cv) => <CvCard key={cv.id} cv={cv} />)}
        </div>
      )}
    </main>
  )
}
```

Note: the upload `<label>` text switches to `dashboard.uploading` while busy — the test targets the input by `aria-label`, which stays `dashboard.upload`.

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): dashboard with CV upload and parse flow"
```

---

### Task 10: CV detail page — preview + ATS convert + PDF download

**Files:**
- Create: `web/src/app/cv/[id]/page.tsx`, `web/src/lib/download.ts`
- Test: `web/src/app/cv/[id]/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `getCv`, `insertCv` (Task 6); `atsRewrite`, `atsPdf`, `ApiError` (Task 5); `messageKeyForCode` (Task 5); `createClient` (Task 4); `useLocale` (next-intl); messages (Task 3).
- Produces: `/cv/[id]` route; `downloadBlob(blob: Blob, filename: string): void` from `@/lib/download`.
- ATS flow (deliberate order): `atsRewrite(parsed_data, locale)` → `atsPdf(rewritten, locale)` → upload PDF to `<user_id>/<uuid>-ats.pdf` → `insertCv` with `is_ats: true, source_cv_id: <original id>` → `downloadBlob`.

- [ ] **Step 1: Write the failing test**

`web/src/app/cv/[id]/__tests__/page.test.tsx`:
```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
}))

const upload = vi.fn(async () => ({ data: { path: 'p' }, error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const ROW: CvRow = {
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada Lovelace', email: 'ada@example.com', phone: null, location: 'London',
    summary: 'Engineer.', experiences: [{ title: 'Dev', company: 'AEC', start_date: '2020', end_date: '2024', description: null }],
    education: [], skills: ['Python'], languages: [], certifications: [],
  },
}

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
  insertCv: vi.fn(async () => ({ ...ROW, id: 'c2', is_ats: true })),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, atsRewrite: vi.fn(), atsPdf: vi.fn() }
})

vi.mock('@/lib/download', () => ({ downloadBlob: vi.fn() }))

import { insertCv } from '@/lib/db'
import { atsPdf, atsRewrite } from '@/lib/api'
import { downloadBlob } from '@/lib/download'
import CvDetailPage from '@/app/cv/[id]/page'

beforeEach(() => vi.clearAllMocks())

it('renders the parsed CV preview', async () => {
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  expect(screen.getByText(/Dev — AEC/)).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
})

it('converts to ATS: rewrite, pdf, storage, new row, download', async () => {
  ;(atsRewrite as Mock).mockResolvedValue(ROW.parsed_data)
  ;(atsPdf as Mock).mockResolvedValue(new Blob([new Uint8Array([1])], { type: 'application/pdf' }))
  renderWithIntl(<CvDetailPage />)
  await userEvent.click(await screen.findByRole('button', { name: "ATS'ye Dönüştür" }))
  await waitFor(() => expect(downloadBlob).toHaveBeenCalled())
  expect(atsRewrite).toHaveBeenCalledWith(ROW.parsed_data, 'tr')
  expect(atsPdf).toHaveBeenCalled()
  expect(upload).toHaveBeenCalled()
  const inserted = (insertCv as Mock).mock.calls[0][1]
  expect(inserted).toMatchObject({ is_ats: true, source_cv_id: 'c1', user_id: 'u1' })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- "cv/\[id\]"`
(If the bracket glob misbehaves in PowerShell, run `npm run test` — only the new file fails.)
Expected: FAIL — page does not exist

- [ ] **Step 3: Write the implementation**

`web/src/lib/download.ts`:
```ts
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
```

`web/src/app/cv/[id]/page.tsx`:
```tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import { getCv, insertCv } from '@/lib/db'
import { ApiError, atsPdf, atsRewrite } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { downloadBlob } from '@/lib/download'
import type { CvRow } from '@/types/db'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export default function CvDetailPage() {
  const t = useTranslations()
  const locale = useLocale()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setCv(await getCv(supabase, id))
  }, [supabase, id])

  useEffect(() => {
    load()
  }, [load])

  async function convert() {
    if (!cv) return
    setError(null)
    setBusy(true)
    try {
      const rewritten = await atsRewrite(cv.parsed_data, locale)
      const pdf = await atsPdf(rewritten, locale)
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)
      const path = `${user.id}/${crypto.randomUUID()}-ats.pdf`
      const { error: upErr } = await supabase.storage
        .from('cvs')
        .upload(path, pdf, { contentType: 'application/pdf' })
      if (upErr) throw upErr
      await insertCv(supabase, {
        user_id: user.id, file_path: path, parsed_data: rewritten,
        is_ats: true, source_cv_id: cv.id,
      })
      downloadBlob(pdf, 'cv-ats.pdf')
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
  }

  if (!cv) {
    return <main className="px-4 py-10 text-sm text-muted-foreground">{t('common.loading')}</main>
  }

  const d = cv.parsed_data
  const contact = [d.email, d.phone, d.location].filter(Boolean).join(' | ')

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{d.full_name}</h1>
        <div className="flex gap-2">
          <Button onClick={convert} disabled={busy}>
            {busy ? t('cv.converting') : t('cv.convertAts')}
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/cv/${cv.id}/score`}>{t('cv.scoreCta')}</Link>
          </Button>
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {contact && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.contact')}</h2>
          <p className="text-sm">{contact}</p>
        </Card>
      )}
      {d.summary && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.summary')}</h2>
          <p className="text-sm">{d.summary}</p>
        </Card>
      )}
      {d.experiences.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.experience')}</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {d.experiences.map((e, i) => (
              <li key={i}>
                <span className="font-medium">{e.title} — {e.company}</span>
                {(e.start_date || e.end_date) && (
                  <span className="text-muted-foreground"> ({e.start_date ?? ''} - {e.end_date ?? ''})</span>
                )}
                {e.description && <p>{e.description}</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {d.education.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.education')}</h2>
          <ul className="text-sm">
            {d.education.map((e, i) => (
              <li key={i}>{e.degree} — {e.school}{e.year ? ` (${e.year})` : ''}</li>
            ))}
          </ul>
        </Card>
      )}
      {d.skills.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.skills')}</h2>
          <ul className="flex flex-wrap gap-2 text-sm">
            {d.skills.map((s) => (
              <li key={s} className="rounded bg-muted px-2 py-0.5">{s}</li>
            ))}
          </ul>
        </Card>
      )}
      {d.languages.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.languages')}</h2>
          <p className="text-sm">{d.languages.join(', ')}</p>
        </Card>
      )}
      {d.certifications.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-1 font-medium">{t('cv.certifications')}</h2>
          <p className="text-sm">{d.certifications.join(', ')}</p>
        </Card>
      )}
    </main>
  )
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): CV detail with ATS conversion and PDF download"
```

---

### Task 11: Score page — URL input, paste fallback, evaluation cache

**Files:**
- Create: `web/src/app/cv/[id]/score/page.tsx`
- Test: `web/src/app/cv/[id]/score/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `getCv`, `findJobByUrl`, `insertJob`, `findEvaluation`, `insertEvaluation` (Task 6); `fetchJob`, `scoreCv`, `ApiError` (Task 5); `StarRating` (Task 1); messages (Task 3).
- Produces: `/cv/[id]/score` route.
- Flow (deliberate): submit → `fetchJob({url})` or `fetchJob({text})` → find-or-insert `job_postings` row (by URL for `fetch_method === 'url'`; always insert for manual) → `findEvaluation(cv_id, job_id)`; hit ⇒ show cached (no `/score` call, `score.cached` notice); miss ⇒ `scoreCv` → `insertEvaluation` → show. `FETCH_FAILED` ⇒ reveal paste textarea (`score.pasteFallbackNotice`).

- [ ] **Step 1: Write the failing test**

`web/src/app/cv/[id]/score/__tests__/page.test.tsx`:
```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow, EvaluationRow, JobPostingRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
  }),
}))

const ROW: CvRow = {
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: ['Python'], languages: [], certifications: [],
  },
}

const JOB: JobPostingRow = {
  id: 'j1', user_id: 'u1', url: 'https://x.co/1', title: 'Dev', company: 'Acme',
  description: 'desc', fetch_method: 'url', created_at: '2026-07-12T00:00:00Z',
}

const EVAL: EvaluationRow = {
  id: 'e1', cv_id: 'c1', job_id: 'j1', percent: 78, stars: 4,
  strengths: ['Python'], gaps: ['SQL'], suggestions: ['Add projects'],
  created_at: '2026-07-12T00:00:00Z',
}

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
  findJobByUrl: vi.fn(async () => null),
  insertJob: vi.fn(async () => JOB),
  findEvaluation: vi.fn(async () => null),
  insertEvaluation: vi.fn(async () => EVAL),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, fetchJob: vi.fn(), scoreCv: vi.fn() }
})

import { findEvaluation, findJobByUrl, insertEvaluation, insertJob } from '@/lib/db'
import { ApiError, fetchJob, scoreCv } from '@/lib/api'
import ScorePage from '@/app/cv/[id]/score/page'

const FETCHED = {
  criteria: { title: 'Dev', company: 'Acme', requirements: ['Python'], skills: ['Python'] },
  description: 'desc', fetch_method: 'url' as const,
}

beforeEach(() => vi.clearAllMocks())

it('scores a URL posting and shows stars with reasons', async () => {
  ;(fetchJob as Mock).mockResolvedValue(FETCHED)
  ;(scoreCv as Mock).mockResolvedValue({
    percent: 78, stars: 4, strengths: ['Python'], gaps: ['SQL'], suggestions: ['Add projects'],
  })
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://x.co/1')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByLabelText('4/5')).toBeInTheDocument()
  expect(screen.getByText('%78')).toBeInTheDocument()
  expect(screen.getByText('SQL')).toBeInTheDocument()
  expect(insertJob).toHaveBeenCalled()
  expect(insertEvaluation).toHaveBeenCalled()
})

it('returns the cached evaluation without calling /score again', async () => {
  ;(fetchJob as Mock).mockResolvedValue(FETCHED)
  ;(findJobByUrl as Mock).mockResolvedValue(JOB)
  ;(findEvaluation as Mock).mockResolvedValue(EVAL)
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://x.co/1')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByLabelText('4/5')).toBeInTheDocument()
  expect(screen.getByText(/önceki sonuç/)).toBeInTheDocument()
  expect(scoreCv).not.toHaveBeenCalled()
  expect(insertEvaluation).not.toHaveBeenCalled()
})

it('falls back to paste mode when the fetch fails', async () => {
  ;(fetchJob as Mock).mockRejectedValueOnce(new ApiError('FETCH_FAILED', 422))
  renderWithIntl(<ScorePage />)
  await userEvent.type(await screen.findByLabelText('İş ilanı bağlantısı'), 'https://linkedin.com/x')
  await userEvent.click(screen.getByRole('button', { name: 'Skorla' }))
  expect(await screen.findByText(/yapıştırın/)).toBeInTheDocument()
  expect(screen.getByLabelText('İlan metni')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test` (new file is the only failure)
Expected: FAIL — page does not exist

- [ ] **Step 3: Write the implementation**

`web/src/app/cv/[id]/score/page.tsx`:
```tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { createClient } from '@/lib/supabase/client'
import {
  findEvaluation, findJobByUrl, getCv, insertEvaluation, insertJob,
} from '@/lib/db'
import { ApiError, fetchJob, scoreCv } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import type { CvRow, EvaluationRow } from '@/types/db'
import { StarRating } from '@/components/StarRating'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

export default function ScorePage() {
  const t = useTranslations()
  const { id } = useParams<{ id: string }>()
  const [supabase] = useState(createClient)
  const [cv, setCv] = useState<CvRow | null>(null)
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [showPaste, setShowPaste] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EvaluationRow | null>(null)
  const [cached, setCached] = useState(false)

  const load = useCallback(async () => {
    setCv(await getCv(supabase, id))
  }, [supabase, id])

  useEffect(() => {
    load()
  }, [load])

  async function run(e: React.FormEvent) {
    e.preventDefault()
    if (!cv) return
    setError(null)
    setResult(null)
    setCached(false)
    setBusy(true)
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new ApiError('NOT_AUTHENTICATED', 401)

      const useText = showPaste && text.trim().length > 0
      const fetched = await fetchJob(useText ? { text } : { url })

      let job = fetched.fetch_method === 'url' ? await findJobByUrl(supabase, url) : null
      if (!job) {
        job = await insertJob(supabase, {
          user_id: user.id,
          url: fetched.fetch_method === 'url' ? url : null,
          title: fetched.criteria.title,
          company: fetched.criteria.company,
          description: fetched.description,
          fetch_method: fetched.fetch_method,
        })
      }

      const existing = await findEvaluation(supabase, cv.id, job.id)
      if (existing) {
        setResult(existing)
        setCached(true)
        return
      }

      const ev = await scoreCv(cv.parsed_data, fetched.criteria)
      const row = await insertEvaluation(supabase, { cv_id: cv.id, job_id: job.id, ...ev })
      setResult(row)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'FETCH_FAILED') {
        setShowPaste(true)
        setError(t('score.pasteFallbackNotice'))
      } else {
        setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
      }
    } finally {
      setBusy(false)
    }
  }

  if (!cv) {
    return <main className="px-4 py-10 text-sm text-muted-foreground">{t('common.loading')}</main>
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-10">
      <h1 className="text-2xl font-semibold">{t('score.title')} — {cv.parsed_data.full_name}</h1>

      <form onSubmit={run} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('score.urlLabel')}
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        {showPaste && (
          <label className="flex flex-col gap-1 text-sm">
            {t('score.pasteLabel')}
            <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
        )}
        {error && <p className="text-sm text-amber-700">{error}</p>}
        <Button type="submit" disabled={busy}>
          {busy ? t('score.scoring') : t('score.scoreButton')}
        </Button>
      </form>

      {result && (
        <Card className="flex flex-col gap-3 p-6">
          {cached && <p className="text-sm text-muted-foreground">{t('score.cached')}</p>}
          <div className="flex items-center gap-3">
            <StarRating stars={result.stars} />
            <span className="text-2xl font-bold">%{result.percent}</span>
          </div>
          <section>
            <h2 className="font-medium">{t('score.strengths')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.strengths.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t('score.gaps')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.gaps.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t('score.suggestions')}</h2>
            <ul className="list-disc pl-5 text-sm">
              {result.suggestions.map((s) => <li key={s}>{s}</li>)}
            </ul>
          </section>
        </Card>
      )}
    </main>
  )
}
```

- [ ] **Step 4: Verify tests + typecheck pass**

Run: `npm run test` then `npm run typecheck`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add web
git commit -m "feat(web): job fit scoring page with paste fallback and cache"
```

---

### Task 12: Playwright smoke (gated), README, full verification

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/smoke.spec.ts`, `web/README.md`
- Test: the whole suite (vitest + typecheck + api pytest + gated e2e)

**Interfaces:**
- Consumes: everything above.
- Produces: `npm run e2e` (skips politely without `E2E_BASE_URL`); `web/README.md` with setup/run instructions; final green state for both `web/` and `api/`.

- [ ] **Step 1: Add Playwright**

```powershell
npm i -D @playwright/test
npx playwright install chromium
```

`web/playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' },
})
```

`web/e2e/smoke.spec.ts`:
```ts
import { expect, test } from '@playwright/test'

// Full journey (register → upload → score → convert) needs live Supabase + OpenAI;
// run manually against a deployed stack. This smoke only needs the app server.
test.skip(!process.env.E2E_BASE_URL, 'set E2E_BASE_URL to run the smoke test')

test('landing renders with a register CTA', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: /Ücretsiz Başla|Start for free/ })).toBeVisible()
})

test('anonymous /dashboard redirects to /login', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
})
```

Add to `web/package.json` scripts: `"e2e": "playwright test"`.

- [ ] **Step 2: Write the README**

`web/README.md`:
```markdown
# CV-AI Web

Next.js 15 frontend for CV-AI: upload a PDF CV, score it against a job posting,
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
```

- [ ] **Step 3: Full verification**

```powershell
npm run test
npm run typecheck
npm run build
cd ..\api
.\.venv\Scripts\python.exe -m pytest -q
```
Expected: vitest all green, typecheck clean, `next build` succeeds, api suite still 44 passed.

- [ ] **Step 4: Commit**

```powershell
cd ..
git add web
git commit -m "feat(web): Playwright smoke, README, final verification"
```

---

## Post-plan notes

- **Deployment (out of task scope, do when ready):** Vercel for `web/` (set the three `NEXT_PUBLIC_*` env vars), Railway for `api/` (set `OPENAI_API_KEY`, `SUPABASE_JWT_SECRET`), then add the Vercel origin to the API's CORS `allow_origins` list in `api/app/main.py`.
- **Manual E2E checklist (needs live Supabase + OpenAI):** register with email → confirm → login → upload a text PDF → see parsed preview → score against a real posting URL → re-score same pair (expect cached notice) → convert to ATS → PDF downloads and a new ATS-badged card appears on the dashboard.
