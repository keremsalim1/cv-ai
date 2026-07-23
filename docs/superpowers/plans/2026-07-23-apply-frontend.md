# Apply Frontend (Faz 2B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/optimize` page that consumes the Faz 2A apply backend — pick a CV + job link, LLM-optimize the CV and answer the form, review/edit on an approval screen, then auto-submit or take delivery — and record every application to a new `applications` table.

**Architecture:** One `/optimize` route as a client state machine (`form → preparing → login → approve → submitting → result`), following the existing `/ats` and `/score` page patterns. Prop-driven child components (`ApprovalScreen`, `ResultScreen`, `OptimizeForm`, `LoginPrompt`, `RecentApplications`) are each testable in isolation; the page orchestrates them. A small backend addendum makes `/apply/prepare` optimize the CV even on captcha/form-not-found pages so delivery mode always has content.

**Tech Stack:** Next.js (App Router — see per-task Next.js note), React client components, next-intl, Tailwind, Supabase (Postgres + storage + RLS), Vitest + Testing Library; FastAPI + pytest for the backend task.

## Global Constraints

- Working dir: `C:\Users\ASUS\Desktop\cv-ai` (capital **D**). Web commands run in `web/`; API commands run in `api/` with `.venv\Scripts\python`.
- **Next.js is non-standard:** `web/CLAUDE.md` → `web/AGENTS.md` require reading the relevant guide in `web/node_modules/next/dist/docs/` before writing Next.js code. Any component using `useSearchParams` MUST be wrapped in `<Suspense>` (see `/ats` page).
- Optimized CVs are saved to `cvs` with `is_ats=false` and `source_cv_id=<selected CV id>` (job-specific copy, distinct from ATS copies).
- The apply-flow statuses (`ready`/`login_required`/`captcha`/`form_not_found`/`submitted`/`failed`) are fields inside 200-responses, NOT `ApiError` codes — handle them as UI state with `optimize.*` messages, not `errors.*`.
- Every new i18n key MUST be added to BOTH `web/src/messages/en.json` and `tr.json` (the parity test enforces this).
- TDD: write the failing test first, watch it fail, implement, watch it pass, commit. Commit after each task.

---

### Task 1: Backend — optimize on captcha/form_not_found too

**Files:**
- Modify: `api/app/services/apply.py` (`prepare_application`)
- Modify: `api/tests/test_apply_prepare.py`

**Interfaces:**
- Consumes: existing `_page_state`, `_wait_for_login`, `detect_captcha`, `detect_login`, `enforce_limit`, `usage_store`, `PrepareIn`, `PrepareOut`, `MODEL_SMART`.
- Produces: `/apply/prepare` now returns the full optimized payload (`form`, `cv`, `changes`, `cover_letter`, `answers`, `job_text`) for `status` in `ready | captcha | form_not_found`; `login_required` still returns only `{status}`. Consumed by Task 2's `applyPrepare`.

- [ ] **Step 1: Update the prepare tests to the new contract**

Replace the bodies of `test_prepare_captcha` and `test_prepare_form_not_found` in `api/tests/test_apply_prepare.py`, and add a credit-consumption assertion. Replace these two functions:

```python
def test_prepare_captcha(client, auth_headers):
    _use_driver(FakeDriver([_html("captcha_page.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "captcha"
    # captcha still optimizes so delivery mode has content
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["cover_letter"].startswith("I am excited")
    assert any(f["id"] == "full_name" for f in body["form"])


def test_prepare_form_not_found(client, auth_headers):
    _use_driver(FakeDriver(["<html><body><h1>Job</h1><p>" + "desc " * 60 + "</p></body></html>"]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "form_not_found"
    assert body["form"] == []
    # no form, but the optimized CV + cover letter are still delivered
    assert body["cv"]["full_name"] == "Ada Lovelace"
    assert body["cover_letter"].startswith("I am excited")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in `api/`): `.venv\Scripts\python -m pytest tests/test_apply_prepare.py -q`
Expected: FAIL — captcha/form_not_found currently return only `{status, job_text}`, so `body["cv"]` raises `KeyError` / assertion fails.

- [ ] **Step 3: Restructure `prepare_application`**

In `api/app/services/apply.py`, replace the body of `prepare_application` from the `is_login, schema = _page_state(html)` line through the end of the `try` block (the `return {...}` for `ready`) with:

```python
        is_login, schema = _page_state(html)
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login = detect_login(html)
        # A login wall means the page isn't visible yet — we can't optimize it.
        if is_login:
            return {"status": "login_required"}

        # The page IS visible. Optimize + answer in one LLM call regardless of
        # captcha/form presence; `status` only signals whether auto-submit works.
        if detect_captcha(html):
            status = "captcha"
        elif not schema.fields:
            status = "form_not_found"
        else:
            status = "ready"

        # Charge one AI credit now that we're actually calling the LLM.
        enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
        job_text = _job_text(html)
        user_payload = PrepareIn(cv=cv, job_text=job_text,
                                 form=schema.fields).model_dump_json()
        out = llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                            user_payload, PrepareOut)
        return {
            "status": status,
            "form": [f.model_dump() for f in schema.fields],
            "cv": out.cv.model_dump(),
            "changes": out.changes,
            "cover_letter": out.cover_letter,
            "answers": [a.model_dump() for a in out.answers],
            "job_text": job_text,
        }
```

(This removes the two early `captcha`/`form_not_found` returns; `login_required` is now checked before captcha.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_apply_prepare.py -q`
Expected: PASS (9 tests). Then full API suite: `.venv\Scripts\python -m pytest -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/apply.py api/tests/test_apply_prepare.py
git commit -m "feat(api): /apply/prepare optimizes CV on captcha/form_not_found too"
```

---

### Task 2: Web — apply API client + types

**Files:**
- Modify: `web/src/types/api.ts` (append apply types)
- Modify: `web/src/lib/api.ts` (append `applyPrepare`, `applySubmit`)
- Modify: `web/src/lib/__tests__/api.test.ts` (append tests)

**Interfaces:**
- Consumes: existing `apiUrl`, `authHeaders`, `ensureOk`, `ApiError`, `CVData`.
- Produces (used by Tasks 4-6):
  - Types `FieldType`, `FormField`, `FieldAnswer`, `OptimizedPayload`, `PrepareResult`, `SubmitResult`.
  - `applyPrepare(cv: CVData, url: string, language: string, headed?: boolean): Promise<PrepareResult>`
  - `applySubmit(cv: CVData, url: string, language: string, answers: FieldAnswer[], headed?: boolean): Promise<SubmitResult>`

