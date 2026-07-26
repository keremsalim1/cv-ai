# Assisted Apply Mode — Design Spec (Faz 2C)

**Date:** 2026-07-24
**Status:** Approved (sections 1–4), pending written-spec review
**Depends on:** Faz 2A apply-backend, Faz 2B apply-frontend (`/optimize` page)

## Problem

The current apply automation is single-page: `/apply/prepare` navigates to a URL,
analyzes **that one page**, and `/apply/submit` opens a **fresh** browser and fills
the form it finds. This works for embedded single-page forms (Greenhouse, Lever) but
fails for enterprise multi-step portals (Siemens/Avature, Workday, SuccessFactors,
Taleo), where the real application questions live behind a wizard (choose method →
profile → global questions → job-specific questions). The tool never reaches those
pages, so it cannot see or answer the actual required fields. `prepare` and `submit`
also use **separate** browser sessions, so any navigation/login state is lost between
them.

Concrete report: applying to a Siemens link only optimized the CV and produced a
cover letter (which the posting did not even ask for); none of the actual application
fields were filled.

## Goal

Add an **assisted apply mode**: a single, persistent, visible (headed) browser session
that the user drives to the real application form (through login/method-choice/wizard
steps), after which the tool fills the **current page's actual fields** with
AI-generated answers grounded in the optimized CV. The user reviews and submits in the
real browser. Works across arbitrary multi-step portals without per-site code, because
the human does the navigation and the AI does the field answering.

## Decisions (locked)

1. **Control model:** fill-on-button, user submits. The tool never auto-submits in
   assisted mode. The user clicks "Formu doldur" (Fill form) in the web UI; the tool
   fills the current page in the live browser; the user reviews and submits in the
   real browser window themselves.
2. **Per-step AI answering:** each "Formu doldur" reads the current page, and the LLM
   answers the **real** visible fields (motivation, availability, job-specific
   questions, etc.) from the optimized CV. Identity fields come from the CV. Charged
   **1 AI credit per fill**. Repeatable across wizard steps.
3. **Smart fallback integration:** the existing single-page auto flow is unchanged for
   `ready` pages (a fillable form found on load → review → auto-submit). Assisted mode
   is offered in the fallback states (`captcha` / `form_not_found` / `login_required`),
   alongside the existing "just deliver" option.

## Architecture & Flow

```
Paste link → Prepare (headless)
   ├─ ready (single-page form)  → Review → Auto-submit           [EXISTING, unchanged]
   └─ captcha / form_not_found / login (portal)  → Approve screen:
         [ Asistanlı başvuru ▶ ]  (primary)   |   [ Sadece bana teslim et ] (secondary)
                    │
                    ▼  assistStart(url)
   ┌───────────────────────────────────────────────────────────────┐
   │ LIVE BROWSER SESSION (persistent profile → logins persist)     │
   │  Web UI: "Navigate to the application form in the open window"  │
   │  [ Formu doldur ]  ← per wizard step (1 credit each)           │
   │      → read current page → extract_form → LLM answers the REAL │
   │        fields → fill in the live browser → return screenshot   │
   │  User reviews + SUBMITS manually in the real browser           │
   │  [ Bitir ] → close session → record to application history     │
   └───────────────────────────────────────────────────────────────┘
```

### Persistent headed session across HTTP requests

The core technical challenge: one browser must stay open across multiple requests
(start → fill → fill → close). Sync Playwright objects are not thread-safe and must be
used from the thread that created them; FastAPI sync endpoints run in an anyio
threadpool with no thread affinity. **Solution:** each session runs on its own
dedicated worker thread that owns the Playwright objects; requests submit commands to
that thread via a queue and await the result. This gives thread affinity and
serializes browser access. A module-level `SessionManager` singleton (like
`usage_store`) maps `session_id → BrowserSession` and lazily GCs idle sessions.

**Persistent profile benefit:** the same `.browser-profile` dir is used, so once the
user logs into a portal in the assisted browser, the session persists for future runs.

**MVP constraint:** one browser session at a time (persistent-profile single-instance
lock). Acceptable for single-user/local use.

## Backend

### Session layer — new `app/services/session.py`

`BrowserSession` protocol (fake-injectable, like `BrowserDriver`):
```
snapshot() -> str
fill_form(schema, answers, pdf_path) -> None
screenshot() -> bytes
close() -> None
```

`ThreadedBrowserSession` (production): starts a dedicated worker thread that builds a
`PlaywrightDriver` (persistent headed context) and navigates to the URL; each method
posts a command to the worker thread and awaits its result.

`SessionManager` (module-level singleton):
```
start(factory, url, user_id) -> session_id   # open, navigate, register, bind owner
get(session_id, user_id) -> BrowserSession    # 404 if missing, 403 if not owner
close(session_id, user_id) -> None            # close browser, stop thread, remove
_gc()                                          # close sessions idle > SESSION_IDLE_TTL
```
`factory = get_session_factory()` is a FastAPI dependency (like `get_driver_factory`);
tests override it with an inline `FakeSession` (wraps a `FakeDriver`, no thread).
`_gc()` runs lazily on each `start`/`get` (no background thread). A FastAPI shutdown
handler closes any open sessions.

`SESSION_IDLE_TTL = 900` seconds; `last_used` refreshed on each access.

### Endpoints — `routers/apply.py`

