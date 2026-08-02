# UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the product a deliberate type system, one spacing rhythm, one depth language, and spring-based motion — without changing a single route, control, or string.

**Architecture:** A foundation lands first: the `motion` dependency, a provider that sets the site-wide reduced-motion policy, three spring tokens, and four primitives every surface composes. Typography and depth become CSS roles in `globals.css`. Only then are surfaces swept, one commit per surface, so a regression bisects to one file.

**Tech Stack:** Next.js 16.2.10 (App Router), React 19, Tailwind v4, `motion` (imported as `motion/react`), next-intl, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-02-ui-refresh-design.md`

## Global Constraints

- **Never import from `framer-motion`.** The package is `motion`; React entry is `motion/react`.
- **No text, no role, no accessible name changes.** The existing 101 web tests must pass untouched. A broken test is evidence the refresh went too far — fix the code, not the test.
- **Spacing tiers are 8 / 12 / 16 / 24 / 40 / 64 only**, which map exactly onto Tailwind `2 / 3 / 4 / 6 / 10 / 16`. No other spacing utility may be introduced.
- **Only `transform` and `opacity` are animated**, with one documented exception: the disclosure panel animates `height` (see Task 3).
- **Every user-facing string exists in both `web/src/messages/tr.json` and `web/src/messages/en.json`.** A key present in only one is a bug.
- **Read `node_modules/next/dist/docs/` before using a Next.js API** — `web/AGENTS.md` requires it; this Next version has breaking changes from training data.
- Run web tests with `npm test` from `web/`, typecheck with `npx tsc --noEmit`, lint with `npm run lint`.
- Commit messages carry no `Co-Authored-By` or `Claude-Session` trailers.

## File Structure

**Foundation**
- Create `web/src/lib/motion.ts` — the three spring tokens and the stagger step. Pure data; no React.
- Create `web/src/components/motion/MotionProvider.tsx` — one `MotionConfig`, site-wide reduced-motion policy.
- Create `web/src/components/motion/Stagger.tsx` — `Stagger` + `StaggerItem`.
- Create `web/src/components/motion/PressableCard.tsx` — hover lift and press feedback.
- Create `web/src/components/motion/Disclosure.tsx` — animated height panel.
- Modify `web/src/app/globals.css` — six type roles, three depth levels.
- Modify `web/src/app/(app)/layout.tsx` — mount the provider.

**Surfaces (swept one per task)**
- `applications/` (new, Task 4) · `dashboard` + `CvCard` · app shell (`layout`, `AppSidebar`, `NavBar`) · `score` / `ats` / `optimize` / `cv/[id]` · landing / login / register.

---

### Task 1: The motion foundation

**Files:**
- Create: `web/src/lib/motion.ts`
- Create: `web/src/components/motion/MotionProvider.tsx`
- Modify: `web/src/app/(app)/layout.tsx`
- Test: `web/src/components/motion/__tests__/MotionProvider.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces:
  ```ts
  // lib/motion.ts
  export const snap: Transition      // press feedback
  export const flow: Transition      // enter/exit, hover
  export const settle: Transition    // height and layout
  export const STAGGER_STEP: number  // seconds between staggered children

  // components/motion/MotionProvider.tsx
  export function MotionProvider({ children }: { children: React.ReactNode }): JSX.Element
  ```

- [ ] **Step 1: Install the dependency**

Run from `web/`:

```bash
npm install motion
```

Confirm the installed version and that `framer-motion` is absent:

```bash
node -p "require('./node_modules/motion/package.json').version"
npm ls framer-motion
```

Expected: a version prints; `npm ls framer-motion` reports it is not installed.

- [ ] **Step 2: Write the failing test**

Create `web/src/components/motion/__tests__/MotionProvider.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { MotionProvider } from '@/components/motion/MotionProvider'
import { flow, settle, snap, STAGGER_MAX_ITEMS, STAGGER_STEP } from '@/lib/motion'

it('renders its children', () => {
  render(<MotionProvider><p>hello</p></MotionProvider>)
  expect(screen.getByText('hello')).toBeInTheDocument()
})

it('every speed is one spring family, fastest to slowest', () => {
  for (const t of [snap, flow, settle]) {
    expect(t.type).toBe('spring')
    expect(t.bounce).toBeLessThanOrEqual(0.25)
  }
  // A press must outrun a hover, and a hover must outrun a height change,
  // or the interface feels like three different products.
  expect(snap.visualDuration).toBeLessThan(flow.visualDuration as number)
  expect(flow.visualDuration).toBeLessThan(settle.visualDuration as number)
})

it('staggers inside the perceptible band', () => {
  // Below 30ms a stagger reads as a single event; above 50ms it reads as a queue.
  expect(STAGGER_STEP).toBeGreaterThanOrEqual(0.03)
  expect(STAGGER_STEP).toBeLessThanOrEqual(0.05)
})

it('caps the entrance so a long list never becomes a queue', () => {
  // A user with 200 applications must not wait 7 seconds for the last row.
  const worstCase = STAGGER_STEP * STAGGER_MAX_ITEMS
  expect(worstCase).toBeLessThanOrEqual(0.5)
})
```

Then, in a **separate file** `web/src/components/motion/__tests__/reducedMotion.test.tsx` — it needs a module mock, which must not leak into the test above:

```tsx
import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

const seen: Record<string, unknown> = {}
vi.mock('motion/react', () => ({
  MotionConfig: (props: Record<string, unknown>) => {
    Object.assign(seen, props)
    return <>{props.children as React.ReactNode}</>
  },
}))

it('defers to the operating system on reduced motion', async () => {
  // The single most important accessibility decision in this refresh, and the
  // only one a component could silently opt out of. Motion's default is
  // "never" — landing on that by accident would ship motion to people who
  // asked for none.
  const { MotionProvider } = await import('@/components/motion/MotionProvider')
  render(<MotionProvider><p>x</p></MotionProvider>)
  expect(seen.reducedMotion).toBe('user')
})
```

- [ ] **Step 3: Run it and watch it fail**

Run: `npm test -- src/components/motion`
Expected: FAIL — cannot resolve `@/components/motion/MotionProvider`.

- [ ] **Step 4: Write the spring tokens**

Create `web/src/lib/motion.ts`:

```ts
import type { Transition } from 'motion/react'

/**
 * One spring family, three speeds. `visualDuration` is the time the motion
 * appears to take — the settle happens after it — which is what makes a spring
 * coordinate with time-based animation instead of fighting it.
 */
export const snap: Transition = { type: 'spring', visualDuration: 0.18, bounce: 0.15 }
export const flow: Transition = { type: 'spring', visualDuration: 0.28, bounce: 0.2 }
export const settle: Transition = { type: 'spring', visualDuration: 0.42, bounce: 0.18 }

/** Seconds between staggered children. */
export const STAGGER_STEP = 0.035

/**
 * A stagger is a rhythm, not a queue. Unbounded, a user with 200 applications
 * waits 7 seconds for the last row — so the delay stops growing after this many
 * items and everything past it arrives together.
 */
export const STAGGER_MAX_ITEMS = 12
```

- [ ] **Step 5: Write the provider**

