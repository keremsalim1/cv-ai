# Signed-in Landing Redirect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in user who opens `/`, `/login` or `/register` is redirected to `/dashboard` by the proxy, with no flash of the marketing page or the sign-in form.

**Architecture:** `web/src/lib/protected.ts` gains a second predicate, `isGuestOnlyPath`, matching an exact list of paths (`/`, `/login`, `/register`). `web/src/proxy.ts` gains the mirror of its existing guard: where it already sends a signed-out visitor away from a protected path, it now sends a signed-in visitor away from a guest-only path. The same request's Supabase session is reused, so no extra round-trip. Same change closes the `/optimize` gap in `PROTECTED_PREFIXES`.

**Tech Stack:** Next.js 16.2.10 (`proxy.ts` file convention, the replacement for `middleware.ts`), `@supabase/ssr` 0.12, TypeScript, Vitest 4 with jsdom.

**Source spec:** `docs/superpowers/specs/2026-08-09-signed-in-landing-redirect-design.md`

## Global Constraints

- All paths below are relative to `web/`. Run every command from `C:\Users\ASUS\Desktop\cv-ai\web` (capital `D` in `Desktop` — lowercase breaks the Next build on this machine).
- Guest-only paths are matched **exactly**, never by prefix: `/` as a prefix matches every route in the app. `isProtectedPath` keeps its existing prefix matching.
- `/dashboard` must never be treated as guest-only. The two rules would otherwise redirect into each other forever.
- No changes to `src/app/page.tsx`, the login/register forms, the nav bar, or any panel page. The redirect lives in the proxy only.
- This repo's convention: the human runs `git add`/`git commit`/`git push`. Every task ends with a handoff step, not a commit executed by the agent. Never `--no-verify`.
- `AGENTS.md` in `web/`: this is Next 16, not the Next you remember. Consult `node_modules/next/dist/docs/` before inventing any API. The code in this plan only reuses what `src/proxy.ts` already does.

---

### Task 1: `isGuestOnlyPath`, plus the `/optimize` gap

**Files:**
- Modify: `web/src/lib/protected.ts:1-5` (whole file)
- Test: `web/src/lib/__tests__/protected.test.ts` (exists — extend it)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `export function isGuestOnlyPath(pathname: string): boolean` from `@/lib/protected`. Task 2 imports it. Also `PROTECTED_PREFIXES` grows by `'/optimize'`; `isProtectedPath(pathname: string): boolean` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `web/src/lib/__tests__/protected.test.ts` with the file below. It keeps every existing row, adds `/optimize` to the protected table, and adds a second table for the new predicate. The `/loginx` and `/registered` rows are what pin exact matching — under prefix matching they would both come back `true`.

```ts
import { isGuestOnlyPath, isProtectedPath } from '@/lib/protected'

it.each([
  ['/dashboard', true],
  ['/dashboard/anything', true],
  ['/cv/abc', true],
  ['/cv/abc/score', true],
  ['/score', true],
  ['/score/anything', true],
  ['/ats', true],
  ['/ats/anything', true],
  ['/optimize', true],
  ['/optimize/anything', true],
  ['/', false],
  ['/login', false],
  ['/register', false],
  ['/auth/callback', false],
  ['/cvsomething', false],
])('isProtectedPath %s -> %s', (path, expected) => {
  expect(isProtectedPath(path)).toBe(expected)
})

it.each([
  ['/', true],
  ['/login', true],
  ['/register', true],
  ['/dashboard', false],
  ['/cv/abc', false],
  ['/optimize', false],
  ['/auth/callback', false],
  // Exact match, not prefix: these must not be caught.
  ['/loginx', false],
  ['/registered', false],
  ['/login/reset', false],
])('isGuestOnlyPath %s -> %s', (path, expected) => {
  expect(isGuestOnlyPath(path)).toBe(expected)
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- src/lib/__tests__/protected.test.ts`

Expected: FAIL. The `isGuestOnlyPath` rows error with something like `isGuestOnlyPath is not a function` (the import is `undefined`), and the two `/optimize` rows fail with `expected false to be true`.

- [ ] **Step 3: Write the implementation**

Replace the whole of `web/src/lib/protected.ts` with:

```ts
const PROTECTED_PREFIXES = ['/dashboard', '/cv', '/score', '/ats', '/applications', '/optimize']

// Exact match, not prefix: '/' as a prefix would swallow every path in the app.
const GUEST_ONLY_PATHS = ['/', '/login', '/register']

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))
}

export function isGuestOnlyPath(pathname: string): boolean {
  return GUEST_ONLY_PATHS.includes(pathname)
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- src/lib/__tests__/protected.test.ts`

Expected: PASS, 23 test cases (13 from the first table, 10 from the second).

- [ ] **Step 5: Hand off for commit**

Do not run `git commit` — this repo's owner commits. Report that Task 1 is done and show them the suggested command:

```bash
git add web/src/lib/protected.ts web/src/lib/__tests__/protected.test.ts
git commit -m "feat(web): add isGuestOnlyPath and protect /optimize"
```

---

### Task 2: The proxy redirect

