# App Shell (Left Panel) Implementation Plan — Faz 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all CV operations (dashboard, score, ATS convert) behind a global left panel, each on its own page with a CV selector, per the spec `docs/superpowers/specs/2026-07-16-app-shell-and-auto-apply-design.md` (Faz 1 only).

**Architecture:** A Next.js route group `web/src/app/(app)/` hosts all logged-in pages and renders a shared `AppSidebar` in its `layout.tsx` (route groups do not change URLs). `/score` and `/ats` become standalone pages with a CV `<select>`; `?cv=<id>` preselects. The CV detail page becomes view-only. The old `/cv/[id]/score` URL redirects to `/score?cv=<id>`.

**Tech Stack:** Next.js 16 (App Router), next-intl, Supabase JS, Tailwind, vitest + testing-library, lucide-react.

## Global Constraints

- **Windows path casing:** run all commands from `C:\Users\ASUS\Desktop\cv-ai` (capital **D** in Desktop); a mismatched-case path breaks the Next build.
- **Next.js 16 has breaking changes** vs training data. Before writing any page/layout code, read the relevant guide in `web/node_modules/next/dist/docs/` (route groups, `useSearchParams`, `redirect`). Known: dynamic route `params` is a **Promise** in server components (`const { id } = await params`); `useSearchParams` in a client page must be wrapped in `<Suspense>`.
- **i18n parity:** every message key must exist in BOTH `web/src/messages/en.json` and `tr.json` — `src/messages/__tests__/parity.test.ts` fails otherwise.
- All web commands run in `web/`: `npm test` (vitest run), `npx tsc --noEmit`.
- App name is **KRESUME.ai** — never reintroduce "CV-AI" in copy.
- Existing visual language: use existing utility classes seen in neighboring components (`text-ink`, `font-display`, `bg-card`, `ring-foreground/10`, etc.). No new design tokens.

---

### Task 1: AppSidebar component + `(app)` route group + page moves

**Files:**
- Create: `web/src/components/AppSidebar.tsx`
- Create: `web/src/app/(app)/layout.tsx`
- Create: `web/src/components/__tests__/AppSidebar.test.tsx`
- Move: `web/src/app/dashboard/` → `web/src/app/(app)/dashboard/` (incl. `__tests__/`)
- Move: `web/src/app/cv/` → `web/src/app/(app)/cv/` (incl. both `__tests__/` dirs)
- Modify: `web/src/messages/en.json`, `web/src/messages/tr.json` (new `sidebar` section)
- Modify: moved test files' imports (`@/app/dashboard/...` → `@/app/(app)/dashboard/...`, `@/app/cv/...` → `@/app/(app)/cv/...`)

**Interfaces:**
- Consumes: `renderWithIntl` from `@/test/utils`, `cn` from `@/lib/utils`.
- Produces: `AppSidebar` (no props) rendered by `(app)/layout.tsx`; nav hrefs `/dashboard`, `/score`, `/ats`; disabled "optimize" entry. Later tasks create the `/score` and `/ats` pages these links point to.

- [ ] **Step 1: Add sidebar messages**

In `web/src/messages/en.json`, after the `"nav"` section add:

```json
"sidebar": {
  "label": "Operations",
  "dashboard": "Dashboard",
  "score": "Score",
  "ats": "Convert to ATS",
  "optimize": "Optimize & Apply",
  "soon": "soon"
},
```

In `web/src/messages/tr.json`, same position:

```json
"sidebar": {
  "label": "İşlemler",
  "dashboard": "Panel",
  "score": "Skorla",
  "ats": "ATS'ye Çevir",
  "optimize": "Optimize & Başvur",
  "soon": "yakında"
},
```

- [ ] **Step 2: Write the failing sidebar test**