- [ ] **Step 1: Append the apply types**

Append to `web/src/types/api.ts`:

```ts
export type FieldType = 'text' | 'textarea' | 'select' | 'radio' | 'checkbox' | 'file'

export interface FormField {
  id: string
  selector: string
  label: string
  type: FieldType
  options: string[]
  option_selectors: string[]
  required: boolean
}

export interface FieldAnswer {
  field_id: string
  value: string
}

// ready/captcha/form_not_found share this payload; `status` only gates auto-submit.
export interface OptimizedPayload {
  form: FormField[]
  cv: CVData
  changes: string[]
  cover_letter: string | null
  answers: FieldAnswer[]
  job_text: string
}

export type PrepareResult =
  | ({ status: 'ready' } & OptimizedPayload)
  | ({ status: 'captcha' } & OptimizedPayload)
  | ({ status: 'form_not_found' } & OptimizedPayload)
  | { status: 'login_required' }

export type SubmitResult =
  | { status: 'submitted'; screenshot: string }
  | { status: 'failed'; reason: string }
  | { status: 'login_required' }
  | { status: 'captcha' }
```

- [ ] **Step 2: Write the failing api-client tests**

Append to `web/src/lib/__tests__/api.test.ts` (the `CV` const and `jsonResponse` helper already exist in this file):

```ts
it('applyPrepare posts cv+url+language+headed and returns the result', async () => {
  const { applyPrepare } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    status: 'ready', form: [], cv: CV, changes: [], cover_letter: null, answers: [], job_text: 'jt',
  }))
  const out = await applyPrepare(CV, 'https://j.com/1', 'en', true)
  expect(out.status).toBe('ready')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/prepare')
  expect(JSON.parse(init.body as string)).toEqual({
    cv: CV, url: 'https://j.com/1', language: 'en', headed: true,
  })
})

it('applySubmit posts answers and defaults headed to false', async () => {
  const { applySubmit } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { status: 'submitted', screenshot: 'AAA' }))
  const out = await applySubmit(CV, 'https://j.com/1', 'en', [{ field_id: 'x', value: 'y' }])
  expect(out).toMatchObject({ status: 'submitted', screenshot: 'AAA' })
  const [, init] = (global.fetch as Mock).mock.calls[0]
  expect(JSON.parse(init.body as string)).toEqual({
    cv: CV, url: 'https://j.com/1', language: 'en',
    answers: [{ field_id: 'x', value: 'y' }], headed: false,
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run (in `web/`): `npx vitest run src/lib/__tests__/api.test.ts`
Expected: FAIL — `applyPrepare`/`applySubmit` are not exported.

- [ ] **Step 4: Implement the client functions**

Append to `web/src/lib/api.ts` (add `FieldAnswer, PrepareResult, SubmitResult` to the existing `import type ... from '@/types/api'` line):

```ts
export async function applyPrepare(
  cv: CVData, url: string, language: string, headed = false
): Promise<PrepareResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/prepare'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, url, language, headed }),
    })
  )
  return res.json()
}

export async function applySubmit(
  cv: CVData, url: string, language: string, answers: FieldAnswer[], headed = false
): Promise<SubmitResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/submit'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv, url, language, answers, headed }),
    })
  )
  return res.json()
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npx vitest run src/lib/__tests__/api.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/types/api.ts web/src/lib/api.ts web/src/lib/__tests__/api.test.ts
git commit -m "feat(web): applyPrepare/applySubmit API client and apply types"
```

---

### Task 3: Web — `applications` table + data layer

**Files:**
- Create: `supabase/migrations/0002_applications.sql`
- Modify: `web/src/types/db.ts` (append `ApplicationRow`, `NewApplication`)
- Modify: `web/src/lib/db.ts` (append `insertApplication`, `listApplications`)
- Modify: `web/src/lib/__tests__/db.test.ts` (append tests)

**Interfaces:**
- Consumes: existing `stubClient` test helper, `SupabaseClient`.
- Produces (used by Tasks 5-7): `ApplicationRow`, `NewApplication`; `insertApplication(sb, row): Promise<ApplicationRow>`; `listApplications(sb): Promise<ApplicationRow[]>` (newest first).

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/0002_applications.sql`:

```sql
-- KRESUME.ai Faz 2B: application history

create table public.applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  cv_id uuid references public.cvs (id) on delete set null,
  optimized_cv_id uuid references public.cvs (id) on delete set null,
  url text not null,
  job_text text,
  cover_letter text,
  qa jsonb not null default '{}',
  changes jsonb not null default '[]',
  status text not null check (status in ('submitted', 'delivered', 'failed')),
  created_at timestamptz not null default now()
);

alter table public.applications enable row level security;

create policy "own applications" on public.applications
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
```

- [ ] **Step 2: Append the DB types**

Append to `web/src/types/db.ts`:

```ts
export interface ApplicationRow {
  id: string
  user_id: string
  cv_id: string | null
  optimized_cv_id: string | null
  url: string
  job_text: string | null
  cover_letter: string | null
  qa: unknown
  changes: string[]
  status: 'submitted' | 'delivered' | 'failed'
  created_at: string
}
export type NewApplication = Omit<ApplicationRow, 'id' | 'created_at'>
```

- [ ] **Step 3: Write the failing DB tests**

Append to `web/src/lib/__tests__/db.test.ts` (import the new functions on line 2: `import { findEvaluation, insertApplication, insertCv, listApplications, listCvs } from '@/lib/db'`):

```ts
it('listApplications queries applications newest first', async () => {
  const rows = [{ id: 'a1' }]
  const { sb, from, q } = stubClient({ data: rows, error: null })
  await expect(listApplications(sb)).resolves.toEqual(rows)
  expect(from).toHaveBeenCalledWith('applications')
  expect(q.order).toHaveBeenCalledWith('created_at', { ascending: false })
})

it('insertApplication returns the inserted row', async () => {
  const row = { id: 'a2' }
  const { sb } = stubClient({ data: row, error: null })
  await expect(insertApplication(sb, {
    user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'c2', url: 'https://x', job_text: null,
    cover_letter: null, qa: {}, changes: [], status: 'delivered',
  })).resolves.toEqual(row)
})
```

- [ ] **Step 4: Run the tests to verify they fail**

Run (in `web/`): `npx vitest run src/lib/__tests__/db.test.ts`
Expected: FAIL — `insertApplication`/`listApplications` are not exported.