**Files:**
- Modify: `web/src/proxy.ts:26-32` (add a branch after the existing guard)
- Create: `web/src/lib/__tests__/proxy.test.ts`

**Interfaces:**
- Consumes: `isGuestOnlyPath(pathname: string): boolean` from `@/lib/protected` (Task 1).
- Produces: no new exports. `proxy(request: NextRequest): Promise<NextResponse>` keeps its signature.

Test-file placement note: the test lives in `src/lib/__tests__/` beside the other unit tests even though `proxy.ts` sits at `src/proxy.ts`. That is what the spec calls for, and `src/` has no other `__tests__` directory at its root.

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/__tests__/proxy.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const getUser = vi.fn()
vi.mock('@supabase/ssr', () => ({
  createServerClient: () => ({ auth: { getUser } }),
}))

import { proxy } from '@/proxy'

function signedIn() {
  getUser.mockResolvedValue({ data: { user: { id: 'u-1' } } })
}

function signedOut() {
  getUser.mockResolvedValue({ data: { user: null } })
}

async function landsOn(path: string): Promise<string | null> {
  const res = await proxy(new NextRequest(`http://localhost:3000${path}`))
  return res.headers.get('location')
}

beforeEach(() => {
  getUser.mockReset()
})

describe('the proxy auth rules', () => {
  it('sends a signed-in visitor from the marketing page to the panel', async () => {
    signedIn()
    expect(await landsOn('/')).toBe('http://localhost:3000/dashboard')
  })

  it('sends a signed-in visitor from the sign-in form to the panel', async () => {
    signedIn()
    expect(await landsOn('/login')).toBe('http://localhost:3000/dashboard')
  })

  it('sends a signed-in visitor from the registration form to the panel', async () => {
    signedIn()
    expect(await landsOn('/register')).toBe('http://localhost:3000/dashboard')
  })

  it('leaves the marketing page alone for a signed-out visitor', async () => {
    signedOut()
    expect(await landsOn('/')).toBeNull()
  })

  it('never bounces a signed-in visitor off the panel', async () => {
    // If /dashboard were ever guest-only, the two rules would loop forever.
    signedIn()
    expect(await landsOn('/dashboard')).toBeNull()
  })

  it('still sends a signed-out visitor from the panel to sign-in', async () => {
    signedOut()
    expect(await landsOn('/dashboard')).toBe('http://localhost:3000/login')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- src/lib/__tests__/proxy.test.ts`

Expected: FAIL on the first three cases with `expected null to be 'http://localhost:3000/dashboard'` — the proxy does not redirect signed-in visitors yet. The last three cases already pass; that is intended, they pin behaviour this change must not break.

- [ ] **Step 3: Write the implementation**

In `web/src/proxy.ts`, widen the import on line 3:

```ts
import { isGuestOnlyPath, isProtectedPath } from '@/lib/protected'
```

Then add the mirror branch immediately after the existing `if (!user && isProtectedPath(...))` block and before `return response`:

```ts
  if (user && isGuestOnlyPath(request.nextUrl.pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/dashboard'
    return NextResponse.redirect(url)
  }
```

The finished tail of `proxy()` reads:

```ts
  const { data: { user } } = await supabase.auth.getUser()

  if (!user && isProtectedPath(request.nextUrl.pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  if (user && isGuestOnlyPath(request.nextUrl.pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/dashboard'
    return NextResponse.redirect(url)
  }

  return response
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- src/lib/__tests__/proxy.test.ts`

Expected: PASS, 6 tests.

- [ ] **Step 5: Run the full web suite, typecheck and lint**

Run each, and paste the real output when reporting:

```bash
npm test
npm run typecheck
npm run lint
```

Expected: the suite passes with no new failures; `typecheck` prints nothing; `lint` reports no new errors. `src/app/(app)/ats/page.tsx` has pre-existing lint errors — leave them, but say so explicitly rather than claiming a clean run.

- [ ] **Step 6: Hand off for commit**

Do not run `git commit`. Report Task 2 as done with the test output, and show the suggested command:

```bash
git add web/src/proxy.ts web/src/lib/__tests__/proxy.test.ts
git commit -m "fix(web): land signed-in visitors on the dashboard, not the marketing page"
```

---

## Manual verification (after both tasks)

Automated tests mock `@supabase/ssr`, so they never exercise a real session cookie. One pass through the running app closes that gap:

- [ ] Start the dev server: `npm run dev` from `C:\Users\ASUS\Desktop\cv-ai\web`.
- [ ] Signed out, open `http://localhost:3000/` — the marketing page renders and stays.
- [ ] Sign in with email and password (Google sign-in refuses assisted browsers; use email/password).
- [ ] Open `http://localhost:3000/` — the panel appears at `/dashboard`, with no flash of the marketing page.
- [ ] Open `http://localhost:3000/login` and `/register` — both land on `/dashboard`.
- [ ] Sign out, then open `http://localhost:3000/optimize` — the proxy now sends you to `/login`.

## Known consequence

A signed-in user cannot reach the marketing page at all — that is the intent, not an oversight. If it ever needs to be viewable while signed in, the answer is a separate public URL, not a softer rule.