Create `web/src/components/__tests__/AppSidebar.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'

const usePathname = vi.fn(() => '/dashboard')
vi.mock('next/navigation', () => ({ usePathname: () => usePathname() }))

import { AppSidebar } from '@/components/AppSidebar'

it('renders links for dashboard, score and ats', () => {
  renderWithIntl(<AppSidebar />)
  expect(screen.getByRole('link', { name: /Panel/ })).toHaveAttribute('href', '/dashboard')
  expect(screen.getByRole('link', { name: /Skorla/ })).toHaveAttribute('href', '/score')
  expect(screen.getByRole('link', { name: /ATS'ye Çevir/ })).toHaveAttribute('href', '/ats')
})

it('marks the active item with aria-current', () => {
  usePathname.mockReturnValue('/score')
  renderWithIntl(<AppSidebar />)
  expect(screen.getByRole('link', { name: /Skorla/ })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: /Panel/ })).not.toHaveAttribute('aria-current')
})

it('shows optimize as disabled with a soon badge', () => {
  renderWithIntl(<AppSidebar />)
  expect(screen.queryByRole('link', { name: /Optimize/ })).toBeNull()
  expect(screen.getByText(/Optimize & Başvur/)).toBeInTheDocument()
  expect(screen.getByText(/yakında/)).toBeInTheDocument()
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (in `web/`): `npx vitest run src/components/__tests__/AppSidebar.test.tsx`
Expected: FAIL — cannot resolve `@/components/AppSidebar`.

- [ ] **Step 4: Implement AppSidebar**

Create `web/src/components/AppSidebar.tsx`:

```tsx
'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { LayoutDashboard, Target, FileOutput, Send } from 'lucide-react'
import { cn } from '@/lib/utils'

const ITEMS = [
  { href: '/dashboard', key: 'dashboard', icon: LayoutDashboard, also: ['/cv'] },
  { href: '/score', key: 'score', icon: Target, also: [] },
  { href: '/ats', key: 'ats', icon: FileOutput, also: [] },
] as const

export function AppSidebar() {
  const t = useTranslations('sidebar')
  const pathname = usePathname()

  const isActive = (item: (typeof ITEMS)[number]) =>
    [item.href, ...item.also].some((p) => pathname === p || pathname.startsWith(p + '/'))

  return (
    <nav
      aria-label={t('label')}
      className="flex shrink-0 gap-1 overflow-x-auto border-b border-border/70 px-5 py-2 sm:px-8 md:sticky md:top-20 md:w-52 md:flex-col md:self-start md:overflow-visible md:border-b-0 md:px-0 md:py-0"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon
        const active = isActive(item)
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              active
                ? 'bg-primary/8 text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <Icon aria-hidden className="size-4" />
            {t(item.key)}
          </Link>
        )
      })}
      <span
        aria-disabled
        className="flex shrink-0 cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground/50"
      >
        <Send aria-hidden className="size-4" />
        {t('optimize')}
        <span className="rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider">
          {t('soon')}
        </span>
      </span>
    </nav>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run src/components/__tests__/AppSidebar.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Create the route group layout and move pages**

Create `web/src/app/(app)/layout.tsx`:

```tsx
import { AppSidebar } from '@/components/AppSidebar'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col md:flex-row md:gap-6 md:px-8 md:pt-10">
      <AppSidebar />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
```

Move the pages (run from repo root; quote the parenthesized path — PowerShell parses `(` otherwise):

```bash
git mv web/src/app/dashboard "web/src/app/(app)/dashboard"
git mv web/src/app/cv "web/src/app/(app)/cv"
```

- [ ] **Step 7: Fix imports in moved tests**

In `web/src/app/(app)/dashboard/__tests__/page.test.tsx`: change `@/app/dashboard/page` to `@/app/(app)/dashboard/page`.
In `web/src/app/(app)/cv/[id]/__tests__/page.test.tsx`: change `@/app/cv/[id]/page` to `@/app/(app)/cv/[id]/page`.
In `web/src/app/(app)/cv/[id]/score/__tests__/page.test.tsx`: change `@/app/cv/[id]/score/page` to `@/app/(app)/cv/[id]/score/page`.
(Search for any other `@/app/dashboard` / `@/app/cv` imports: `grep -rn "@/app/(dashboard|cv)" web/src` and fix all hits.)

- [ ] **Step 8: Run the full web suite + typecheck**

Run (in `web/`): `npm test` then `npx tsc --noEmit`
Expected: all tests pass (parity picks up the new `sidebar` keys in both files), tsc clean.

- [ ] **Step 9: Commit**

```bash
git add -A web/src docs
git commit -m "feat(web): global left panel via (app) route group"
```

---

### Task 2: Shared CvSelect + `/ats` page; CV detail becomes view-only

**Files:**
- Create: `web/src/components/CvSelect.tsx`
- Create: `web/src/app/(app)/ats/page.tsx`
- Create: `web/src/app/(app)/ats/__tests__/page.test.tsx`
- Modify: `web/src/app/(app)/cv/[id]/page.tsx` (remove conversion UI + score button)
- Modify: `web/src/app/(app)/cv/[id]/__tests__/page.test.tsx` (drop convert-flow assertions if present)
- Modify: `web/src/messages/en.json`, `tr.json` (new `ats` section, `common.cvLabel`; remove `cv.atsLanguage`, `cv.convertAts`, `cv.converting`, `cv.scoreCta`, `cv.downloadPdf`)

