# Role-Based Form Engine — Design Spec (Faz 3)

**Date:** 2026-07-26
**Status:** Approved (sections 1–3), pending written-spec review
**Depends on:** Faz 2C assisted apply (`/apply/assist/*`, merged to `master` 7c03240)

## Problem

Assisted apply finds its fields by parsing `page.content()` with lxml and addressing
them by absolute XPath. Three structures defeat that, and together they cover most of
the portals we want to support:

1. **Shadow DOM.** Workday renders its controls inside shadow roots. They are absent
   from `page.content()` entirely, and XPath cannot address them even when they are
   known to exist. Measured on a synthetic page carrying both a shadow root and a
   div-combobox:

   ```
   extract_form(page.content())        -> fields found: []
   page.locator("xpath=//input[@id='em']").count()  -> 0
   page.locator("#em").count()                      -> 1      # CSS pierces
   ```

2. **Controls that are not form controls.** Workday, SmartRecruiters and anything
   built on react-select render dropdowns as `div[role=combobox]` with a separate
   `role=listbox` popup. The extractor only looks for `input`/`textarea`/`select`, so
   these are invisible to it.

3. **iframes.** Greenhouse and Lever embed the application form in an iframe. Neither
   `page.content()` nor a CSS selector crosses that boundary.

The LinkedIn Easy Apply work (`fb59d20`, dialog-scoped extraction and id-based
selectors) fixed one instance of this class by hand. Repeating that per portal is the
approach this spec rejects.

## Key finding

The ARIA tree sees everything the HTML string does not, and its elements can be
addressed and filled back. Same synthetic page:

```
- textbox "Email"          # inside the shadow root
- textbox "Phone"          # inside the shadow root
- combobox "Country"       # a div, not a <select>

get_by_role("textbox", name="Phone").fill(...)  ->  +90 555 000 11 22
```

`get_by_role` is what proved the elements are reachable and fillable across the shadow
boundary. It is not what production will use to address them — see Decision 3.

Enterprise ATS vendors (Workday, Greenhouse, Taleo) sell to buyers who require
accessibility conformance, so their custom widgets carry real ARIA roles and
accessible names. That makes role-based extraction **general** rather than
per-platform: the thing every portal must already comply with is the thing we read.

This is a bet, not a certainty — see Risks.

## Goal

Replace field discovery and addressing in **assisted mode** with a role-based engine
that reads the live page rather than an HTML string, so that shadow DOM, custom
widgets and iframes stop being per-platform problems. Per-platform code shrinks to
scope hints and quirk overrides, written only where a captured fixture proves the
generic engine falls short.

## Decisions (locked)

1. **Assisted mode only.** The auto flow (`/apply/prepare`, `/apply/submit`) keeps the
   existing `extract_form(html)` path untouched. This bounds the change and keeps the
   99 existing API tests meaningful. Migrating the auto flow later is a separate call.
2. **The probe collects, Python decides.** Injected JS walks the DOM (descending into
   `element.shadowRoot`), stamps each control with `data-cvai-ref="N"`, and returns raw
   JSON. Accessible-name resolution, field typing and scope filtering stay in Python,
   where they are already written, already tested, and testable without a browser.
3. **Stamped refs, not role+name lookup.** Addressing is `[data-cvai-ref="N"]`.
   `get_by_role(role, name=...)` is ambiguous whenever an accessible name repeats on
   the page ("First name" in both the application form and a references section),
   which raises a strict-mode violation. A stamped ref is unique by construction and,
   being a CSS selector, pierces shadow DOM.
4. **Fills are verified, not assumed.** After filling, the probe runs a second time and
   actual values are compared against intended ones. No LLM call, milliseconds of DOM
   reading. Today a silently-failed click is reported to the user as success.
5. **Adapters are evidence-driven.** A platform module is written only where a captured
   fixture shows the generic engine measurably failing. No speculative per-portal code.
6. **The visual fallback is deferred to its own spec.** The seam ships here; the
   coordinate-clicking agent does not. See Out of scope.

## Architecture

```
session.probe()  ──►  list[RawControl]        browser-side JS, pierces shadow roots
                            │
                            ▼
                  build_form(controls)  ──►  FormSchema      pure, fixture-tested
                            │
                            ▼
                   LLM answers (unchanged)
                            │
                            ▼
              fill_strategies.fill(driver, field, value)
                            │
                            ▼
                  session.probe()  ──►  verify  ──►  list[FieldOutcome]
```

### Components

**`app/services/probe.js`** — the collector. Walks `document`, descends into every
`element.shadowRoot`, and recurses into same-origin frames. For each candidate control
returns: `ref`, `tag`, `type`, `role`, `aria_label`, `labelledby_text`, `label_text`,
`placeholder`, `name`, `required`, `disabled`, `visible`, `options`, `frame_path`,
`landmark` (nearest enclosing landmark role). Stamps `data-cvai-ref` as it goes.

`options` carries the option texts of a native `<select>`, and of a custom widget only
when its listbox is already in the DOM. For a combobox that builds its popup on open —
the common case — it is empty, and the options are discovered by the fill strategy.