- [ ] **Step 5: Implement the DB functions**

Append to `web/src/lib/db.ts` (add `ApplicationRow, NewApplication` to the `import type ... from '@/types/db'` block):

```ts
export async function listApplications(sb: SupabaseClient): Promise<ApplicationRow[]> {
  const { data, error } = await sb
    .from('applications').select('*').order('created_at', { ascending: false })
  if (error) throw error
  return (data ?? []) as ApplicationRow[]
}

export async function insertApplication(
  sb: SupabaseClient, row: NewApplication
): Promise<ApplicationRow> {
  const { data, error } = await sb.from('applications').insert(row).select().single()
  if (error) throw error
  return data as ApplicationRow
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx vitest run src/lib/__tests__/db.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/0002_applications.sql web/src/types/db.ts web/src/lib/db.ts web/src/lib/__tests__/db.test.ts
git commit -m "feat(web): applications table migration + insert/list data layer"
```

---

### Task 4: Web — ApprovalScreen + FormAnswerField

**Files:**
- Create: `web/src/components/apply/FormAnswerField.tsx`
- Create: `web/src/components/apply/ApprovalScreen.tsx`
- Create: `web/src/components/apply/__tests__/ApprovalScreen.test.tsx`
- Modify: `web/src/messages/en.json`, `web/src/messages/tr.json` (add `optimize` section)

**Interfaces:**
- Consumes: `FormField`, `FieldAnswer`, `OptimizedPayload`, `CVData` from `@/types/api`; `Button` from `@/components/ui/button`; `ui/textarea`.
- Produces (used by Task 6): `ApprovalScreen` with props
  `{ payload: OptimizedPayload; canSubmit: boolean; onSubmit: (answers: FieldAnswer[], coverLetter: string) => void; onDeliver: (answers: FieldAnswer[], coverLetter: string) => void }`.
  `canSubmit` is `true` only for `status==='ready'`.

- [ ] **Step 1: Add the `optimize` i18n keys (both languages)**

In `web/src/messages/en.json`, add a top-level `"optimize"` section (after `"ats"`):

```json
"optimize": {
  "title": "Optimize & Apply",
  "intro": "Pick a CV and paste a job application link. We tailor the CV to the posting, draft answers to the form, and let you review everything before applying.",
  "link": "Application link",
  "linkPlaceholder": "https://company.com/jobs/123/apply",
  "language": "Output language",
  "prepare": "Prepare",
  "preparing": "Reading the page and optimizing…",
  "loginTitle": "Sign-in required",
  "loginIntro": "This page needs you to sign in. We'll open a visible browser window — sign in there, and we continue automatically. Your password is never sent to us.",
  "loginButton": "Sign in the window and continue",
  "loginWaiting": "Waiting for sign-in in the browser window…",
  "approveTitle": "Review before applying",
  "changes": "What changed",
  "coverLetter": "Cover letter",
  "formAnswers": "Application form answers",
  "requiredEmpty": "You need to fill this in",
  "fileNote": "Your CV will be uploaded automatically as an ATS PDF.",
  "submit": "Approve & apply",
  "deliver": "Just hand it to me",
  "submitting": "Filling the form and submitting…",
  "deliverModeNote": "This page can't be submitted automatically (sign-in loop, CAPTCHA, or no form found). You can take the materials below.",
  "resultSubmitted": "Applied! Here's the confirmation screenshot.",
  "resultDelivered": "Ready. Your optimized CV was saved to your dashboard.",
  "downloadPdf": "Download ATS PDF",
  "copyCoverLetter": "Copy cover letter",
  "copyAnswers": "Copy answers",
  "copied": "Copied",
  "recent": "Recent applications",
  "recentEmpty": "No applications yet.",
  "statusSubmitted": "Submitted",
  "statusDelivered": "Delivered",
  "statusFailed": "Delivered (auto-submit failed)"
}
```

In `web/src/messages/tr.json`, add the matching section:

```json
"optimize": {
  "title": "Optimize & Başvur",
  "intro": "Bir CV seçin ve başvuru linkini yapıştırın. CV'yi ilana göre uyarlar, form sorularını cevaplar ve başvurmadan önce her şeyi incelemenizi sağlarız.",
  "link": "Başvuru linki",
  "linkPlaceholder": "https://sirket.com/ilan/123/basvur",
  "language": "Çıktı dili",
  "prepare": "Hazırla",
  "preparing": "Sayfa okunuyor ve optimize ediliyor…",
  "loginTitle": "Giriş gerekiyor",
  "loginIntro": "Bu sayfa giriş yapmanızı istiyor. Görünür bir tarayıcı penceresi açacağız — oradan giriş yapın, akış otomatik devam etsin. Şifreniz bize hiçbir zaman gönderilmez.",
  "loginButton": "Pencerede giriş yap ve devam et",
  "loginWaiting": "Tarayıcı penceresinde giriş bekleniyor…",
  "approveTitle": "Başvurmadan önce inceleyin",
  "changes": "Neler değişti",
  "coverLetter": "Motivasyon mektubu",
  "formAnswers": "Başvuru formu cevapları",
  "requiredEmpty": "Bu alanı doldurmanız gerekiyor",
  "fileNote": "CV'niz ATS PDF olarak otomatik yüklenecek.",
  "submit": "Onayla ve Başvur",
  "deliver": "Sadece bana teslim et",
  "submitting": "Form dolduruluyor ve gönderiliyor…",
  "deliverModeNote": "Bu sayfa otomatik gönderime uygun değil (giriş döngüsü, CAPTCHA veya form bulunamadı). Aşağıdaki materyalleri alabilirsiniz.",
  "resultSubmitted": "Başvuruldu! İşte gönderim ekran görüntüsü.",
  "resultDelivered": "Hazır. Optimize CV'niz panelinize kaydedildi.",
  "downloadPdf": "ATS PDF indir",
  "copyCoverLetter": "Motivasyonu kopyala",
  "copyAnswers": "Cevapları kopyala",
  "copied": "Kopyalandı",
  "recent": "Son başvurular",
  "recentEmpty": "Henüz başvuru yok.",
  "statusSubmitted": "Gönderildi",
  "statusDelivered": "Teslim edildi",
  "statusFailed": "Teslim edildi (otomatik gönderim başarısız)"
}
```

- [ ] **Step 2: Implement `FormAnswerField`**

Create `web/src/components/apply/FormAnswerField.tsx`:

```tsx
'use client'
import { useTranslations } from 'next-intl'
import type { FormField } from '@/types/api'

const SELECT_CLS =
  'h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'
const TEXT_CLS =
  'min-h-11 rounded-lg border border-border bg-background px-3 py-2 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

export function FormAnswerField({ field, value, onChange }: {
  field: FormField
  value: string
  onChange: (value: string) => void
}) {
  const t = useTranslations('optimize')
  const showRequired = field.required && !value.trim() && field.type !== 'file'

  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
      <span className="flex items-center gap-2">
        {field.label}
        {showRequired && (
          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-normal text-destructive">
            {t('requiredEmpty')}
          </span>
        )}
      </span>

      {field.type === 'file' ? (
        <span className="text-[13px] font-normal text-muted-foreground">{t('fileNote')}</span>
      ) : field.type === 'select' || field.type === 'radio' ? (
        <select className={SELECT_CLS} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      ) : field.type === 'checkbox' ? (
        <input
          type="checkbox"
          className="size-5 self-start accent-primary"
          checked={['yes', 'true', 'on', 'evet', '1'].includes(value.toLowerCase())}
          onChange={(e) => onChange(e.target.checked ? 'yes' : 'no')}
        />
      ) : (
        <textarea className={TEXT_CLS} rows={field.type === 'textarea' ? 4 : 1}
          value={value} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  )
}
```

- [ ] **Step 3: Write the failing ApprovalScreen test**

Create `web/src/components/apply/__tests__/ApprovalScreen.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { OptimizedPayload } from '@/types/api'
import { ApprovalScreen } from '@/components/apply/ApprovalScreen'

const PAYLOAD: OptimizedPayload = {
  job_text: 'Backend developer',
  cv: {
    full_name: 'Ada Lovelace', title: null, email: 'ada@x.com', phone: null, location: null,
    summary: 'Engineer', experiences: [], education: [], skills: ['Python'],
    languages: [], certifications: [],
  },
  changes: ['Reordered skills'],
  cover_letter: 'I am excited to apply.',
  form: [
    { id: 'motivation', selector: '/x', label: 'Why us?', type: 'textarea', options: [], option_selectors: [], required: false },
    { id: 'experience', selector: '/y', label: 'Years', type: 'select', options: ['1-3', '3-5'], option_selectors: [], required: true },
  ],
  answers: [
    { field_id: 'motivation', value: 'I love APIs.' },
    { field_id: 'experience', value: '3-5' },
  ],
}

it('renders read-only CV summary, changes and editable answers', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByText('Reordered skills')).toBeInTheDocument()
  expect((screen.getByDisplayValue('I love APIs.') as HTMLTextAreaElement).value).toBe('I love APIs.')
})

it('submit sends edited answers and cover letter', async () => {
  const onSubmit = vi.fn()
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit onSubmit={onSubmit} onDeliver={vi.fn()} />)
  await userEvent.clear(screen.getByDisplayValue('I love APIs.'))
  await userEvent.type(screen.getByLabelText('Why us?'), 'Edited motivation')
  await userEvent.click(screen.getByRole('button', { name: 'Approve & apply' }))
  const [answers, cover] = onSubmit.mock.calls[0]
  expect(answers).toContainEqual({ field_id: 'motivation', value: 'Edited motivation' })
  expect(typeof cover).toBe('string')
})

it('hides the submit button when canSubmit is false', () => {
  renderWithIntl(<ApprovalScreen payload={PAYLOAD} canSubmit={false} onSubmit={vi.fn()} onDeliver={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'Approve & apply' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Just hand it to me' })).toBeInTheDocument()
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `npx vitest run "src/components/apply/__tests__/ApprovalScreen.test.tsx"`
Expected: FAIL — cannot resolve `@/components/apply/ApprovalScreen`.

- [ ] **Step 5: Implement `ApprovalScreen`**

Create `web/src/components/apply/ApprovalScreen.tsx`:

```tsx
'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Send, PackageOpen } from 'lucide-react'
import type { FieldAnswer, OptimizedPayload } from '@/types/api'
import { Button } from '@/components/ui/button'
import { FormAnswerField } from './FormAnswerField'