**Interfaces:**
- Consumes: `listCvs`, `insertCv` from `@/lib/db`; `atsRewrite`, `atsPdf`, `ApiError` from `@/lib/api`; `downloadBlob` from `@/lib/download`; `messageKeyForCode` from `@/lib/errors`.
- Produces: `CvSelect` component with props `{ cvs: CvRow[]; value: string; onChange: (id: string) => void }` — Task 3's `/score` page reuses it. Page route `/ats` accepting `?cv=<id>`.

- [ ] **Step 1: Update messages**

`web/src/messages/en.json` — add after the `score` section:

```json
"ats": {
  "title": "Convert to ATS",
  "intro": "Pick a CV and a language; you get a clean, ATS-readable PDF. The copy is also saved to your dashboard.",
  "language": "Conversion language",
  "convert": "Convert to ATS",
  "converting": "Converting…",
  "done": "Converted! The PDF was downloaded and the ATS copy was saved to your dashboard."
},
```

In `"common"` add: `"cvLabel": "CV",`
Remove from `"cv"`: `atsLanguage`, `convertAts`, `converting`, `downloadPdf`, `scoreCta`.

`web/src/messages/tr.json` — same shape:

```json
"ats": {
  "title": "ATS'ye Çevir",
  "intro": "Bir CV ve dil seçin; ATS sistemlerinin okuyabildiği temiz bir PDF alın. Kopya panelinize de kaydedilir.",
  "language": "Dönüştürme dili",
  "convert": "ATS'ye Çevir",
  "converting": "Dönüştürülüyor…",
  "done": "Dönüştürüldü! PDF indirildi ve ATS kopyası panelinize kaydedildi."
},
```

In `"common"` add: `"cvLabel": "CV",` and remove the same five `cv.*` keys.

Then verify nothing else uses the removed keys: `grep -rn "atsLanguage\|convertAts\|cv.converting\|scoreCta\|downloadPdf" web/src` — fix any hit before proceeding.

- [ ] **Step 2: Implement CvSelect**

Create `web/src/components/CvSelect.tsx`:

```tsx
'use client'
import { useTranslations } from 'next-intl'
import type { CvRow } from '@/types/db'

export function CvSelect({ cvs, value, onChange }: {
  cvs: CvRow[]
  value: string
  onChange: (id: string) => void
}) {
  const t = useTranslations()
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
      {t('common.cvLabel')}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground transition-all outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {cvs.map((c) => (
          <option key={c.id} value={c.id}>
            {c.parsed_data.full_name}
            {c.is_ats ? ' — ATS' : ''} ({new Date(c.created_at).toLocaleDateString()})
          </option>
        ))}
      </select>
    </label>
  )
}
```

- [ ] **Step 3: Write the failing `/ats` page test**