Create `web/src/components/motion/MotionProvider.tsx`:

```tsx
'use client'
import { MotionConfig } from 'motion/react'
import { flow } from '@/lib/motion'

/**
 * `reducedMotion="user"` is the whole accessibility story: Motion disables
 * transform and layout animations when the OS asks for reduced motion, and
 * keeps opacity. Doing this per-component would guarantee somewhere gets missed.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={flow}>
      {children}
    </MotionConfig>
  )
}
```

- [ ] **Step 6: Mount it at the root**

In `web/src/app/layout.tsx` — the **root** layout, not `(app)/layout.tsx` — wrap the body's children in `<MotionProvider>…</MotionProvider>` and add the import. Change nothing else in that file.

The root, because the landing, login and register pages live outside `(app)`. Mounting inside `(app)` first and moving it later would leave those three pages with no reduced-motion policy for the length of the sweep, and the policy is the one thing that must never be partially applied.

If `app/layout.tsx` is a server component, do not add `'use client'` to it — `MotionProvider` already carries the directive, and a client provider can wrap server children.

- [ ] **Step 7: Run the tests**

Run: `npm test && npx tsc --noEmit`
Expected: PASS — 3 new tests, and all 101 pre-existing tests still green.

- [ ] **Step 8: Commit**

```bash
git add web/package.json web/package-lock.json web/src/lib/motion.ts \
        web/src/components/motion web/src/app/layout.tsx
git commit -m "feat(web): one spring family and a site-wide reduced-motion policy"
```

---

### Task 2: Type roles and depth

**Files:**
- Modify: `web/src/app/globals.css`

**Interfaces:**
- Consumes: nothing.
- Produces: CSS classes `.type-display`, `.type-title`, `.type-heading`, `.type-body`, `.type-ui`, `.type-meta`; Tailwind shadow utilities `shadow-e1`, `shadow-e2`, `shadow-e3`.

**Note on testing:** this task ships CSS only. There is nothing to unit-test honestly — do not invent a test that asserts a stylesheet contains a string. Verification is: the build succeeds, the existing suite stays green, and the roles render at the stated sizes in a browser. Say so in the report rather than claiming test coverage.

- [ ] **Step 1: Add the depth scale to the theme**

In `web/src/app/globals.css`, inside the existing `@theme inline { … }` block, after the `--color-ink` line, add:

```css
  --shadow-e1: var(--elevation-1);
  --shadow-e2: var(--elevation-2);
  --shadow-e3: var(--elevation-3);
```

- [ ] **Step 2: Define the depth values for both themes**

In the `:root { … }` block, after the `--radius: 0.5rem;` line, add:

```css
  /* One depth language. Level 1 is a card at rest, 2 is a card under the
     pointer, 3 is something floating over the page. Nothing else. */
  --elevation-1: 0 1px 2px rgb(0 0 0 / 0.04);
  --elevation-2: 0 8px 24px -12px rgb(0 0 0 / 0.18);
  --elevation-3: 0 24px 48px -20px rgb(0 0 0 / 0.28);
```

In the `.dark { … }` block, after the `--sidebar-ring` line, add:

```css
  /* Shadow reads as absence of light: on a dark ground it must be darker and
     deeper, not the same values at lower opacity. */
  --elevation-1: 0 1px 2px rgb(0 0 0 / 0.3);
  --elevation-2: 0 8px 24px -12px rgb(0 0 0 / 0.55);
  --elevation-3: 0 24px 48px -20px rgb(0 0 0 / 0.7);
```

- [ ] **Step 3: Add the type roles, and retire the one they duplicate**

`globals.css:196` already defines `.font-display`, which sets the same
`font-family: var(--font-heading)` and `font-feature-settings: "ss01"` that
`.type-display` and `.type-title` are about to set. Leaving both is how a type
system rots — the exact fault this refresh exists to fix, recreated in the act
of fixing it.

So: **replace** `.font-display` with the roles below. It has 13 call sites; each
one is a heading that becomes `.type-title` (page headings) or `.type-display`
(the landing hero), and every one of those files is already being touched by
Tasks 4-8. Find them with:

```bash
grep -rn "font-display" web/src --include=*.tsx
```

Delete the `.font-display` rule, and in the existing `@layer components { … }`
block add:

```css
  /* Six roles. A component adopts one; it does not assemble its own from
     size + weight + family utilities, which is how a type system rots. */
  .type-display {
    font-family: var(--font-heading);
    font-size: clamp(2.5rem, 4vw, 3.5rem);
    line-height: 1.05;
    letter-spacing: -0.02em;
    font-weight: 600;
    font-feature-settings: "ss01";
  }
  .type-title {
    font-family: var(--font-heading);
    font-size: 2.25rem;
    line-height: 1.15;
    letter-spacing: -0.015em;
    font-weight: 600;
    font-feature-settings: "ss01";
  }
  .type-heading {
    font-size: 1.375rem;
    line-height: 1.3;
    letter-spacing: -0.01em;
    font-weight: 600;
  }
  .type-body {
    font-size: 1rem;
    line-height: 1.6;
  }
  .type-ui {
    font-size: 0.875rem;
    line-height: 1.45;
    font-weight: 500;
  }
  .type-meta {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    line-height: 1.4;
    letter-spacing: 0.04em;
    /* Metadata is where numbers change while the user is reading them.
       Proportional figures make the line twitch on every update. */
    font-variant-numeric: tabular-nums;
  }
```

- [ ] **Step 4: Verify the build and the suite**

Run from `web/`:

```bash
grep -rn "font-display" web/src --include=*.tsx | wc -l   # must be 0
npm run build
npm test
```

Expected: no `font-display` references remain, the build succeeds, and all 101 tests pass. The headings now render at 36px instead of 30px; if a test asserted on a class name rather than on text, that is a test worth fixing — class names are not behavior.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/globals.css
git commit -m "feat(web): six type roles and one depth scale"
```

---

### Task 3: The motion primitives

**Files:**
- Create: `web/src/components/motion/Stagger.tsx`
- Create: `web/src/components/motion/PressableCard.tsx`
- Create: `web/src/components/motion/Disclosure.tsx`
- Test: `web/src/components/motion/__tests__/primitives.test.tsx`

**Interfaces:**
- Consumes: `snap`, `flow`, `settle`, `STAGGER_STEP` from `@/lib/motion`.
- Produces:
  ```tsx
  export function Stagger(props: { children: React.ReactNode; className?: string; as?: 'div' | 'ul' }): JSX.Element
  export function StaggerItem(props: { children: React.ReactNode; className?: string; as?: 'div' | 'li' }): JSX.Element
  export function PressableCard(props: { children: React.ReactNode; className?: string; as?: 'div' | 'li' }): JSX.Element
  export function Disclosure(props: { open: boolean; children: React.ReactNode; className?: string }): JSX.Element
  ```

- [ ] **Step 1: Write the failing tests**

Create `web/src/components/motion/__tests__/primitives.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { Disclosure } from '@/components/motion/Disclosure'
import { PressableCard } from '@/components/motion/PressableCard'
import { Stagger, StaggerItem } from '@/components/motion/Stagger'