It computes no policy. Everything it returns is an observation.

**`app/services/page_probe.py`** — thin Python wrapper. Injects the script, returns
`list[RawControl]` (pydantic). One new driver capability is required:
`driver.evaluate(script, arg)`.

**`app/services/form_build.py`** — pure. `build_form(controls) -> FormSchema`.
Responsibilities, all ported from the current `extract_form`/`_label_text`:

- accessible name: `aria-labelledby` text → `aria-label` → `<label for>` → enclosing
  `<label>`/`<fieldset><legend>` → `placeholder` → `name`
- field typing, extended with `combobox`, `listbox`, `date`
- scope: drop controls whose nearest landmark is `banner`, `navigation`, `search` or
  `contentinfo`; drop password fields; then prefer, in order, an open
  `dialog`/`aria-modal` region, a `<form>`, `role=main`
- radio grouping by `name`, as today

**`app/services/platforms/`** — registry keyed by hostname. A platform supplies an
optional scope root and optional quirk overrides. Empty at the start of
implementation; entries are added only against a captured fixture that demonstrates
the need.

**`app/services/fill_strategies.py`** — `_fill_form`'s if/elif chain, extracted and
extended:

| type | strategy |
|---|---|
| text, textarea | `driver.fill` |
| select | `driver.select_by_label` |
| checkbox | `driver.set_checked` |
| radio | click the matching option ref |
| file | `driver.set_files` |
| **combobox / listbox** | click to open → re-probe for visible `role=option` → click the option whose text matches |
| **typeahead** (`aria-autocomplete`) | type the value → pick the first matching option |
| date | typed as text; the LLM is given the placeholder as a format hint |

The combobox strategy needs the option popup, which these portals render at the
document root rather than inside the combobox. It is found by re-running the collector
with a role filter, which is another `evaluate` call — no further driver capability.

### Schema changes

`FormField.selector` changes content, not shape: `[data-cvai-ref="7"]` instead of an
absolute XPath. `web/src/types/api.ts` is unaffected.

Added: `FormField.frame_path: list[int] = []`.

New: `FieldOutcome{field_id, label, value, status, reason}` where status is
`filled | skipped | failed`.

`assist_fill` returns `filled` (as today) plus `unfilled`, so the UI can tell the user
which fields they must complete by hand. With custom widgets a partial fill is normal,
not exceptional, and silence about it is what produced the "it said it worked" reports.

## Error handling

- A field that cannot be filled is recorded as `failed` with a reason and the loop
  continues; one bad widget never aborts the rest. (Current behaviour, now surfaced
  instead of only logged.)
- Verification mismatch (the control does not hold the intended value afterwards) is
  `failed`, not `filled`.
- Zero fields returns `status: "no_form"` with a `reason`: `login_wall`, `captcha`,
  `no_controls`, or `unsupported`. This is the seam the visual fallback will attach to,
  and in the meantime it tells us which reason actually dominates in the wild.
- Cross-origin frames cannot be probed. They are reported as `unsupported` rather than
  silently yielding an empty form.

## Testing

- **`tools/capture_page.py <url> [--platform NAME]`** — opens a headed browser, waits
  for the operator to log in and navigate to the real form, then writes
  `tests/fixtures/platforms/<name>/<slug>.{html,inventory.json,png}`.
- **Pure tests** run `build_form()` against saved `inventory.json` files: no browser,
  fast, in CI. This is the same discipline that made the LinkedIn dialog fix stick.
- **Strategy tests** drive `fill_strategies` against a fake driver, asserting the click
  sequence for combobox and typeahead.
- **Live probes** (`probe_*.py`, manual, not CI) confirm end-to-end behaviour against
  real postings.
- The existing 99 API tests stay green: the auto flow is untouched.

Per-platform acceptance is measured, not asserted: for each captured fixture, the
number of fields the engine discovers and the number it verifies as filled.

## Risks

1. **The ARIA-quality bet is unverified on real portals.** It is confirmed only on a
   synthetic page. If a real Workday snapshot exposes poor roles or missing accessible
   names, per-platform work grows back toward the adapter-heavy approach. The capture
   script exists to settle this early — it is the first thing implementation should do.
2. **Bot detection is an independent wall.** Indeed and LinkedIn may block automated
   sessions regardless of how well we read the page. Extraction quality cannot fix it.
3. **Kariyer.net is the weakest candidate.** Turkish job boards are less likely to have
   been through an accessibility audit than US enterprise ATS products, so the generic
   engine may underperform there specifically.
4. **Stamped refs die on re-render**, exactly as ids did. The probe → fill → verify
   cycle must stay inside one request; refs are never persisted across calls.

## Out of scope

- The **visual/coordinate fallback agent**. The `no_form` + `reason` seam ships here;
  the agent gets its own spec once we know from real reasons which sites need it. The
  approved UX (automatic, with a "this site is not recognized, this may take longer"
  warning) is preserved for that spec.
- Migrating `/apply/prepare` and `/apply/submit` to the role engine.
- Multi-step wizard navigation and auto-submit: assisted mode has the user drive both.
- Cross-origin frame support.