Create `web/src/app/(app)/ats/__tests__/page.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

// Stable identities: the page's useCallback/useEffect depend on these; a fresh
// object per render causes an infinite re-render loop (same trap as the
// dashboard useRouter fix on Jul 16).
const ROUTER = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
const PARAMS = new URLSearchParams('cv=c2')
vi.mock('next/navigation', () => ({
  useRouter: () => ROUTER,
  useSearchParams: () => PARAMS,
}))

const upload = vi.fn(async () => ({ error: null }))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
    storage: { from: () => ({ upload }) },
  }),
}))

const CVS: CvRow[] = [
  {
    id: 'c1', user_id: 'u1', file_path: 'u1/a.pdf', is_ats: false, source_cv_id: null,
    created_at: '2026-07-12T00:00:00Z',
    parsed_data: {
      full_name: 'Ada', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  },
  {
    id: 'c2', user_id: 'u1', file_path: 'u1/b.pdf', is_ats: false, source_cv_id: null,
    created_at: '2026-07-13T00:00:00Z',
    parsed_data: {
      full_name: 'Grace', email: null, phone: null, location: null, summary: null,
      experiences: [], education: [], skills: [], languages: [], certifications: [],
    },
  },
]

vi.mock('@/lib/db', () => ({
  listCvs: vi.fn(async () => CVS),
  insertCv: vi.fn(async () => CVS[0]),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return { ...orig, atsRewrite: vi.fn(), atsPdf: vi.fn() }
})

vi.mock('@/lib/download', () => ({ downloadBlob: vi.fn() }))

import { insertCv } from '@/lib/db'
import { atsRewrite, atsPdf } from '@/lib/api'
import { downloadBlob } from '@/lib/download'
import AtsPage from '@/app/(app)/ats/page'

beforeEach(() => vi.clearAllMocks())

it('preselects the CV from the query param', async () => {
  renderWithIntl(<AtsPage />)
  const select = await screen.findByLabelText('CV')
  expect((select as HTMLSelectElement).value).toBe('c2')
})

it('converts, downloads the PDF and saves the ATS copy', async () => {
  ;(atsRewrite as Mock).mockResolvedValue(CVS[0].parsed_data)
  ;(atsPdf as Mock).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
  renderWithIntl(<AtsPage />)
  await screen.findByLabelText('CV')
  await userEvent.click(screen.getByRole('button', { name: "ATS'ye Çevir" }))
  await waitFor(() => expect(downloadBlob).toHaveBeenCalled())
  expect(insertCv).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
    is_ats: true, source_cv_id: 'c2',
  }))
  expect(await screen.findByText(/Dönüştürüldü/)).toBeInTheDocument()
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `npx vitest run "src/app/(app)/ats/__tests__/page.test.tsx"`
Expected: FAIL — cannot resolve `@/app/(app)/ats/page`.

- [ ] **Step 5: Implement the `/ats` page**

Create `web/src/app/(app)/ats/page.tsx` (conversion logic lifted verbatim from the old CV-detail `convert()`):

```tsx
'use client'
import { Suspense, useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Download, AlertCircle, CheckCircle2, FileOutput } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { insertCv, listCvs } from '@/lib/db'
import { ApiError, atsPdf, atsRewrite } from '@/lib/api'
import { messageKeyForCode } from '@/lib/errors'
import { downloadBlob } from '@/lib/download'
import type { CvRow } from '@/types/db'
import { CvSelect } from '@/components/CvSelect'
import { Button } from '@/components/ui/button'

function AtsPageInner() {
  const t = useTranslations()
  const locale = useLocale()
  const router = useRouter()
  const params = useSearchParams()
  const [supabase] = useState(createClient)
  const [cvs, setCvs] = useState<CvRow[] | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [atsLang, setAtsLang] = useState<'tr' | 'en'>(locale === 'en' ? 'en' : 'tr')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      router.replace('/login')
      return
    }
    const rows = await listCvs(supabase)
    setCvs(rows)
    const fromQuery = params.get('cv')
    setSelected(fromQuery && rows.some((r) => r.id === fromQuery) ? fromQuery : rows[0]?.id ?? '')
  }, [supabase, router, params])

  useEffect(() => {
    load()
  }, [load])

  async function convert() {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv) return
    setError(null)
    setDone(false)
    setBusy(true)
    try {
      const rewritten = await atsRewrite(cv.parsed_data, atsLang)
      const pdf = await atsPdf(rewritten, atsLang)
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
      setDone(true)
    } catch (err) {
      setError(t(err instanceof ApiError ? messageKeyForCode(err.code) : 'errors.UNKNOWN'))
    } finally {
      setBusy(false)
    }
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
          <FileOutput aria-hidden className="size-3.5" />
          {t('ats.title')}
        </p>
        <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
          {t('ats.intro')}
        </p>
      </header>

      <div className="flex flex-col gap-4 rounded-2xl bg-card p-6 ring-1 ring-foreground/10">
        <CvSelect cvs={cvs} value={selected} onChange={setSelected} />
        <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
          {t('ats.language')}
          <select
            value={atsLang}
            onChange={(e) => setAtsLang(e.target.value as 'tr' | 'en')}
            className="h-11 rounded-lg border border-border bg-background px-3 text-base font-medium text-foreground transition-all outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </select>
        </label>
        {error && (
          <p className="flex items-center gap-2 rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
            <AlertCircle aria-hidden className="size-4 shrink-0" />
            {error}
          </p>
        )}
        {done && (
          <p className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
            <CheckCircle2 aria-hidden className="size-4 shrink-0" />
            {t('ats.done')}
          </p>
        )}
        <Button onClick={convert} disabled={busy || !selected} className="h-11 gap-1.5 text-base">
          <Download aria-hidden className="size-4" />
          {busy ? t('ats.converting') : t('ats.convert')}
        </Button>
      </div>
    </main>
  )
}