it('a stagger renders a real list when asked for one', () => {
  render(
    <Stagger as="ul" className="grid">
      <StaggerItem as="li">first</StaggerItem>
      <StaggerItem as="li">second</StaggerItem>
    </Stagger>
  )
  // Motion must not cost us the semantics: a list has to stay a list.
  expect(screen.getByRole('list')).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
})

it('a pressable card keeps its content addressable', () => {
  render(<PressableCard className="card">clickable content</PressableCard>)
  expect(screen.getByText('clickable content')).toBeInTheDocument()
})

it('a closed disclosure exposes nothing to assistive technology', () => {
  render(<Disclosure open={false}><p>the evidence</p></Disclosure>)
  expect(screen.queryByText('the evidence')).not.toBeInTheDocument()
})

it('an open disclosure exposes its content immediately, not after animating', () => {
  render(<Disclosure open><p>the evidence</p></Disclosure>)
  expect(screen.getByText('the evidence')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `npm test -- src/components/motion`
Expected: FAIL — cannot resolve `@/components/motion/Stagger`.

- [ ] **Step 3: Write the stagger**

Create `web/src/components/motion/Stagger.tsx`:

```tsx
'use client'
import { motion, type Variants } from 'motion/react'
import { flow, STAGGER_MAX_ITEMS, STAGGER_STEP } from '@/lib/motion'

const container: Variants = { hidden: {}, show: {} }

/**
 * The delay is computed per index rather than handed to `stagger()`, because
 * `stagger()` keeps multiplying forever: a 200-row list would take seven
 * seconds to finish arriving. Past the cap every remaining row shares the last
 * delay, so a long list still has a rhythm but never a queue.
 */
const item: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { ...flow, delay: Math.min(index, STAGGER_MAX_ITEMS) * STAGGER_STEP },
  }),
}

export function Stagger({ children, className, as = 'div' }: {
  children: React.ReactNode
  className?: string
  as?: 'div' | 'ul'
}) {
  const Tag = as === 'ul' ? motion.ul : motion.div
  return (
    <Tag variants={container} initial="hidden" animate="show" className={className}>
      {children}
    </Tag>
  )
}

export function StaggerItem({ children, className, index = 0, as = 'div' }: {
  children: React.ReactNode
  className?: string
  /** Position in the list. Drives the capped delay; pass the map index. */
  index?: number
  as?: 'div' | 'li'
}) {
  const Tag = as === 'li' ? motion.li : motion.div
  return (
    <Tag variants={item} custom={index} className={className}>
      {children}
    </Tag>
  )
}
```

- [ ] **Step 4: Write the pressable card**

Create `web/src/components/motion/PressableCard.tsx`:

```tsx
'use client'
import { motion } from 'motion/react'
import { flow, snap } from '@/lib/motion'

/**
 * Hover lifts, press compresses. Both are transform-only, which is what lets
 * the reduced-motion policy switch them off cleanly.
 */
export function PressableCard({ children, className, as = 'div' }: {
  children: React.ReactNode
  className?: string
  as?: 'div' | 'li'
}) {
  const Tag = as === 'li' ? motion.li : motion.div
  return (
    <Tag
      className={className}
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.985, transition: snap }}
      transition={flow}
    >
      {children}
    </Tag>
  )
}
```

- [ ] **Step 5: Write the disclosure**

Create `web/src/components/motion/Disclosure.tsx`:

```tsx
'use client'
import { AnimatePresence, motion } from 'motion/react'
import { settle } from '@/lib/motion'

/**
 * The one place we animate a non-transform property. A disclosure that scales
 * instead of growing distorts its own text, and one that snaps open loses the
 * connection between the button and what it revealed. Motion animates to
 * `height: "auto"` by measuring, so no layout projection is involved.
 */
export function Disclosure({ open, children, className }: {
  open: boolean
  children: React.ReactNode
  className?: string
}) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          key="panel"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={settle}
          style={{ overflow: 'hidden' }}
          className={className}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 6: Run the tests**

Run: `npm test && npx tsc --noEmit`
Expected: PASS (4 new tests, 101 pre-existing still green).

If a test fails with `ResizeObserver is not defined`, add this to the top of `web/vitest.setup.ts` and re-run — jsdom does not implement it:

```ts
global.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
```

- [ ] **Step 7: Commit**

```bash
git add web/src/components/motion web/vitest.setup.ts
git commit -m "feat(web): stagger, press, and disclosure primitives"
```

---

### Task 4: The applications page

**Supersedes Task 13 of `docs/superpowers/plans/2026-07-27-inbox-status-tracking.md`.** That task's markup predates this refresh and its `gmailConsentUrl` call predates the `state` parameter added in Task 12. Build this instead; do not build both.

**Files:**
- Create: `web/src/app/(app)/applications/page.tsx`
- Create: `web/src/components/applications/StageBadge.tsx`
- Create: `web/src/components/applications/ConnectGmailCard.tsx`
- Create: `web/src/components/applications/ApplicationCard.tsx`
- Modify: `web/src/components/AppSidebar.tsx`, `web/src/lib/protected.ts`
- Modify: `web/src/messages/tr.json`, `web/src/messages/en.json`
- Modify: `web/README.md`
- Test: `web/src/app/(app)/applications/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `listApplications`, `listApplicationEvents` from `@/lib/db`; `inboxStatus`, `inboxSync`, `inboxConnect`, `InboxStatus` from `@/lib/api`; `gmailConsentUrl`, `newOAuthState`, `rememberOAuthState`, `takeOAuthState`, `GMAIL_REDIRECT_PATH` from `@/lib/gmailOAuth`; `Stagger`, `StaggerItem`, `PressableCard`, `Disclosure` from `@/components/motion/*`.
- Produces: the `/applications` route.

**Two deviations from the superseded task, both deliberate:**

1. **The connect control is a `button`, not a link.** The OAuth `state` must be stored before navigating. Computing it during render (`useState(newOAuthState)`) produces a different value on server and client, so the `href` would mismatch at hydration. A button generates the state on click, stores it, then navigates. The test asserts `role: 'button'` accordingly.
2. **The page verifies `state` before exchanging the code.** Task 12 generates and forwards it but nothing checks it yet, which means it currently buys nothing. This is the carry-forward from that task and the security-relevant part of this one.

- [ ] **Step 1: Add the translations**

In `web/src/messages/tr.json`, add a top-level `"applications"` block:

```json
  "applications": {
    "title": "Başvurularım",
    "intro": "Gmail'ini bağla, şirketlerden gelen cevapları burada topluca gör.",
    "connect": "Gmail'i bağla",
    "connectExplain": "Sadece başvuru maillerini okuruz — hiçbir mail göndermez, silmez ve kişisel yazışmalarını indirmeyiz. İstediğin an bağlantıyı kesebilirsin.",
    "connected": "Gmail'e bağlı",
    "disconnect": "Bağlantıyı kes",
    "refresh": "Yenile",
    "refreshing": "Gelen kutusu taranıyor…",
    "syncedAt": "{time} güncellendi",
    "neverSynced": "Henüz taranmadı",
    "partial": "Kısmen güncellendi — Gmail sınırına takıldık, birazdan tekrar dene.",
    "denied": "Gmail bağlantısına izin verilmedi.",
    "revoked": "Gmail bağlantın sona ermiş. Yeniden bağla.",
    "empty": "Henüz başvuru yok.",
    "why": "Neden?",
    "noEvents": "Bu başvuru için henüz bir e-posta görmedik.",
    "eventFrom": "Gönderen",
    "unknownCompany": "Şirket belirtilmemiş",
    "stage": {
      "received": "Alındı",
      "in_review": "Değerlendirmede",
      "interview": "Mülakat",
      "offer": "Teklif",
      "rejected": "Ret"
    }
  },
```

In `web/src/messages/en.json`, the same block:

```json
  "applications": {
    "title": "My applications",
    "intro": "Connect Gmail and see every company's reply in one place.",
    "connect": "Connect Gmail",
    "connectExplain": "We only read application emails — we never send or delete anything, and we don't download your personal correspondence. Disconnect whenever you like.",
    "connected": "Gmail connected",
    "disconnect": "Disconnect",
    "refresh": "Refresh",
    "refreshing": "Scanning your inbox…",
    "syncedAt": "updated {time}",
    "neverSynced": "Not scanned yet",
    "partial": "Partially updated — we hit a Gmail limit. Try again shortly.",
    "denied": "Gmail access was not granted.",
    "revoked": "Your Gmail connection has expired. Reconnect to continue.",
    "empty": "No applications yet.",
    "why": "Why?",
    "noEvents": "We haven't seen an email for this application yet.",
    "eventFrom": "From",
    "unknownCompany": "Company not stated",
    "stage": {
      "received": "Received",
      "in_review": "In review",
      "interview": "Interview",
      "offer": "Offer",
      "rejected": "Rejected"
    }
  },
```

Also add `"applications": "Başvurularım"` to the `sidebar` block in `tr.json` and `"applications": "My applications"` to the `sidebar` block in `en.json`.

(`errors.GMAIL_DISCONNECTED` already exists in both files — it landed with Task 12.)

- [ ] **Step 2: Write the failing page tests**

Create `web/src/app/(app)/applications/__tests__/page.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import ApplicationsPage from '../page'

const searchParams = new URLSearchParams()
vi.mock('next/navigation', () => {
  const router = { push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }
  return { useRouter: () => router, useSearchParams: () => searchParams }
})

const listApplications = vi.fn()
const listApplicationEvents = vi.fn()
vi.mock('@/lib/db', () => ({
  listApplications: (...a: unknown[]) => listApplications(...a),
  listApplicationEvents: (...a: unknown[]) => listApplicationEvents(...a),
}))

const inboxStatus = vi.fn()
const inboxSync = vi.fn()
const inboxConnect = vi.fn()
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  inboxStatus: (...a: unknown[]) => inboxStatus(...a),
  inboxSync: (...a: unknown[]) => inboxSync(...a),
  inboxConnect: (...a: unknown[]) => inboxConnect(...a),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) } }),
}))

const application = (over = {}) => ({
  id: 'a1', user_id: 'u1', url: 'https://acme.com/j', company: 'Acme',
  title: 'Backend Engineer', stage: 'rejected', stage_updated_at: '2026-07-27T10:00:00Z',
  source: 'email', status: 'external', cv_id: null, optimized_cv_id: null,
  job_text: null, cover_letter: null, qa: {}, changes: [],
  created_at: '2026-07-20T10:00:00Z', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  for (const k of [...searchParams.keys()]) searchParams.delete(k)
  listApplications.mockResolvedValue([])
  listApplicationEvents.mockResolvedValue([])
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: new Date().toISOString(), status: 'active' })
  inboxSync.mockResolvedValue({ scanned: 0, classified: 0, created: 0, updated: [], partial: false })
})

it('offers to connect Gmail when no mailbox is linked', async () => {
  inboxStatus.mockResolvedValue({ connected: false, email: null, last_synced_at: null, status: null })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByRole('button', { name: "Gmail'i bağla" })).toBeInTheDocument()
  expect(screen.getByText(/kişisel yazışmalarını indirmeyiz/)).toBeInTheDocument()
})

it('shows each application with its stage', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText('Acme')).toBeInTheDocument()
  expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
  expect(screen.getByText('Ret')).toBeInTheDocument()
})

it('reveals the email behind a stage when asked why', async () => {
  listApplications.mockResolvedValue([application()])
  listApplicationEvents.mockResolvedValue([{
    id: 'e1', subject: 'Update on your application', from_address: 'no-reply@greenhouse.io',
    received_at: '2026-07-27T10:00:00Z', detected_stage: 'rejected',
    evidence: 'We have decided to move forward with other candidates.',
  }])
  renderWithIntl(<ApplicationsPage />)

  await userEvent.click(await screen.findByRole('button', { name: 'Neden?' }))

  expect(await screen.findByText(/move forward with other candidates/)).toBeInTheDocument()
  expect(screen.getByText(/no-reply@greenhouse.io/)).toBeInTheDocument()
})

it('syncs on demand and reloads the list', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Acme')
  listApplications.mockClear()

  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))

  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
  await waitFor(() => expect(listApplications).toHaveBeenCalled())
})

it('does not sync on open when the last scan is recent', async () => {
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await waitFor(() => expect(inboxStatus).toHaveBeenCalled())
  expect(inboxSync).not.toHaveBeenCalled()
})

it('syncs on open when the last scan is stale', async () => {
  inboxStatus.mockResolvedValue({
    connected: true, email: 'ada@example.com', status: 'active',
    last_synced_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  })
  renderWithIntl(<ApplicationsPage />)
  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
})

it('tells the user when the connection has been revoked', async () => {
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: null, status: 'revoked' })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText(/Gmail bağlantın sona ermiş/)).toBeInTheDocument()
})

it('says so when a sync was cut short', async () => {
  inboxSync.mockResolvedValue({ scanned: 5, classified: 2, created: 0, updated: [], partial: true })
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))
  expect(await screen.findByText(/Kısmen güncellendi/)).toBeInTheDocument()
})

it('exchanges the code when the returned state matches the one we stored', async () => {
  sessionStorage.setItem('gmail_oauth_state', 'st-1')
  searchParams.set('gmail_code', 'auth-code')
  searchParams.set('gmail_state', 'st-1')

  renderWithIntl(<ApplicationsPage />)

  await waitFor(() => expect(inboxConnect).toHaveBeenCalledWith(
    'auth-code', expect.stringContaining('/auth/gmail/callback')
  ))
})

it('refuses a code whose state we never issued', async () => {
  // Someone else's authorization code, walked into our callback. Exchanging it
  // would attach the attacker's mailbox to this account.
  sessionStorage.setItem('gmail_oauth_state', 'st-mine')
  searchParams.set('gmail_code', 'attacker-code')
  searchParams.set('gmail_state', 'st-theirs')

  renderWithIntl(<ApplicationsPage />)

  expect(await screen.findByText(/izin verilmedi/)).toBeInTheDocument()
  expect(inboxConnect).not.toHaveBeenCalled()
})

it('refuses a code when no flow was started in this tab', async () => {
  searchParams.set('gmail_code', 'auth-code')
  searchParams.set('gmail_state', 'st-1')

  renderWithIntl(<ApplicationsPage />)

  expect(await screen.findByText(/izin verilmedi/)).toBeInTheDocument()
  expect(inboxConnect).not.toHaveBeenCalled()
})
```

- [ ] **Step 3: Run them and watch them fail**

Run: `npm test -- src/app/\(app\)/applications`
Expected: FAIL — cannot resolve `../page`.

- [ ] **Step 4: Build the stage badge**

Create `web/src/components/applications/StageBadge.tsx`:

```tsx
'use client'
import { AnimatePresence, motion } from 'motion/react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { flow } from '@/lib/motion'
import type { ApplicationStage } from '@/types/db'

const TONE: Record<ApplicationStage, string> = {
  received: 'bg-muted text-muted-foreground ring-border',
  in_review: 'bg-primary/8 text-primary ring-primary/15',
  interview: 'bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400',
  offer: 'bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400',
  rejected: 'bg-destructive/8 text-destructive ring-destructive/15',
}

/**
 * Keyed on the stage so a sync that moves an application crossfades the badge
 * instead of swapping the text underneath the user. This is the one animation
 * here that carries information rather than polish.
 */
export function StageBadge({ stage }: { stage: ApplicationStage }) {
  const t = useTranslations('applications.stage')
  return (
    <span className="relative inline-grid shrink-0">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={stage}
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.94 }}
          transition={flow}
          className={cn(
            'rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1',
            TONE[stage]
          )}
        >
          {t(stage)}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
```

- [ ] **Step 5: Build the connect card**

Create `web/src/components/applications/ConnectGmailCard.tsx`:

```tsx
'use client'
import { Mail } from 'lucide-react'
import { motion } from 'motion/react'
import { useTranslations } from 'next-intl'
import { snap } from '@/lib/motion'
import {
  GMAIL_REDIRECT_PATH, gmailConsentUrl, newOAuthState, rememberOAuthState,
} from '@/lib/gmailOAuth'

export function ConnectGmailCard() {
  const t = useTranslations('applications')

  function connect() {
    // Generated on click, not during render: a value produced on the server
    // and again on the client would differ and break hydration.
    const state = newOAuthState()
    rememberOAuthState(state)
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? ''
    const redirect = window.location.origin + GMAIL_REDIRECT_PATH
    window.location.href = gmailConsentUrl(clientId, redirect, state)
  }

  return (
    <section className="grain flex flex-col items-start gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-10">
      <span className="grid size-11 place-items-center rounded-full bg-primary/8 text-primary ring-1 ring-primary/12">
        <Mail aria-hidden className="size-5" />
      </span>
      <p className="type-body max-w-[65ch] text-muted-foreground">
        {t('connectExplain')}
      </p>
      <motion.button
        type="button"
        onClick={connect}
        whileHover={{ y: -2 }}
        whileTap={{ scale: 0.98, transition: snap }}
        className="type-ui inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-primary-foreground shadow-md shadow-primary/20 hover:bg-primary/90"
      >
        {t('connect')}
      </motion.button>
    </section>
  )
}
```

- [ ] **Step 6: Build the application card**

Create `web/src/components/applications/ApplicationCard.tsx`:

```tsx
'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Disclosure } from '@/components/motion/Disclosure'
import { PressableCard } from '@/components/motion/PressableCard'
import type { ApplicationEventRow, ApplicationRow } from '@/types/db'
import { StageBadge } from './StageBadge'

export function ApplicationCard({ row, loadEvents }: {
  row: ApplicationRow
  loadEvents: (id: string) => Promise<ApplicationEventRow[]>
}) {
  const t = useTranslations('applications')
  const [events, setEvents] = useState<ApplicationEventRow[] | null>(null)
  const [open, setOpen] = useState(false)

  async function toggle() {
    setOpen((was) => !was)
    if (events === null) setEvents(await loadEvents(row.id))
  }

  return (
    <PressableCard
      className="flex flex-col gap-3 rounded-xl bg-card px-4 py-4 shadow-e1 ring-1 ring-foreground/[0.07] hover:shadow-e2"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="type-ui truncate text-foreground">
            {row.company ?? t('unknownCompany')}
          </p>
          {row.title && (
            <p className="type-meta truncate text-muted-foreground">{row.title}</p>
          )}
        </div>
        <StageBadge stage={row.stage} />
      </div>

      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="type-meta self-start text-primary hover:underline"
      >
        {t('why')}
      </button>

      <Disclosure open={open}>
        <div className="flex flex-col gap-2 rounded-lg bg-muted/50 px-3 py-2.5">
          {events === null ? (
            <span className="type-meta text-muted-foreground">…</span>
          ) : events.length === 0 ? (
            <span className="type-meta text-muted-foreground">{t('noEvents')}</span>
          ) : (
            events.map((e) => (
              <div key={e.id} className="flex flex-col gap-0.5">
                <span className="type-meta font-medium text-foreground">{e.subject}</span>
                <span className="type-meta text-muted-foreground">
                  {t('eventFrom')}: {e.from_address}
                  {e.received_at && ` · ${new Date(e.received_at).toLocaleDateString()}`}
                </span>
                {e.evidence && (
                  <span className="type-meta italic text-muted-foreground">
                    “{e.evidence}”
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </Disclosure>
    </PressableCard>
  )
}
```

- [ ] **Step 7: Build the page**

Create `web/src/app/(app)/applications/page.tsx`:

```tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { RefreshCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { createClient } from '@/lib/supabase/client'
import { listApplicationEvents, listApplications } from '@/lib/db'
import { inboxConnect, inboxStatus, inboxSync, type InboxStatus } from '@/lib/api'
import { GMAIL_REDIRECT_PATH, takeOAuthState } from '@/lib/gmailOAuth'
import { flow, snap } from '@/lib/motion'
import { Stagger, StaggerItem } from '@/components/motion/Stagger'
import type { ApplicationRow } from '@/types/db'
import { ApplicationCard } from '@/components/applications/ApplicationCard'
import { ConnectGmailCard } from '@/components/applications/ConnectGmailCard'

const STALE_MS = 15 * 60 * 1000

export default function ApplicationsPage() {
  const t = useTranslations('applications')
  const router = useRouter()
  const params = useSearchParams()
  const [supabase] = useState(createClient)
  const [rows, setRows] = useState<ApplicationRow[] | null>(null)
  const [status, setStatus] = useState<InboxStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const loadRows = useCallback(async () => {
    setRows(await listApplications(supabase))
  }, [supabase])

  const runSync = useCallback(async () => {
    setBusy(true)
    setNotice(null)
    try {
      const report = await inboxSync()
      if (report.partial) setNotice(t('partial'))
      setStatus(await inboxStatus())
      await loadRows()
    } catch {
      setNotice(t('revoked'))
    } finally {
      setBusy(false)
    }
  }, [loadRows, t])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      const code = params.get('gmail_code')
      if (params.get('gmail') === 'denied') setNotice(t('denied'))
      if (code) {
        // Strip the code from the URL before anything else can re-trigger it.
        router.replace('/applications')
        // The state is single-use: read it before deciding anything, so a
        // replayed callback finds nothing waiting either way.
        const expected = takeOAuthState()
        const returned = params.get('gmail_state')
        if (!expected || expected !== returned) {
          // Someone else's code, or a flow this tab never started.
          setNotice(t('denied'))
        } else {
          try {
            await inboxConnect(code, window.location.origin + GMAIL_REDIRECT_PATH)
          } catch {
            setNotice(t('denied'))
          }
        }
      }
      const current = await inboxStatus()
      if (cancelled) return
      setStatus(current)
      await loadRows()
      const last = current.last_synced_at ? Date.parse(current.last_synced_at) : 0
      if (current.connected && current.status === 'active' && Date.now() - last > STALE_MS) {
        await runSync()
      }
    }
    boot()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadEvents = useCallback(
    (id: string) => listApplicationEvents(supabase, id), [supabase]
  )

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-10 px-5 py-16 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="type-title text-ink">{t('title')}</h1>
          {status?.connected && (
            <p className="type-meta mt-2 text-muted-foreground">
              {t('connected')} · {status.email} ·{' '}
              {status.last_synced_at
                ? t('syncedAt', { time: new Date(status.last_synced_at).toLocaleTimeString() })
                : t('neverSynced')}
            </p>
          )}
        </div>

        {status?.connected && (
          <motion.button
            type="button"
            onClick={runSync}
            disabled={busy}
            whileHover={busy ? undefined : { y: -2 }}
            whileTap={busy ? undefined : { scale: 0.98, transition: snap }}
            // The label swaps between two lengths; a floor stops the row jumping.
            className="type-ui inline-flex min-w-[13rem] items-center justify-center gap-2 rounded-lg px-4 py-2 text-foreground ring-1 ring-border hover:bg-accent disabled:opacity-60"
          >
            <RefreshCw aria-hidden className={`size-4 ${busy ? 'animate-spin' : ''}`} />
            {busy ? t('refreshing') : t('refresh')}
          </motion.button>
        )}
      </div>

      {status?.status === 'revoked' && (
        <p className="type-ui rounded-lg bg-destructive/8 px-4 py-3 text-destructive">
          {t('revoked')}
        </p>
      )}
      {notice && (
        <p className="type-ui rounded-lg bg-muted px-4 py-3 text-muted-foreground">{notice}</p>
      )}

      {status && !status.connected && <ConnectGmailCard />}

      {/* The skeleton fades out as the list staggers in, so the swap is a
          dissolve rather than a cut. `mode="wait"` holds the entrance until
          the placeholder has gone. */}
      <AnimatePresence mode="wait" initial={false}>
        {rows === null && (
          <motion.div
            key="skeleton"
            exit={{ opacity: 0 }}
            transition={flow}
            className="flex flex-col gap-3"
            aria-hidden
          >
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-[84px] animate-pulse rounded-xl bg-muted/70" />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {rows === null ? null : rows.length === 0 ? (
        <p className="type-body text-muted-foreground">{t('empty')}</p>
      ) : (
        <Stagger as="ul" className="flex flex-col gap-3">
          {rows.map((row, i) => (
            <StaggerItem as="li" key={row.id} index={i}>
              <ApplicationCard row={row} loadEvents={loadEvents} />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </main>
  )
}
```

Note: the `li` comes from `StaggerItem as="li"` in the page, and `ApplicationCard`'s `PressableCard` stays a `div` inside it. One `li` per row — a nested `li` is invalid HTML and would break the list-semantics assertion in Task 3.

- [ ] **Step 8: Add the nav entry and protect the route**

In `web/src/components/AppSidebar.tsx`, add `Inbox` to the `lucide-react` import and add this entry to `ITEMS` after the `optimize` entry:

```tsx
  { href: '/applications', key: 'applications', icon: Inbox, also: [] },
```

In `web/src/lib/protected.ts`, extend the prefix list:

```ts
const PROTECTED_PREFIXES = ['/dashboard', '/cv', '/score', '/ats', '/applications']
```

Then run `npm test -- src/components/__tests__/AppSidebar.test.tsx`. If it asserts
on the number of nav items, that assertion now needs the new count — this is the
one place in the whole plan where editing an existing test is correct, because the
nav genuinely gained an item. If it fails for any other reason, stop and report.

- [ ] **Step 9: Run the page tests**

Run: `npm test -- src/app/\(app\)/applications`
Expected: PASS (11 tests).

- [ ] **Step 10: Run everything**

Run: `npm test && npx tsc --noEmit && npm run lint`
Expected: PASS across the board, including the pre-existing sidebar and dashboard tests.

- [ ] **Step 11: Document the web env var**

In `web/README.md`, add to the env section:

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID=...   # same OAuth client as the API's GOOGLE_CLIENT_ID
```

- [ ] **Step 12: Commit**

```bash
git add web/src/app/\(app\)/applications web/src/components/applications \
        web/src/components/AppSidebar.tsx web/src/lib/protected.ts \
        web/src/messages web/README.md
git commit -m "feat(web): applications page with stages and the email behind each one"
```

---

## A note on Tasks 5–8

Tasks 1–4 create files, so they carry complete source. Tasks 5–8 edit files that
already exist, and their steps give a substitution table rather than a full
rewrite. That is deliberate: writing "the new `score/page.tsx`" in full would mean
inventing the ~80% of each file this refresh does not touch, and an implementer
following invented code would silently revert real work.

The rule for those tasks: **make only the listed substitutions.** If a file
contains something the table does not cover, leave it. If a substitution cannot
be applied because the file does not look as described, stop and report it —
the plan is wrong, not the file.

---

### Task 5: Sweep the dashboard

**Files:**
- Modify: `web/src/app/(app)/dashboard/page.tsx`
- Modify: `web/src/components/CvCard.tsx`

**Interfaces:**
- Consumes: type roles (Task 2), `Stagger`/`StaggerItem`/`PressableCard` (Task 3).
- Produces: nothing new.

- [ ] **Step 1: Confirm the current tests pass before touching anything**

Run: `npm test -- src/app/\(app\)/dashboard src/components`
Expected: PASS. This is the baseline the sweep must not move.

- [ ] **Step 2: Apply the type roles to the dashboard**

In `web/src/app/(app)/dashboard/page.tsx`:
- The `h1`: replace `className="font-display text-3xl font-semibold tracking-tight text-ink"` with `className="type-title text-ink"`.
- The count line: replace `className="mt-1 font-mono text-xs tracking-wide text-muted-foreground"` with `className="type-meta mt-2 text-muted-foreground"`.
- The upload label: replace the leading `text-sm font-medium` in its class list with `type-ui`.
- The error paragraph: replace `text-sm` with `type-ui`.
- The empty-state paragraph: replace `text-[15px] leading-relaxed` with `type-body`.
- The `main` element: change `gap-8` to `gap-10` and `py-12` to `py-16`.

- [ ] **Step 3: Give the CV list its entrance**

In the same file, replace the rendered list container:

```tsx
        <Stagger className="flex flex-col gap-3">
          {cvs.map((cv, i) => (
            <StaggerItem key={cv.id} index={i}>
              <CvCard cv={cv} onDelete={() => onDelete(cv)} />
            </StaggerItem>
          ))}
        </Stagger>
```

and add the import:

```tsx
import { Stagger, StaggerItem } from '@/components/motion/Stagger'
```

- [ ] **Step 4: Give the CV card its depth and press**

In `web/src/components/CvCard.tsx`, wrap the card's outermost element in `PressableCard`, move its class list onto it, and add `shadow-e1 ring-1 ring-foreground/[0.07] hover:shadow-e2` to that class list. Remove any `transition-all` you find — the spring replaces it. Add:

```tsx
import { PressableCard } from '@/components/motion/PressableCard'
```

- [ ] **Step 5: Run the tests**

Run: `npm test && npx tsc --noEmit`
Expected: PASS. If a dashboard or CvCard test fails, the sweep changed behavior — revert that change rather than editing the test.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/\(app\)/dashboard web/src/components/CvCard.tsx
git commit -m "refresh(web): dashboard adopts the type roles and the list entrance"
```

---

### Task 6: Sweep the app shell

**Files:**
- Modify: `web/src/app/(app)/layout.tsx`
- Modify: `web/src/components/AppSidebar.tsx`
- Modify: `web/src/components/NavBar.tsx`

**Interfaces:**
- Consumes: `flow` from `@/lib/motion`, `MotionProvider` (already mounted in Task 1).
- Produces: nothing new.

- [ ] **Step 1: Add the route transition**

In `web/src/app/(app)/layout.tsx`, wrap the page slot (the `{children}` inside the provider) in a keyed motion element so a route change rises and fades rather than cutting:

```tsx
'use client'
import { usePathname } from 'next/navigation'
import { motion } from 'motion/react'
import { flow } from '@/lib/motion'
```

```tsx
  const pathname = usePathname()
```

```tsx
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={flow}
        className="min-w-0 flex-1"
      >
        {children}
      </motion.div>
```

Deliberately not a full-screen overlay: in a shell with a persistent sidebar an overlay reads as latency and fights scroll restoration.

If the layout is currently a server component, adding `'use client'` is the change that makes `usePathname` legal — check `node_modules/next/dist/docs/01-app/` before assuming any other approach.

- [ ] **Step 2: Give the sidebar its active indicator motion**

In `web/src/components/AppSidebar.tsx`, replace `transition-colors` on the `Link` with nothing, and render a shared active pill behind the label:

```tsx
            {active && (
              <motion.span
                layoutId="sidebar-active"
                transition={flow}
                className="absolute inset-0 -z-10 rounded-lg bg-primary/8"
              />
            )}
```

Add `relative` to the `Link`'s class list, drop `bg-primary/8` from the active branch (the pill now draws it), and add the imports:

```tsx
import { motion } from 'motion/react'
import { flow } from '@/lib/motion'
```

`layoutId` makes the indicator travel between items instead of blinking out and in. This is the one place a layout animation earns its cost.

- [ ] **Step 3: Apply the type roles to the shell**

In `AppSidebar.tsx` replace `text-sm font-medium` with `type-ui` in the `Link` class list. In `NavBar.tsx`, replace any `text-sm`/`text-xs` on navigation labels with `type-ui`/`type-meta` respectively. Change nothing structural.

- [ ] **Step 4: Run the tests**

Run: `npm test && npx tsc --noEmit`
Expected: PASS, including `src/components/__tests__/AppSidebar.test.tsx`.

If `layoutId` triggers `ResizeObserver is not defined` under jsdom, add the polyfill shown in Task 3 Step 6.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/\(app\)/layout.tsx web/src/components/AppSidebar.tsx web/src/components/NavBar.tsx
git commit -m "refresh(web): route transition and a travelling sidebar indicator"
```

---

### Task 7: Sweep the remaining app pages

**Files:**
- Modify: `web/src/app/(app)/score/page.tsx`
- Modify: `web/src/app/(app)/ats/page.tsx`
- Modify: `web/src/app/(app)/optimize/page.tsx`
- Modify: `web/src/app/(app)/cv/[id]/page.tsx`
- Modify: `web/src/app/(app)/cv/[id]/score/page.tsx`
- Modify: `web/src/components/ProgressBar.tsx`, `web/src/components/StarRating.tsx`

**Interfaces:**
- Consumes: type roles, `Stagger`, `PressableCard`, `flow`.
- Produces: nothing new.

- [ ] **Step 1: Establish the baseline**

Run: `npm test`
Expected: PASS. Record the number of passing tests; it must not change by the end of this task.

- [ ] **Step 2: Apply the roles page by page**

For each of the five pages, in this order — `score`, `ats`, `optimize`, `cv/[id]`, `cv/[id]/score` — make exactly these substitutions and nothing else:

| Found | Replace with |
|---|---|
| `font-display text-3xl font-semibold tracking-tight` | `type-title` |
| `font-mono text-xs tracking-wide` | `type-meta` |
| `text-sm font-medium` on a control | `type-ui` |
| `text-sm` on a paragraph | `type-ui` |
| `text-[15px] leading-relaxed` | `type-body` |
| `gap-8` on the page `main` | `gap-10` |
| `py-12` on the page `main` | `py-16` |
| `transition-all` | remove it |
| a card's `ring-1 ring-foreground/10` | `shadow-e1 ring-1 ring-foreground/[0.07] hover:shadow-e2` |

Run `npm test` after each page. A failure means that page's test asserted on something the substitution changed — revert and report it rather than editing the test.

- [ ] **Step 3: Animate the progress bar's fill**

In `web/src/components/ProgressBar.tsx`, replace the element whose width expresses the value with:

```tsx
      <motion.div
        className="h-full rounded-full bg-primary"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: value / 100 }}
        transition={settle}
        style={{ originX: 0 }}
      />
```

`scaleX` rather than `width`: a transform does not force layout, and the reduced-motion policy can switch it off.

Add:

```tsx
import { motion } from 'motion/react'
import { settle } from '@/lib/motion'
```

- [ ] **Step 4: Run everything**

Run: `npm test && npx tsc --noEmit && npm run lint`
Expected: PASS, with the same test count recorded in Step 1 plus nothing.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/\(app\) web/src/components/ProgressBar.tsx web/src/components/StarRating.tsx
git commit -m "refresh(web): remaining app pages adopt the type roles and depth scale"
```

---

### Task 8: Sweep the public pages

**Files:**
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/app/login/page.tsx`
- Modify: `web/src/app/register/page.tsx`
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Consumes: type roles, `MotionProvider`, `flow`.
- Produces: nothing new.

- [ ] **Step 1: Mount the provider for the public tree**

`MotionProvider` is currently mounted in `(app)/layout.tsx` only, so the landing, login and register pages have no reduced-motion policy. Move the mount up: wrap the body's children in `web/src/app/layout.tsx` with `<MotionProvider>` and remove the wrapper from `(app)/layout.tsx`.

If `app/layout.tsx` is a server component, do not add `'use client'` to it — `MotionProvider` already carries the directive, and a client provider can wrap server children. Read `node_modules/next/dist/docs/01-app/` if this behaves unexpectedly.

- [ ] **Step 2: Give the landing its display role**

In `web/src/app/page.tsx`, the hero headline takes `type-display`; the sub-headline takes `type-body`; any eyebrow or stat line takes `type-meta`. Section paddings move onto the tier list (`py-16` for major sections). Change no copy and no structure.

- [ ] **Step 3: Give the auth pages their roles**

In `login/page.tsx` and `register/page.tsx`: the heading takes `type-title`, labels take `type-ui`, helper and error text take `type-meta`, and the submit button loses `transition-all`. Wrap the form card in `PressableCard` only if it is already interactive — a form card is not; leave it as a plain element with `shadow-e1 ring-1 ring-foreground/[0.07]`.

- [ ] **Step 4: Run everything**

Run: `npm test && npx tsc --noEmit && npm run lint`
Expected: PASS, including `src/app/__tests__/page.test.tsx`, `login`, and `register` tests.

- [ ] **Step 5: Verify reduced motion by hand**

This cannot be asserted in jsdom, so verify it in a real browser: start the app, enable the OS "Reduce motion" setting, reload `/applications`, and confirm the list still appears (opacity only) with no rise, and the disclosure opens without the height animation.

Run: `npm run dev`

Report what you observed. If the animations still run, `reducedMotion="user"` is not reaching those components — find out why rather than patching the symptom.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/page.tsx web/src/app/login web/src/app/register \
        web/src/app/layout.tsx web/src/app/\(app\)/layout.tsx
git commit -m "refresh(web): landing and auth pages adopt the type roles"
```

---

## Manual verification (after Task 8)

The suite proves the logic; only a browser proves the feel.

1. `npm run dev`, then walk `/`, `/login`, `/dashboard`, `/applications`, `/score`, `/ats`, `/optimize`.
2. On each: headings are Spectral at the new size, metadata lines are mono with tabular figures, cards lift on hover and compress on press, lists arrive staggered rather than all at once.
3. On `/applications`: click **Neden?** and confirm the panel grows rather than snapping, and that its text is selectable during the animation.
4. Move between sidebar items and confirm the active pill travels rather than blinking.
5. Toggle dark mode on every page and confirm the depth scale still reads as depth — shadows on a dark ground must be darker, not fainter.
6. Enable OS reduced motion and repeat steps 2–4: everything still works, nothing translates.
7. At 375px width, confirm no horizontal scroll and no clipped headline.

---

## What already exists

| Already in the codebase | Does the plan reuse it? |
|---|---|
| `.font-display` (globals.css:196) | **No — it duplicated it.** Fixed in Task 2: the role replaces it, 13 call sites migrate. |
| Tailwind spacing 2/3/4/6/10/16 | Yes. The tier list maps onto them exactly, so no new spacing tokens. |
| `tw-animate-css` (`animate-pulse`, `animate-spin`) | Yes, kept for the skeleton and the sync spinner. Motion does not replace them. |
| `MotionConfig reducedMotion="user"` | Yes — the framework's built-in, not a hand-rolled `useReducedMotion` in every component. |
| React `<ViewTransition>` (Next 16, experimental) | **Deliberately not used.** It animates via browser CSS, which would put a second motion vocabulary next to the spring family. |
| `components/ui/` (shadcn card, button) | Untouched. The depth scale applies to their consumers, not to the primitives. |

## NOT in scope

- **Full route exit transitions.** The App Router "frozen router" pattern fights
  scroll restoration and data freshness for a marginal gain (D3).
- **Component anatomy, IA, navigation, copy, palette, fonts.** If one of these
  turns out to be the real problem, that is a finding to report, not a change to
  make here.
- **`LazyMotion` bundle optimization.** Premature until the bundle cost is
  measured against a real build.
- **`Disclosure` inlining.** It has one consumer today, which by strict YAGNI is
  premature abstraction. Kept because it carries its own contract and tests, and
  `ApplicationCard` is already long. Revisit if it still has one consumer in three
  months.
- **The landing page's structure.** Task 8 gives it type roles only.

## Failure modes

| New codepath | Realistic production failure | Test? | Error handling? | Silent? |
|---|---|---|---|---|
| `MotionProvider` | Policy not applied → motion ships to users who asked for none | Yes — `reducedMotion.test.tsx` asserts `"user"` | N/A | Would be silent — hence the test |
| `Stagger` delay | Long list becomes a 7s queue | Yes — cap asserted in `MotionProvider.test.tsx` | Cap in `motion.ts` | Would be visible but maddening |
| `Disclosure` height | Panel opens to 0 height if content measures late | Partial — open/closed content presence tested, not measurement | None | Visible |
| OAuth `state` check | Attacker's code exchanged onto this account | Yes — two tests in Task 4 | `setNotice(t('denied'))` | No, user sees the notice |
| Route entrance | Fires on back/forward, fighting scroll restore | No | None | Visible jank only |

No critical gaps: every failure mode above has either a test or visible symptoms.
The `Disclosure` measurement case is the weakest and is accepted.

## Worktree parallelization

| Step | Modules touched | Depends on |
|------|----------------|------------|
| T1 motion foundation | `lib/`, `components/motion/`, `app/layout.tsx` | — |
| T2 type roles + depth | `app/globals.css` | — |
| T3 primitives | `components/motion/` | T1 |
| T4 applications page | `app/(app)/applications/`, `components/applications/`, `messages/` | T1, T2, T3 |
| T5 dashboard | `app/(app)/dashboard/`, `components/CvCard` | T2, T3 |
| T6 app shell | `app/(app)/layout.tsx`, `components/AppSidebar`, `NavBar` | T1, T2 |
| T7 remaining app pages | `app/(app)/score|ats|optimize|cv/`, `components/Progress*` | T2, T3 |
| T8 public pages | `app/page.tsx`, `app/login/`, `app/register/` | T1, T2 |

```
Lane A: T1 -> T3 -> T4          (sequential, shared components/motion/)
Lane B: T2                       (independent, CSS only)
Lane C: T5, T6, T7, T8           (parallel with each other, all wait on A+B)

Launch A and B together. Merge. Then C fans out into four lanes.
```

Conflict flag: **T6 and T1 both touch a layout file** (`(app)/layout.tsx` vs
`app/layout.tsx`) — different files after the D3/finding-2 fix, so no conflict.
T4 and T5 both touch `components/`, but disjoint subdirectories.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_found | 6 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

Step 0 scope: accepted in full, split across two branches (T1-T4 here, T5-T8 on
`feat/design-refresh`).

Findings and disposition:
1. Route transition was enter-only — kept enter-only by decision D3, spec wording corrected.
2. `MotionProvider` was mounted in `(app)` then moved — now mounted at the root in Task 1.
3. `.font-display` duplicated the new roles — retired in Task 2, 13 call sites migrate.
4. Stagger was unbounded (7s for 200 rows) — capped at `STAGGER_MAX_ITEMS`, asserted by test.
5. `Disclosure` has one consumer — accepted, recorded in NOT in scope.
6. `AppSidebar` test may assert nav item count — flagged in Task 4 Step 8.

**VERDICT:** ENG CLEARED — ready to implement.

NO UNRESOLVED DECISIONS