| Endpoint | Body | Behavior | Credit |
|---|---|---|---|
| `POST /apply/assist/start` | `{ url }` | Open persistent headed browser, navigate. Returns `{ session_id }`. No LLM. | 0 |
| `POST /apply/assist/fill` | `{ session_id, cv, language }` | Read live page → `extract_form`. If form: LLM answers the real fields, fill in live browser, screenshot. Returns `filled`. Else `no_form`. | 1 |
| `POST /apply/assist/close` | `{ session_id }` | Close browser, remove session. Returns `{ ok: true }`. | 0 |

All endpoints require `get_current_user`; sessions are owner-bound so a user cannot
touch another user's session. The CV was already optimized in `prepare` (credit spent
there); `assist/start` neither re-optimizes nor charges — the credit is only per
`fill`, where the real questions are answered.

Response shapes:
```
assist/fill filled:  { status: "filled", filled: [{label, value}], field_count, screenshot }
assist/fill no_form: { status: "no_form" }
```

### `assist_fill` service — `services/apply.py`

```python
def assist_fill(session, cv, language, llm, user_id) -> dict:
    html = session.snapshot()
    schema = extract_form(html)                 # already skips login forms
    if not schema.fields:
        return {"status": "no_form"}            # user hasn't reached the form
    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)   # 1 credit
    job_text = _job_text(html)
    out = llm.chat_json(MODEL_SMART, ASSIST_SYSTEM.format(language=language),
                        AssistIn(cv=cv, job_text=job_text, form=schema.fields).model_dump_json(),
                        AnswersOut)
    pdf = ats.render_pdf(cv, language)          # for file inputs
    tmp = <write pdf to NamedTemporaryFile>
    try:
        session.fill_form(schema, out.answers, tmp.name)
        shot = base64.b64encode(session.screenshot()).decode()
    finally:
        <unlink tmp>
    return {"status": "filled",
            "filled": [{"label": f.label, "value": _value_for(f, out.answers)} for f in schema.fields],
            "field_count": len(schema.fields), "screenshot": shot}
```

New LLM contract (lean, answer-only — does NOT re-optimize the CV):
- `ASSIST_SYSTEM`: "Answer this application form's fields from the CV. Identity fields
  from the CV; select/radio pick exactly one option verbatim; unknown → empty string.
  Answer in language: {language}."
- `AssistIn { cv: CVData, job_text: str, form: list[FormField] }` (reuses `PrepareIn` shape).
- `AnswersOut { answers: list[FieldAnswer] }`.

Field filling reuses the existing `_fill_form` (per-field try/except resilience; ATS
PDF to file inputs; idempotent checkbox).

## Frontend

### API client — `web/src/lib/api.ts` + `types/api.ts`
```ts
assistStart(url: string): Promise<{ session_id: string }>
assistFill(sessionId: string, cv: CVData, language: string): Promise<AssistFillResult>
assistClose(sessionId: string): Promise<void>

type AssistFillResult =
  | { status: 'filled'; filled: { label: string; value: string }[]; field_count: number; screenshot: string }
  | { status: 'no_form' }
```

### `/optimize` state machine
Existing: `form → preparing → login → approve → submitting → result`. Add step
**`assist`**.

- **Approve screen (delivery-mode, status ≠ ready):** two buttons — primary
  **`Asistanlı başvuru`** → `assistStart(url)` → step `assist`; secondary
  `Sadece bana teslim et` → existing deliver behavior.
- **Login step:** same primary `Asistanlı başvuru` CTA (the user can log in inside the
  live browser).

**Which CV `assistFill` sends:** the optimized CV from the prepare response
(`payload.cv`) when available (delivery-mode: `captcha` / `form_not_found`). In the
`login_required` case prepare returns only `{status}` (no optimization ran), so the
frontend sends the selected CV's raw `parsed_data`. Either way `assistFill` answers the
live form's fields from whatever CV it receives; the optimized copy is preferred when
it exists.

### `assist` step — new `components/apply/AssistScreen.tsx`
- Instructions: navigate to the application form in the open window.
- **[Formu doldur]** → `assistFill`. `filled` → show filled-field summary + screenshot
  (`data:image/png;base64,…`); repeatable, 1 credit each. `no_form` → gentle notice
  ("no form on this page; navigate to the application form and try again"), no credit.
- Review-and-submit note: the user submits in the real browser.
- **[Bitir]** → `assistClose` → `saveApplication({ status: 'delivered', qa: {form, answers} })`
  → step `result`. No DB schema change (reuses `delivered`; submission can't be
  confirmed since the user submits manually).
- `ProgressBar` shown while starting/filling.

### i18n — `optimize` section (en + tr, parity test enforced)
`assist`, `assistIntro`, `assistFill`, `assistFilling`, `assistStarting`,
`assistNoForm`, `assistFilledCount`, `assistReviewNote`, `assistFinish`.

## Testing

**Backend:** `assist/start|fill|close` via `FakeSession`; `no_form` charges 0 credits;
`fill` charges 1; ownership (another user's `session_id` → 403/404); idle GC closes a
stale session. Optional small unit test for the threaded command round-trip (no real
Playwright).

**Frontend:** approve screen shows `Asistanlı başvuru`; `assist` step: fill → shows
screenshot + summary; `no_form` notice; Bitir → `saveApplication` called → result.
`renderWithIntl` is Turkish-only (codebase convention — assert Turkish strings).

**Verification:** web `npm test` + `tsc --noEmit` + `npm run build`; api `pytest`.

## Out of scope (MVP)

- Concurrent sessions (single session at a time).
- Confirming the application was actually submitted (user submits manually).
- Automatic wizard navigation (the user navigates).
- Multi-file form fine-tuning (ATS PDF is set on file inputs as-is).