export default function AtsPage() {
  return (
    <Suspense fallback={null}>
      <AtsPageInner />
    </Suspense>
  )
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `npx vitest run "src/app/(app)/ats/__tests__/page.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 7: Make CV detail view-only**

In `web/src/app/(app)/cv/[id]/page.tsx`:
- Delete the `convert()` function, the `busy`/`error`/`atsLang` state, and the whole `<div className="flex gap-2">…</div>` action block in the header (language select + convert button + score link) plus the `{error && …}` paragraph.
- Remove now-unused imports: `Link`, `useLocale`, `Download`, `Target`, `Mail` stays (contact line uses it), `AlertCircle`, `insertCv`, `ApiError`, `atsPdf`, `atsRewrite`, `messageKeyForCode`, `downloadBlob`, `Button`, `buttonVariants`, `cn`.
- The header keeps only the name + contact block.

Replace `web/src/app/(app)/cv/[id]/__tests__/page.test.tsx` with exactly (the convert-flow test moved to `/ats` in Step 3; only the render test remains, so the storage/api/download mocks go away):

```tsx
import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { CvRow } from '@/types/db'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
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

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) },
  }),
}))

vi.mock('@/lib/db', () => ({
  getCv: vi.fn(async () => ROW),
}))

import CvDetailPage from '@/app/(app)/cv/[id]/page'

it('renders the parsed CV preview', async () => {
  renderWithIntl(<CvDetailPage />)
  expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument()
  expect(screen.getByText(/Dev — AEC/)).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
})
```

- [ ] **Step 8: Full suite + typecheck**

Run (in `web/`): `npm test` then `npx tsc --noEmit`
Expected: all green. If parity fails, a key was removed from only one language file.

- [ ] **Step 9: Commit**

```bash
git add -A web/src
git commit -m "feat(web): standalone /ats page with CV selector; view-only CV detail"
```

---

### Task 3: `/score` page with CV selector, legacy redirect, dashboard links

**Files:**
- Create: `web/src/app/(app)/score/page.tsx`
- Create: `web/src/app/(app)/score/__tests__/page.test.tsx` (adapted from the old score test)
- Replace: `web/src/app/(app)/cv/[id]/score/page.tsx` with a redirect (delete its `__tests__/` dir)
- Modify: `web/src/components/CvCard.tsx` (score link → `/score?cv=`, new ATS link → `/ats?cv=`)
- Modify: `web/src/messages/en.json`, `tr.json` (`dashboard.atsAction` key)

**Interfaces:**
- Consumes: `CvSelect` from Task 2 (`{ cvs, value, onChange }`); `listCvs` from `@/lib/db`; everything the old score page used (`fetchJob`, `scoreCv`, `findJobByUrl`, `insertJob`, `findEvaluation`, `insertEvaluation`, `StarRating`, `messageKeyForCode`).
- Produces: route `/score` accepting `?cv=<id>`; `/cv/[id]/score` → 307 redirect to `/score?cv=<id>`.

- [ ] **Step 1: Add the dashboard ATS-action message**

`en.json` `"dashboard"`: add `"atsAction": "ATS",`
`tr.json` `"dashboard"`: add `"atsAction": "ATS",`

- [ ] **Step 2: Create the new score page**

Create `web/src/app/(app)/score/page.tsx`. It is the existing `web/src/app/(app)/cv/[id]/score/page.tsx` with these exact changes (everything else — BAND/bandFor, ReasonBlock, the `run()` body from `fetchJob` onward, the result JSX — is copied unchanged):

1. Imports: drop `useParams`, `getCv`; add `Suspense` to the react import, `useRouter, useSearchParams` from `next/navigation`, `listCvs` instead of `getCv`, and `CvSelect` from `@/components/CvSelect`.
2. State: replace `const { id } = useParams…` and `const [cv, setCv] = useState<CvRow | null>(null)` with:

```tsx
const router = useRouter()
const params = useSearchParams()
const [cvs, setCvs] = useState<CvRow[] | null>(null)
const [selected, setSelected] = useState<string>('')
const cv = cvs?.find((c) => c.id === selected) ?? null
```

3. Loader becomes:

```tsx
const load = useCallback(async () => {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) {
    router.replace('/login')
    return
  }
  const rows = await listCvs(supabase)
  setCvs(rows)
  const fromQuery = params.get('cv')
  setSelected(fromQuery && rows.some((r) => r.id === fromQuery) ? fromQuery : rows[0]?.id ?? '')
}, [supabase, router, params])
```

4. The `if (!cv)` loading guard becomes `if (!cvs)` (same skeleton JSX). Inside the returned form, insert `<CvSelect cvs={cvs} value={selected} onChange={(id) => { setSelected(id); setResult(null); setCached(false) }} />` as the first child of the form (above the URL label). Guard `run()` with `if (!cv) return` at the top.
5. The `<h1>` shows `{cv?.parsed_data.full_name ?? ''}`.
6. Component is renamed `ScorePageInner`; default export wraps it:

```tsx
export default function ScorePage() {
  return (
    <Suspense fallback={null}>
      <ScorePageInner />
    </Suspense>
  )
}
```

- [ ] **Step 3: Adapt the score page test**

Create `web/src/app/(app)/score/__tests__/page.test.tsx` as a copy of the old `cv/[id]/score` test with:
- `vi.mock('next/navigation', …)` — drop `useParams`; return STABLE instances (hoisted consts, not fresh objects per call — a fresh object per render causes an infinite re-render loop):

```tsx
const ROUTER = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
const PARAMS = new URLSearchParams('cv=c1')
vi.mock('next/navigation', () => ({
  useRouter: () => ROUTER,
  useSearchParams: () => PARAMS,
}))
```
- `vi.mock('@/lib/db', …)`: replace `getCv: vi.fn(async () => ROW)` with `listCvs: vi.fn(async () => [ROW])`.
- Import the page from `@/app/(app)/score/page`.
- All three test bodies stay identical (they find by label/button text, which is unchanged).

Delete the old test dir: `git rm -r "web/src/app/(app)/cv/[id]/score/__tests__"`

- [ ] **Step 4: Run the score tests**

Run: `npx vitest run "src/app/(app)/score/__tests__/page.test.tsx"`
Expected: PASS (3 tests).

- [ ] **Step 5: Replace the legacy route with a redirect**

Replace the entire content of `web/src/app/(app)/cv/[id]/score/page.tsx` with (server component; Next 16 `params` is a Promise — verify against `web/node_modules/next/dist/docs/`):

```tsx
import { redirect } from 'next/navigation'

