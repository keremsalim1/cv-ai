# UI Refresh: Motion and Typographic Rhythm

**Goal:** Make the product read as expensive without changing what it does. Every
route, every control, every string stays where it is; what changes is the type
system, the spacing rhythm, the depth language, and — mostly — the fact that
things now move like they have mass.

**Non-goals.** No new pages, no moved navigation, no renamed controls, no changed
copy, no new palette, no new fonts. The OXBLOOD identity in `globals.css` is the
identity. A refresh that repaints the brand is a different project.

## Why this, and not a redesign

The design system is already good. `globals.css` carries an oklch OXBLOOD
palette, a Spectral display serif, Geist Sans and Geist Mono, and three earned
utilities — `grain`, `hairline`, `oxblood-wash`. The dashboard uses them
correctly. Nothing here is cheap because the wrong colors were chosen.

It reads cheap for five specific reasons, each verifiable in the source:

1. **The type scale is flat.** A page heading is `text-3xl` (30px) and body copy
   is `text-sm` (14px) — a ratio of 2.14. Editorial work earns its authority from
   a much wider jump. The display serif appears only on `h1`, which makes it an
   ornament rather than a system.
2. **There is no motion identity.** Every state change snaps. The one recurring
   transition is `transition-all`, which animates every animatable property —
   both characterless and a performance smell.
3. **Spacing has no tiers.** Page-level `gap-8`, list `gap-3`, `py-12`. Sections,
   groups, and items are separated by nearly the same amount, so nothing reads as
   grouped.
4. **Three depth languages coexist.** `shadow-md shadow-primary/20` on buttons,
   `ring-1 ring-foreground/10` on cards, `border-dashed` on empty states.
5. **Numerals are proportional.** The mono metadata lines shift horizontally when
   a value updates, which is exactly when the user is looking at them.

## The system

### Type roles

Six roles in `@layer components`, additive — existing utilities keep working, and
a component adopts a role instead of assembling one.

| Role | Family | Size / leading | Where |
|---|---|---|---|
| `.type-display` | Spectral | `clamp(2.5rem, 4vw, 3.5rem)`, `-0.02em`, 600 | landing hero only |
| `.type-title` | Spectral | 2.25rem / 1.15, `-0.015em`, 600 | page `h1` |
| `.type-heading` | Geist Sans | 1.375rem / 1.3, 600 | section and card headings |
| `.type-body` | Geist Sans | 1rem / 1.6 | prose |
| `.type-ui` | Geist Sans | 0.875rem / 1.45, 500 | controls and labels |
| `.type-meta` | Geist Mono | 0.75rem, `+0.04em`, `tabular-nums` | metadata lines |

Two consequences worth stating plainly: page headings grow from 30px to 36px, and
prose grows from 14px to 16px. Prose containers gain `max-w-[65ch]`.

### Spacing rhythm

One tier list — **8 / 12 / 16 / 24 / 40 / 64** — and nothing between. Page
vertical padding goes 48 → 64px, section separation 32 → 40px, list item gaps
stay at 12px. The point is not the specific numbers; it is that a reader can feel
which things belong together.

### Depth

One scale replaces the three languages:

| Level | Treatment | Use |
|---|---|---|
| 0 | `ring-1 ring-border/60` | flat surfaces, dividers |
| 1 | level 0 + `0 1px 2px rgb(0 0 0 / 0.04)` | cards at rest |
| 2 | level 0 + `0 8px 24px -12px rgb(0 0 0 / 0.18)`, `y: -2` | card hover / active |
| 3 | heavier, blurred | popovers and modals only |

The primary button keeps its colored shadow. It is the single primary action on
its screen, and that is what the shadow is saying.

### Motion

**One spring, three speeds.** A single family is what makes motion read as
designed rather than assembled.

| Token | Spring | Settles in | Use |
|---|---|---|---|
| `snap` | stiffness 520, damping 32 | ~180ms | press feedback, toggles |
| `flow` | stiffness 380, damping 34 | ~280ms | enter/exit, hover |
| `settle` | stiffness 240, damping 30 | ~420ms | layout and height |

Exact spring parameters and the current API come from the `motion` skill at
implementation time, not from memory. The library is `motion` (imported as
`motion/react`), never `framer-motion`.

Where motion is applied, and what each instance is *for*:

1. **List entrance** — 35ms stagger, opacity and 8px rise, `flow`. Gives a list a
   direction of arrival instead of appearing fully formed.
2. **Disclosure** (`Neden?` on an application card) — `layout` height animation
   with `settle`, content crossfading. This is the one thing CSS cannot do
   honestly, and the reason the library is worth its bytes.
3. **Press** — `scale: 0.98` with `snap` on buttons and interactive cards.
4. **Card hover** — `y: -2` plus depth level 1 → 2, `flow`. Replaces
   `transition-all`; only transform and opacity are animated.
5. **Skeleton → content** — crossfade rather than an abrupt swap.
6. **Stage badge change** — when a sync moves an application, the badge crossfades
   with a slight scale. This is the one animation that carries information: it
   tells the user *what changed* without a toast.
7. **Route change** — the content region rises 6px and fades. Deliberately **not**
   a full-screen overlay transition: in a sidebar app shell an overlay reads as
   latency and fights scroll-position restoration.
8. **Sync button** — the label swaps between "Yenile" and "Gelen kutusu taranıyor…",
   which changes the button's width. `layout` absorbs the change instead of
   letting the row jump.

### Reduced motion

`useReducedMotion()` gates every spring. When the user asks for reduced motion,
transitions become instant and only opacity changes. This is a requirement, not a
refinement — and it is the one behavior in this document that must be tested
rather than eyeballed.

## Structure

New: `web/src/components/motion/` — a provider that reads the reduced-motion
preference once, and three primitives (`Stagger`, `FadeIn`, `PressableCard`) that
every surface composes. Pages do not hand-write spring parameters; if a page needs
a spring the primitives do not offer, the primitive is missing.

Modified: `globals.css` (roles, tiers, depth, spring tokens), `(app)/layout.tsx`
(provider and route transition), and the existing surfaces as they are swept.

Task 13's applications page is built directly in this language rather than built
once and refreshed later.

## Testing

The existing 101 web tests must keep passing untouched. This refresh changes no
text, no roles, and no accessible names, so a test that breaks is evidence that
the refresh went further than it should have — fix the code, not the test.

New tests cover the two things that are behavior rather than appearance:

- Reduced motion is honored (the provider yields instant transitions when the
  media query matches).
- The disclosure still exposes its content to assistive technology while
  animating — `aria-expanded` and the presence of the panel are not deferred to
  the end of an animation.

## Risks

- **`layout` animation needs `ResizeObserver`, which jsdom does not implement.**
  A polyfill in `vitest.setup.ts` is the likely fix. To be confirmed at
  implementation, not assumed here.
- **Bundle size.** `motion` is a new runtime dependency. If the cost shows up,
  `LazyMotion` with a deferred feature bundle is the escape hatch; it is not worth
  pre-optimizing.
- **Sweep breadth.** Seven pages and six components change visually in one pass.
  The mitigation is that the foundation lands first and each surface is a separate
  commit, so a regression is bisectable to one surface.

## Out of scope

Component anatomy, information architecture, navigation, copy, palette, fonts,
and the marketing landing page's structure. If any of those turn out to be the
real problem, that is a finding to report, not a change to make here.