export function ApprovalScreen({ payload, canSubmit, onSubmit, onDeliver }: {
  payload: OptimizedPayload
  canSubmit: boolean
  onSubmit: (answers: FieldAnswer[], coverLetter: string) => void
  onDeliver: (answers: FieldAnswer[], coverLetter: string) => void
}) {
  const t = useTranslations('optimize')
  const [coverLetter, setCoverLetter] = useState(payload.cover_letter ?? '')
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(payload.answers.map((a) => [a.field_id, a.value]))
  )

  const answers = (): FieldAnswer[] =>
    payload.form
      .filter((f) => f.type !== 'file')
      .map((f) => ({ field_id: f.id, value: values[f.id] ?? '' }))

  return (
    <div className="flex flex-col gap-7">
      <section className="flex flex-col gap-3 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
        <h2 className="text-lg font-semibold text-foreground">{payload.cv.full_name}</h2>
        {payload.cv.summary && (
          <p className="text-[15px] leading-relaxed text-muted-foreground">{payload.cv.summary}</p>
        )}
        {payload.changes.length > 0 && (
          <div>
            <p className="mb-1 text-sm font-medium text-foreground">{t('changes')}</p>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {payload.changes.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
        )}
      </section>

      <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
        {t('coverLetter')}
        <textarea
          className="min-h-32 rounded-lg border border-border bg-background px-3 py-2 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={coverLetter} onChange={(e) => setCoverLetter(e.target.value)}
        />
      </label>

      {payload.form.length > 0 && (
        <section className="flex flex-col gap-4">
          <p className="text-sm font-medium text-foreground">{t('formAnswers')}</p>
          {payload.form.map((field) => (
            <FormAnswerField
              key={field.id} field={field} value={values[field.id] ?? ''}
              onChange={(v) => setValues((prev) => ({ ...prev, [field.id]: v }))}
            />
          ))}
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        {canSubmit && (
          <Button onClick={() => onSubmit(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
            <Send aria-hidden className="size-4" />
            {t('submit')}
          </Button>
        )}
        <Button variant="outline" onClick={() => onDeliver(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
          <PackageOpen aria-hidden className="size-4" />
          {t('deliver')}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `npx vitest run "src/components/apply/__tests__/ApprovalScreen.test.tsx"`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/apply/FormAnswerField.tsx web/src/components/apply/ApprovalScreen.tsx web/src/components/apply/__tests__/ApprovalScreen.test.tsx web/src/messages/en.json web/src/messages/tr.json
git commit -m "feat(web): ApprovalScreen with editable answers + cover letter, optimize i18n"
```

---

### Task 5: Web — persistence helper + ResultScreen

**Files:**
- Create: `web/src/lib/applications.ts` (`saveApplication`)
- Create: `web/src/lib/__tests__/applications.test.ts`
- Create: `web/src/components/apply/ResultScreen.tsx`
- Create: `web/src/components/apply/__tests__/ResultScreen.test.tsx`

**Interfaces:**
- Consumes: `insertCv`, `insertApplication` from `@/lib/db`; `CVData`, `FieldAnswer`, `FormField` from `@/types/api`; `downloadBlob` from `@/lib/download`; `Button` from `@/components/ui/button`.
- Produces (used by Task 6):
  - `saveApplication(sb, args): Promise<void>` where `args = { userId: string; sourceCvId: string; optimizedCv: CVData; pdf: Blob; url: string; jobText: string; coverLetter: string; form: FormField[]; answers: FieldAnswer[]; changes: string[]; status: 'submitted' | 'delivered' | 'failed' }`.
  - `ResultScreen` with props `{ mode: 'submitted' | 'delivered'; screenshot?: string; pdf: Blob; pdfName: string; coverLetter: string; answers: FieldAnswer[] }`.

- [ ] **Step 1: Write the failing persistence test**

Create `web/src/lib/__tests__/applications.test.ts`:

```ts
import { vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'

const upload = vi.fn(async () => ({ error: null }))
const insertCv = vi.fn(async () => ({ id: 'opt-cv' }))
const insertApplication = vi.fn(async () => ({ id: 'app-1' }))
vi.mock('@/lib/db', () => ({ insertCv: (...a: unknown[]) => insertCv(...a), insertApplication: (...a: unknown[]) => insertApplication(...a) }))

import { saveApplication } from '@/lib/applications'

const CV = {
  full_name: 'Ada', email: null, phone: null, location: null, summary: null,
  experiences: [], education: [], skills: [], languages: [], certifications: [],
}

it('uploads the pdf, saves optimized CV (is_ats=false) and records the application', async () => {
  const sb = { storage: { from: () => ({ upload }) } } as unknown as SupabaseClient
  await saveApplication(sb, {
    userId: 'u1', sourceCvId: 'c1', optimizedCv: CV, pdf: new Blob(['%PDF']),
    url: 'https://x', jobText: 'jt', coverLetter: 'cl', form: [], answers: [],
    changes: ['a'], status: 'delivered',
  })
  expect(upload).toHaveBeenCalled()
  expect(insertCv).toHaveBeenCalledWith(sb, expect.objectContaining({
    user_id: 'u1', is_ats: false, source_cv_id: 'c1',
  }))
  expect(insertApplication).toHaveBeenCalledWith(sb, expect.objectContaining({
    user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'opt-cv', status: 'delivered',
  }))
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (in `web/`): `npx vitest run src/lib/__tests__/applications.test.ts`
Expected: FAIL — cannot resolve `@/lib/applications`.

- [ ] **Step 3: Implement `saveApplication`**

Create `web/src/lib/applications.ts`:

```ts
import type { SupabaseClient } from '@supabase/supabase-js'
import type { CVData, FieldAnswer, FormField } from '@/types/api'
import { insertApplication, insertCv } from '@/lib/db'

export async function saveApplication(sb: SupabaseClient, args: {
  userId: string
  sourceCvId: string
  optimizedCv: CVData
  pdf: Blob
  url: string
  jobText: string
  coverLetter: string
  form: FormField[]
  answers: FieldAnswer[]
  changes: string[]
  status: 'submitted' | 'delivered' | 'failed'
}): Promise<void> {
  const path = `${args.userId}/${crypto.randomUUID()}-optimized.pdf`
  const { error } = await sb.storage.from('cvs').upload(path, args.pdf, { contentType: 'application/pdf' })
  if (error) throw error

  const optimized = await insertCv(sb, {
    user_id: args.userId, file_path: path, parsed_data: args.optimizedCv,
    is_ats: false, source_cv_id: args.sourceCvId,
  })
  await insertApplication(sb, {
    user_id: args.userId, cv_id: args.sourceCvId, optimized_cv_id: optimized.id,
    url: args.url, job_text: args.jobText, cover_letter: args.coverLetter,
    qa: { form: args.form, answers: args.answers }, changes: args.changes, status: args.status,
  })
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/lib/__tests__/applications.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing ResultScreen test**

Create `web/src/components/apply/__tests__/ResultScreen.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import { ResultScreen } from '@/components/apply/ResultScreen'

const downloadBlob = vi.fn()
vi.mock('@/lib/download', () => ({ downloadBlob: (...a: unknown[]) => downloadBlob(...a) }))

beforeEach(() => vi.clearAllMocks())

it('submitted mode shows the screenshot', () => {
  renderWithIntl(
    <ResultScreen mode="submitted" screenshot="AAAA" pdf={new Blob(['%PDF'])}
      pdfName="Ada.pdf" coverLetter="cl" answers={[]} />
  )
  const img = screen.getByRole('img') as HTMLImageElement
  expect(img.src).toContain('data:image/png;base64,AAAA')
})

it('delivered mode downloads the PDF', async () => {
  renderWithIntl(
    <ResultScreen mode="delivered" pdf={new Blob(['%PDF'])} pdfName="Ada.pdf"
      coverLetter="my letter" answers={[]} />
  )
  await userEvent.click(screen.getByRole('button', { name: 'Download ATS PDF' }))
  expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'Ada.pdf')
})
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `npx vitest run "src/components/apply/__tests__/ResultScreen.test.tsx"`
Expected: FAIL — cannot resolve `@/components/apply/ResultScreen`.

- [ ] **Step 7: Implement `ResultScreen`**

Create `web/src/components/apply/ResultScreen.tsx`:

```tsx
'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Download, Copy, CheckCircle2 } from 'lucide-react'
import type { FieldAnswer } from '@/types/api'
import { downloadBlob } from '@/lib/download'
import { Button } from '@/components/ui/button'

export function ResultScreen({ mode, screenshot, pdf, pdfName, coverLetter, answers }: {
  mode: 'submitted' | 'delivered'
  screenshot?: string
  pdf: Blob
  pdfName: string
  coverLetter: string
  answers: FieldAnswer[]
}) {
  const t = useTranslations('optimize')
  const [copied, setCopied] = useState<string | null>(null)

  const copy = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 2000)
  }
  const answersText = answers.map((a) => `${a.field_id}: ${a.value}`).join('\n')

  return (
    <div className="flex flex-col gap-6">
      <p className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
        <CheckCircle2 aria-hidden className="size-4 shrink-0" />
        {mode === 'submitted' ? t('resultSubmitted') : t('resultDelivered')}
      </p>

      {mode === 'submitted' && screenshot && (
        <img src={`data:image/png;base64,${screenshot}`} alt=""
          className="w-full rounded-xl border border-border" />
      )}

      <div className="flex flex-wrap gap-3">
        <Button onClick={() => downloadBlob(pdf, pdfName)} className="h-11 gap-1.5 text-base">
          <Download aria-hidden className="size-4" />
          {t('downloadPdf')}
        </Button>
        <Button variant="outline" onClick={() => copy('cover', coverLetter)} className="h-11 gap-1.5 text-base">
          <Copy aria-hidden className="size-4" />
          {copied === 'cover' ? t('copied') : t('copyCoverLetter')}
        </Button>
        {answers.length > 0 && (
          <Button variant="outline" onClick={() => copy('answers', answersText)} className="h-11 gap-1.5 text-base">
            <Copy aria-hidden className="size-4" />
            {copied === 'answers' ? t('copied') : t('copyAnswers')}
          </Button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `npx vitest run "src/components/apply/__tests__/ResultScreen.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
git add web/src/lib/applications.ts web/src/lib/__tests__/applications.test.ts web/src/components/apply/ResultScreen.tsx web/src/components/apply/__tests__/ResultScreen.test.tsx
git commit -m "feat(web): saveApplication persistence helper + ResultScreen"
```

---

### Task 6: Web — `/optimize` page orchestrator + sidebar activation

**Files:**
- Create: `web/src/app/(app)/optimize/page.tsx`
- Create: `web/src/app/(app)/optimize/__tests__/page.test.tsx`
- Modify: `web/src/components/AppSidebar.tsx` (activate the Optimize link)

**Interfaces:**
- Consumes: `applyPrepare`, `applySubmit`, `atsPdf`, `ApiError` from `@/lib/api`; `listCvs` from `@/lib/db`; `saveApplication` from `@/lib/applications`; `ApprovalScreen`, `ResultScreen` from `@/components/apply/*`; `CvSelect`, `ProgressBar`, `Button`; `messageKeyForCode` from `@/lib/errors`; `PrepareResult`, `SubmitResult`, `FieldAnswer` from `@/types/api`.
- Produces: route `/optimize`. Sidebar links to it.

- [ ] **Step 1: Read the Next.js routing guide**

Read `web/node_modules/next/dist/docs/` for the App Router client-component + `useSearchParams`/`Suspense` guidance (per `web/AGENTS.md`). Mirror the exact pattern already used in `web/src/app/(app)/ats/page.tsx` (a `Suspense`-wrapped inner component; `'use client'`).

- [ ] **Step 2: Write the failing page test**

Create `web/src/app/(app)/optimize/__tests__/page.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

const ROUTER = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
const PARAMS = new URLSearchParams('')
vi.mock('next/navigation', () => ({ useRouter: () => ROUTER, useSearchParams: () => PARAMS }))

const upload = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const CVS: CvRow[] = [{
  id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
  created_at: '2026-07-12T00:00:00Z',
  parsed_data: {
    full_name: 'Ada', email: null, phone: null, location: null, summary: null,
    experiences: [], education: [], skills: [], languages: [], certifications: [],
  },
}]

vi.mock('@/lib/db', () => ({ listCvs: vi.fn(async () => CVS), insertCv: vi.fn(async () => ({ id: 'opt' })), insertApplication: vi.fn(async () => ({ id: 'app' })) }))
vi.mock('@/lib/applications', () => ({ saveApplication: vi.fn(async () => {}) }))
vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, applyPrepare: vi.fn(), applySubmit: vi.fn(), atsPdf: vi.fn(async () => new Blob(['%PDF'])) }
})

import { applyPrepare, applySubmit } from '@/lib/api'
import { saveApplication } from '@/lib/applications'
import OptimizePage from '@/app/(app)/optimize/page'

beforeEach(() => vi.clearAllMocks())

async function fillLinkAndPrepare() {
  await screen.findByLabelText('CV')
  await userEvent.type(screen.getByLabelText('Application link'), 'https://j.com/1')
  await userEvent.click(screen.getByRole('button', { name: 'Prepare' }))
}

it('login_required shows the sign-in prompt then retries headed', async () => {
  ;(applyPrepare as Mock)
    .mockResolvedValueOnce({ status: 'login_required' })
    .mockResolvedValueOnce({ status: 'ready', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt' })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Sign in the window and continue' }))
  expect((applyPrepare as Mock).mock.calls[1]).toEqual([CVS[0].parsed_data, 'https://j.com/1', expect.any(String), true])
  await screen.findByText('Review before applying')
})

it('ready → approve → submit saves the application and shows the screenshot', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'ready', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  ;(applySubmit as Mock).mockResolvedValue({ status: 'submitted', screenshot: 'PNGDATA' })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Approve & apply' }))
  await waitFor(() => expect(saveApplication).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ status: 'submitted' })))
  expect((screen.getByRole('img') as HTMLImageElement).src).toContain('PNGDATA')
})

it('captcha goes straight to delivery mode (no submit button)', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'captcha', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await screen.findByText('Review before applying')
  expect(screen.queryByRole('button', { name: 'Approve & apply' })).toBeNull()
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npx vitest run "src/app/(app)/optimize/__tests__/page.test.tsx"`
Expected: FAIL — cannot resolve `@/app/(app)/optimize/page`.

- [ ] **Step 4: Implement the page**

Create `web/src/app/(app)/optimize/page.tsx`:

```tsx
'use client'
import { Suspense, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Send, AlertCircle, LogIn } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { listCvs } from '@/lib/db'
import { ApiError, applyPrepare, applySubmit, atsPdf } from '@/lib/api'
import { saveApplication } from '@/lib/applications'
import { messageKeyForCode } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { CvRow } from '@/types/db'
import type { FieldAnswer, OptimizedPayload, PrepareResult } from '@/types/api'
import { CvSelect } from '@/components/CvSelect'
import { ProgressBar } from '@/components/ProgressBar'
import { ApprovalScreen } from '@/components/apply/ApprovalScreen'
import { ResultScreen } from '@/components/apply/ResultScreen'
import { Button, buttonVariants } from '@/components/ui/button'

type Step = 'form' | 'preparing' | 'login' | 'approve' | 'submitting' | 'result'
type ResultView = { mode: 'submitted' | 'delivered'; screenshot?: string; pdf: Blob; pdfName: string; coverLetter: string; answers: FieldAnswer[] }

function pdfName(fullName: string): string {
  const safe = fullName.trim().replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, '_') || 'CV'
  return `${safe}_OptimizedCV.pdf`
}

function OptimizePageInner() {
  const t = useTranslations()
  const locale = useLocale()
  const router = useRouter()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [selected, setSelected] = useState('')
  const [url, setUrl] = useState('')
  const [lang, setLang] = useState<'tr' | 'en'>(locale === 'en' ? 'en' : 'tr')
  const [step, setStep] = useState<Step>('form')
  const [preparingLabel, setPreparingLabel] = useState('optimize.preparing')
  const [payload, setPayload] = useState<(OptimizedPayload & { status: PrepareResult['status'] }) | null>(null)
  const [result, setResult] = useState<ResultView | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { router.replace('/login'); return }
    setCvs(await listCvs(supabase))
  }, [supabase, router])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (cvs && cvs.length && !selected) setSelected(cvs[0].id) }, [cvs, selected])

  const showError = (err: unknown) =>
    setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))

  async function prepare(headed: boolean) {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv || !url.trim()) return
    setError(null)
    // headed retry means the user is signing in by hand — show the waiting copy.
    setPreparingLabel(headed ? 'optimize.loginWaiting' : 'optimize.preparing')
    setStep('preparing')
    try {
      const res = await applyPrepare(cv.parsed_data, url.trim(), lang, headed)
      if (res.status === 'login_required') { setStep('login'); return }
      setPayload(res)
      setStep('approve')
    } catch (err) {
      showError(err)
      setStep('form')
    }
  }

  async function finish(mode: 'submitted' | 'delivered', optimized: OptimizedPayload,
                        answers: FieldAnswer[], coverLetter: string, screenshot?: string) {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { router.replace('/login'); return }
    const pdf = await atsPdf(optimized.cv, lang)
    try {
      await saveApplication(supabase, {
        userId: user.id, sourceCvId: selected, optimizedCv: optimized.cv, pdf,
        url: url.trim(), jobText: optimized.job_text, coverLetter,
        form: optimized.form, answers, changes: optimized.changes,
        status: mode === 'submitted' ? 'submitted' : 'delivered',
      })
    } catch (err) {
      showError(err)
    }
    setResult({ mode, screenshot, pdf, pdfName: pdfName(optimized.cv.full_name), coverLetter, answers })
    setStep('result')
  }

  async function onSubmit(answers: FieldAnswer[], coverLetter: string) {
    if (!payload) return
    setError(null)
    setStep('submitting')
    try {
      const cv = cvs!.find((c) => c.id === selected)!
      const res = await applySubmit(cv.parsed_data, url.trim(), lang, answers)
      if (res.status === 'submitted') {
        await finish('submitted', payload, answers, coverLetter, res.screenshot)
      } else {
        // failed / login_required / captcha between prepare and submit → delivery
        await finish('delivered', payload, answers, coverLetter)
      }
    } catch (err) {
      showError(err)
      await finish('delivered', payload, answers, coverLetter)
    }
  }

  async function onDeliver(answers: FieldAnswer[], coverLetter: string) {
    if (payload) await finish('delivered', payload, answers, coverLetter)
  }

  if (!cvs) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-12 sm:px-8">
        <div className="h-40 animate-pulse rounded-2xl bg-muted/70" aria-hidden />
        <span className="sr-only">{t('common.loading')}</span>
      </main>
    )
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-7 px-5 py-12 sm:px-8">
      <header>
        <p className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.18em] text-primary/80">
          <Send aria-hidden className="size-3.5" />
          {t('optimize.title')}
        </p>
        <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted-foreground">{t('optimize.intro')}</p>
      </header>

      {error && (
        <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
          <AlertCircle aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      )}

      {cvs.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
          <p className="max-w-xs text-[15px] leading-relaxed text-muted-foreground">{t('common.noCvs')}</p>
          <Link href="/dashboard" className={cn(buttonVariants({ size: 'sm' }))}>{t('nav.dashboard')}</Link>
        </div>
      ) : step === 'form' ? (
        <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
          <CvSelect cvs={cvs} value={selected} onChange={setSelected} />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('optimize.link')}
            <input
              type="url" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder={t('optimize.linkPlaceholder')}
              className="h-11 rounded-lg border border-border bg-background px-3 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            {t('optimize.language')}
            <select value={lang} onChange={(e) => setLang(e.target.value as 'tr' | 'en')}
              className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50">
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
            </select>
          </label>
          <Button onClick={() => prepare(false)} disabled={!selected || !url.trim()} className="h-11 gap-1.5 text-base">
            <Send aria-hidden className="size-4" />
            {t('optimize.prepare')}
          </Button>
        </div>
      ) : step === 'preparing' ? (
        <ProgressBar label={t(preparingLabel)} />
      ) : step === 'login' ? (
        <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
          <h2 className="text-lg font-semibold text-foreground">{t('optimize.loginTitle')}</h2>
          <p className="text-[15px] leading-relaxed text-muted-foreground">{t('optimize.loginIntro')}</p>
          <Button onClick={() => prepare(true)} className="h-11 gap-1.5 text-base">
            <LogIn aria-hidden className="size-4" />
            {t('optimize.loginButton')}
          </Button>
        </div>
      ) : step === 'submitting' ? (
        <ProgressBar label={t('optimize.submitting')} />
      ) : step === 'approve' && payload ? (
        <>
          <h1 className="text-xl font-semibold text-foreground">{t('optimize.approveTitle')}</h1>
          {payload.status !== 'ready' && (
            <p className="rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">{t('optimize.deliverModeNote')}</p>
          )}
          <ApprovalScreen payload={payload} canSubmit={payload.status === 'ready'} onSubmit={onSubmit} onDeliver={onDeliver} />
        </>
      ) : step === 'result' && result ? (
        <ResultScreen {...result} />
      ) : null}
    </main>
  )
}

export default function OptimizePage() {
  return (
    <Suspense fallback={null}>
      <OptimizePageInner />
    </Suspense>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npx vitest run "src/app/(app)/optimize/__tests__/page.test.tsx"`
Expected: PASS (3 tests). If the `preparing`/`login` transition races, assert on `findBy*` (already used) which retries.

- [ ] **Step 6: Activate the sidebar link**

In `web/src/components/AppSidebar.tsx`, add `optimize` to `ITEMS` (after the `ats` entry, line 11):

```tsx
  { href: '/optimize', key: 'optimize', icon: Send, also: [] },
```

Then delete the disabled `<span>` block (the `aria-disabled` span with the `Send` icon and `soon` badge, lines 46-55). The `Send` icon is already imported on line 5; remove the now-unused `soon` usage. Leave `sidebar.optimize` in the messages; delete `sidebar.soon` only if no other file references it (`grep -rn "sidebar.soon\|'soon'" web/src` first — if the grep is clean of other uses, remove the `soon` key from both `en.json` and `tr.json`).

- [ ] **Step 7: Run the sidebar test + full web suite**

Run: `npx vitest run src/components/__tests__/AppSidebar.test.tsx` then `npm test`
Expected: all green. If `AppSidebar.test.tsx` asserted the disabled "soon" state, update that assertion to expect an active `/optimize` link.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/(app)/optimize web/src/components/AppSidebar.tsx web/src/messages/en.json web/src/messages/tr.json
git commit -m "feat(web): /optimize page state machine + activate sidebar link"
```

---

### Task 7: Web — RecentApplications list + final verification

**Files:**
- Create: `web/src/components/apply/RecentApplications.tsx`
- Create: `web/src/components/apply/__tests__/RecentApplications.test.tsx`
- Modify: `web/src/app/(app)/optimize/page.tsx` (render the list under the form)

**Interfaces:**
- Consumes: `listApplications` from `@/lib/db`; `ApplicationRow` from `@/types/db`.
- Produces: `RecentApplications` component (self-loading from a passed `SupabaseClient`).

- [ ] **Step 1: Write the failing test**

Create `web/src/components/apply/__tests__/RecentApplications.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { ApplicationRow } from '@/types/db'
import type { SupabaseClient } from '@supabase/supabase-js'

const ROWS: ApplicationRow[] = [{
  id: 'a1', user_id: 'u1', cv_id: 'c1', optimized_cv_id: 'c2', url: 'https://acme.com/jobs/1',
  job_text: null, cover_letter: null, qa: {}, changes: [], status: 'submitted',
  created_at: '2026-07-20T00:00:00Z',
}]
vi.mock('@/lib/db', () => ({ listApplications: vi.fn(async () => ROWS) }))

import { RecentApplications } from '@/components/apply/RecentApplications'

it('lists recent applications with their status', async () => {
  renderWithIntl(<RecentApplications supabase={{} as SupabaseClient} />)
  expect(await screen.findByText(/acme.com/)).toBeInTheDocument()
  expect(screen.getByText('Submitted')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run "src/components/apply/__tests__/RecentApplications.test.tsx"`
Expected: FAIL — cannot resolve `@/components/apply/RecentApplications`.

- [ ] **Step 3: Implement `RecentApplications`**

Create `web/src/components/apply/RecentApplications.tsx`:

```tsx
'use client'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import type { SupabaseClient } from '@supabase/supabase-js'
import { listApplications } from '@/lib/db'
import type { ApplicationRow } from '@/types/db'

const STATUS_KEY: Record<ApplicationRow['status'], string> = {
  submitted: 'statusSubmitted', delivered: 'statusDelivered', failed: 'statusFailed',
}

export function RecentApplications({ supabase }: { supabase: SupabaseClient }) {
  const t = useTranslations('optimize')
  const [rows, setRows] = useState<ApplicationRow[] | null>(null)

  useEffect(() => {
    listApplications(supabase).then(setRows).catch(() => setRows([]))
  }, [supabase])

  if (!rows || rows.length === 0) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-foreground">{t('recent')}</h2>
        <p className="text-sm text-muted-foreground">{rows ? t('recentEmpty') : '…'}</p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-foreground">{t('recent')}</h2>
      <ul className="flex flex-col divide-y divide-border rounded-xl ring-1 ring-foreground/10">
        {rows.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <span className="truncate text-muted-foreground">{r.url}</span>
            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-foreground">
              {t(STATUS_KEY[r.status])}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run "src/components/apply/__tests__/RecentApplications.test.tsx"`
Expected: PASS.

- [ ] **Step 5: Render it on the optimize page (form step only)**

In `web/src/app/(app)/optimize/page.tsx`, add the import near the other apply imports:

```tsx
import { RecentApplications } from '@/components/apply/RecentApplications'
```

Then, inside the `step === 'form'` branch, immediately AFTER the closing `</div>` of the form card (still inside the `cvs.length === 0 ? ... : step === 'form' ? (...)` expression), wrap the form card and the list in a fragment so both render:

Replace the `) : step === 'form' ? (` block's single `<div>…</div>` with:

```tsx
      ) : step === 'form' ? (
        <>
          <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
            <CvSelect cvs={cvs} value={selected} onChange={setSelected} />
            <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
              {t('optimize.link')}
              <input
                type="url" value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder={t('optimize.linkPlaceholder')}
                className="h-11 rounded-lg border border-border bg-background px-3 text-base text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
              {t('optimize.language')}
              <select value={lang} onChange={(e) => setLang(e.target.value as 'tr' | 'en')}
                className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50">
                <option value="tr">Türkçe</option>
                <option value="en">English</option>
              </select>
            </label>
            <Button onClick={() => prepare(false)} disabled={!selected || !url.trim()} className="h-11 gap-1.5 text-base">
              <Send aria-hidden className="size-4" />
              {t('optimize.prepare')}
            </Button>
          </div>
          <RecentApplications supabase={supabase} />
        </>
```

- [ ] **Step 6: Full verification**

Run (in `web/`):
- `npm test` — all green (includes message parity).
- `npx tsc --noEmit` — no type errors.
- `npm run build` — succeeds, `/optimize` route listed, no Suspense warnings.

Run (in `api/`): `.venv\Scripts\python -m pytest -q` — all green.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/apply/RecentApplications.tsx web/src/components/apply/__tests__/RecentApplications.test.tsx web/src/app/(app)/optimize/page.tsx
git commit -m "feat(web): recent applications list on /optimize"
```

- [ ] **Step 8: Whole-branch review**

Request a whole-branch code review (high effort) against `master` before merge, per the SDD workflow. Address findings, then merge.

---
```