export default async function LegacyScoreRedirect({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  redirect(`/score?cv=${id}`)
}
```

- [ ] **Step 6: Update CvCard links**

In `web/src/components/CvCard.tsx`:
- Add `FileOutput` to the lucide import.
- Change the score link `href` from `` `/cv/${cv.id}/score` `` to `` `/score?cv=${cv.id}` ``.
- After the score link, add:

```tsx
<Link
  href={`/ats?cv=${cv.id}`}
  className="inline-flex items-center gap-1.5 rounded-md bg-primary/8 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/14"
>
  <FileOutput aria-hidden className="size-4" />
  {t('atsAction')}
</Link>
```

Check the dashboard test for link-href assertions and update any `/cv/c1/score` expectation to `/score?cv=c1`.

- [ ] **Step 7: Full suite + typecheck**

Run (in `web/`): `npm test` then `npx tsc --noEmit`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add -A web/src
git commit -m "feat(web): standalone /score page, legacy score redirect, card links"
```

---

### Task 4: End-to-end verification

**Files:** none created — verification only.

- [ ] **Step 1: Production build**

Run (in `web/`, correct path casing!): `npm run build`
Expected: build succeeds; no `useSearchParams` Suspense warnings.

- [ ] **Step 2: Manual flow check**

Start both servers (`api`: `.venv\Scripts\uvicorn app.main:app --reload --port 8000`; `web`: `npm run dev`) and verify in the browser:
1. Landing / login / register show NO left panel.
2. `/dashboard` shows the panel; active item highlighted; Optimize entry disabled with "yakında".
3. Card "Skorla" opens `/score` with that CV preselected; scoring works end-to-end.
4. Card "ATS" opens `/ats` preselected; conversion downloads a PDF and the ATS copy appears on the dashboard.
5. `/cv/<id>` is view-only (no convert/score buttons); old `/cv/<id>/score` URL redirects to `/score?cv=<id>`.
6. Mobile width (devtools): panel renders as a horizontal strip under the navbar.

- [ ] **Step 3: Report**

Report any failures back before Faz 2 planning starts. If all pass, Faz 1 is done.
