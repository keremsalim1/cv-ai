# Assisted Apply Mode (Faz 2C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an assisted apply mode — a single persistent visible browser session the user drives to a real (multi-step) application form, where the tool fills the current page's actual fields with AI answers grounded in the optimized CV, and the user submits manually.

**Architecture:** A per-session dedicated worker thread owns a headed Playwright browser so it survives across `start → fill → fill → close` HTTP requests (sync Playwright is not thread-safe). A module-level `SessionManager` singleton maps `session_id → BrowserSession`. Three new `/apply/assist/*` endpoints open the browser, fill the live page (1 credit per fill), and close it. The `/optimize` page gains an `assist` step offered from the delivery-mode/ login fallback, keeping the existing single-page auto flow unchanged.

**Tech Stack:** FastAPI + pytest, sync Playwright (persistent headed context), Next.js (App Router) client components, next-intl, Tailwind, Vitest + Testing Library.

## Global Constraints

- Working dir: `C:\Users\ASUS\Desktop\cv-ai` (capital **D**). API commands run in `api/` with `.venv\Scripts\python`; web commands run in `web/`.
- **Next.js is non-standard:** `web/AGENTS.md` requires reading the relevant guide in `web/node_modules/next/dist/docs/` before writing Next.js code. Any component using `useSearchParams` MUST be wrapped in `<Suspense>` (see `/optimize` and `/ats` pages).
- `renderWithIntl` (`web/src/test/utils.tsx`) renders with `locale="tr"` and the Turkish messages ONLY. All web test assertions on visible text MUST use the Turkish strings.
- Every new i18n key MUST be added to BOTH `web/src/messages/en.json` and `tr.json` (the parity test enforces this).
- Apply-flow statuses are fields inside 200-responses, NOT `ApiError` codes. Handle them as UI state.
- TDD: write the failing test first, watch it fail, implement, watch it pass, commit after each task.
- One AI credit is charged per `assist/fill` via `enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)`, called only after a fillable form is confirmed (so `no_form` costs nothing).

---

### Task 1: Backend — browser session layer (`session.py`)

**Files:**
- Create: `api/app/services/session.py`
- Create: `api/tests/fake_session.py`
- Create: `api/tests/test_session.py`

**Interfaces:**
- Consumes: `BrowserDriver` protocol and `get_driver_factory` from `app.services.browser`; `_fill_form` from `app.services.apply` (lazy import to avoid a cycle); `FakeDriver` from `tests.fake_browser`.
- Produces (used by Task 2):
  - `BrowserSession` protocol: `snapshot() -> str`, `fill_form(schema, answers, pdf_path) -> None`, `screenshot() -> bytes`, `close() -> None`.
  - `ThreadedBrowserSession(driver_factory: Callable[[bool], BrowserDriver], url: str)`.
  - `session_manager` singleton with `start(factory, url, user_id) -> str`, `get(session_id, user_id) -> BrowserSession`, `close(session_id, user_id) -> None`, `close_all() -> None`.
  - `get_session_factory()` dependency returning `Callable[[str], BrowserSession]`.
  - `FakeSession(driver)` test double (in `tests/fake_session.py`).

- [x] **Step 1: Write the failing session tests**

Create `api/tests/test_session.py`:

```python
import pytest
from fastapi import HTTPException

from app.services.session import ThreadedBrowserSession, SessionManager
from tests.fake_browser import FakeDriver


def _factory(pages):
    return lambda headed: FakeDriver(list(pages))


def test_threaded_session_round_trips_on_its_own_thread():
    driver = FakeDriver(["<html><body><h1>Hi</h1></body></html>"])
    session = ThreadedBrowserSession(lambda headed: driver, "https://x.com/1")
    try:
        assert "Hi" in session.snapshot()
        assert session.screenshot() == b"\x89PNG-fake"
        assert driver.gotos == ["https://x.com/1"]
    finally:
        session.close()
    assert driver.closed is True


def test_manager_start_get_close_with_ownership():
    mgr = SessionManager()
    fake = FakeDriver(["<html><body>ok</body></html>"])
    session = _FakeSession(fake)
    sid = mgr.start(lambda url: session, "https://x.com", "user-1")
    assert mgr.get(sid, "user-1") is session
    with pytest.raises(HTTPException) as exc:
        mgr.get(sid, "user-2")
    assert exc.value.status_code == 403
    mgr.close(sid, "user-1")
    with pytest.raises(HTTPException) as exc2:
        mgr.get(sid, "user-1")
    assert exc2.value.status_code == 404


def test_manager_gc_closes_idle_sessions():
    mgr = SessionManager()
    session = _FakeSession(FakeDriver(["<html>x</html>"]))
    sid = mgr.start(lambda url: session, "https://x.com", "user-1")
    # force the entry to look old, then trigger lazy GC via another start
    mgr._sessions[sid].last_used -= 10_000
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>y</html>"])), "https://y.com", "user-1")
    assert session.closed is True


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver
        self.closed = False

    def snapshot(self):
        return self._driver.content()

    def fill_form(self, schema, answers, pdf_path):
        pass

    def screenshot(self):
        return self._driver.screenshot()

    def close(self):
        self.closed = True
```

- [x] **Step 2: Run the tests to verify they fail**

Run (in `api/`): `.venv\Scripts\python -m pytest tests/test_session.py -q`
Expected: FAIL — `app.services.session` does not exist (ImportError).

- [x] **Step 3: Implement `session.py`**

Create `api/app/services/session.py`:

```python
"""Persistent headed browser sessions for assisted apply. Each session owns a
BrowserDriver on a dedicated thread, because sync Playwright objects are not
thread-safe and FastAPI's threadpool has no thread affinity."""
import queue
import threading
import time
import uuid
from typing import Callable, Protocol

from fastapi import HTTPException

from app.services.browser import BrowserDriver, get_driver_factory

SESSION_IDLE_TTL = 900  # seconds a session may sit idle before it is GC'd


class BrowserSession(Protocol):
    def snapshot(self) -> str: ...
    def fill_form(self, schema, answers, pdf_path: str) -> None: ...
    def screenshot(self) -> bytes: ...
    def close(self) -> None: ...


class ThreadedBrowserSession:
    """Owns a BrowserDriver on a dedicated thread; every command runs there."""

    def __init__(self, driver_factory: Callable[[bool], BrowserDriver], url: str):
        self._in: "queue.Queue" = queue.Queue()
        self._ready: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, args=(driver_factory, url), daemon=True)
        self._thread.start()
        err = self._ready.get()      # block until the browser is up (or failed)
        if err is not None:
            raise err

    def _run(self, driver_factory, url):
        try:
            driver = driver_factory(True)   # headed
            driver.goto(url)
        except Exception as exc:            # startup failure -> surface to caller
            self._ready.put(exc)
            return
        self._ready.put(None)
        while True:
            fn, out = self._in.get()
            if fn is None:                  # close sentinel
                try:
                    driver.close()
                finally:
                    out.put((None, None))
                return
            try:
                out.put((fn(driver), None))
            except Exception as exc:        # relay to the calling thread
                out.put((None, exc))

    def _call(self, fn):
        out: "queue.Queue" = queue.Queue()
        self._in.put((fn, out))
        result, err = out.get()
        if err is not None:
            raise err
        return result

    def snapshot(self) -> str:
        return self._call(lambda d: d.content())

    def fill_form(self, schema, answers, pdf_path: str) -> None:
        from app.services.apply import _fill_form   # lazy: avoid import cycle
        self._call(lambda d: _fill_form(d, schema, answers, pdf_path))

    def screenshot(self) -> bytes:
        return self._call(lambda d: d.screenshot())

    def close(self) -> None:
        out: "queue.Queue" = queue.Queue()
        self._in.put((None, out))
        out.get()
        self._thread.join(timeout=10)


class _Entry:
    def __init__(self, session: BrowserSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.last_used = time.monotonic()


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def start(self, factory: Callable[[str], BrowserSession], url: str, user_id: str) -> str:
        self._gc()
        session = factory(url)
        sid = uuid.uuid4().hex
        with self._lock:
            self._sessions[sid] = _Entry(session, user_id)
        return sid

    def get(self, session_id: str, user_id: str) -> BrowserSession:
        self._gc()
        with self._lock:
            entry = self._sessions.get(session_id)
        if entry is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND"})
        if entry.user_id != user_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
        entry.last_used = time.monotonic()
        return entry.session

    def close(self, session_id: str, user_id: str) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            if entry.user_id != user_id:
                raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
            del self._sessions[session_id]
        entry.session.close()

    def _gc(self) -> None:
        now = time.monotonic()
        stale: list[_Entry] = []
        with self._lock:
            for sid in [s for s, e in self._sessions.items()
                        if now - e.last_used > SESSION_IDLE_TTL]:
                stale.append(self._sessions.pop(sid))
        for entry in stale:
            try:
                entry.session.close()
            except Exception:
                pass

    def close_all(self) -> None:
        with self._lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
        for entry in entries:
            try:
                entry.session.close()
            except Exception:
                pass


session_manager = SessionManager()


def get_session_factory() -> Callable[[str], BrowserSession]:
    driver_factory = get_driver_factory()
    return lambda url: ThreadedBrowserSession(driver_factory, url)
```

Also create `api/tests/fake_session.py` (used by Task 2):

```python
"""Inline BrowserSession double: wraps a FakeDriver, no thread."""
from app.services.apply import _fill_form


class FakeSession:
    def __init__(self, driver):
        self._driver = driver
        self.closed = False

    def snapshot(self) -> str:
        return self._driver.content()

    def fill_form(self, schema, answers, pdf_path: str) -> None:
        _fill_form(self._driver, schema, answers, pdf_path)

    def screenshot(self) -> bytes:
        return self._driver.screenshot()

    def close(self) -> None:
        self.closed = True
        self._driver.close()
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_session.py -q`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add api/app/services/session.py api/tests/fake_session.py api/tests/test_session.py
git commit -m "feat(api): persistent browser session layer for assisted apply"
```

---

### Task 2: Backend — assist_fill service + `/apply/assist/*` endpoints

**Files:**
- Modify: `api/app/services/apply.py` (add `ASSIST_SYSTEM`, `AssistIn`, `AnswersOut`, `assist_fill`)
- Modify: `api/app/routers/apply.py` (add three endpoints)
- Modify: `api/app/main.py` (shutdown handler closing sessions)
- Create: `api/tests/test_apply_assist.py`

**Interfaces:**
- Consumes: `session_manager`, `get_session_factory`, `BrowserSession` from `app.services.session`; existing `extract_form`, `_job_text`, `_fill_form`, `enforce_limit`, `usage_store`, `get_settings`, `MODEL_SMART`, `LLMClient`, `ats.render_pdf`, `CVData`, `FieldAnswer`, `FormField`; `get_current_user`, `get_llm`.
- Produces: `POST /apply/assist/start` → `{session_id}`; `POST /apply/assist/fill` → `{status:"filled", filled:[{label,value}], field_count, screenshot}` | `{status:"no_form"}`; `POST /apply/assist/close` → `{ok:true}`. Consumed by Tasks 3–5.

- [x] **Step 1: Write the failing endpoint tests**

Create `api/tests/test_apply_assist.py`:

```python
import json

import pytest

from app.main import app
from app.services.session import get_session_factory, session_manager
from tests.conftest import SAMPLE_CV_JSON, make_token, override_llm
from tests.fake_browser import FakeDriver
from tests.fake_session import FakeSession

FORM_HTML = (
    "<html><body><h1>Apply</h1>"
    "<form><label>Motivation<textarea name='motivation'></textarea></label>"
    "<label>Email<input type='email' name='email'></label>"
    "<button type='submit'>Send</button></form></body></html>"
)
NO_FORM_HTML = "<html><body><h1>Step 1</h1><p>Choose a method to continue.</p></body></html>"
ASSIST_OUT = json.dumps({"answers": [{"field_id": "motivation", "value": "I love APIs."}]})


@pytest.fixture(autouse=True)
def _clear_sessions():
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def _use_session(driver: FakeDriver):
    session = FakeSession(driver)
    app.dependency_overrides[get_session_factory] = lambda: (lambda url: session)
    return session


def _start(client, auth_headers) -> str:
    r = client.post("/apply/assist/start", headers=auth_headers,
                    json={"url": "https://jobs.siemens.com/x"})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_assist_start_opens_a_session(client, auth_headers):
    _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    assert sid
    assert sid in session_manager._sessions


def test_assist_fill_fills_and_charges_one_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([FORM_HTML]))
    override_llm([ASSIST_OUT])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "filled"
    assert body["field_count"] >= 2
    assert body["screenshot"]
    assert sum(usage_store._counts.values()) == 1


def test_assist_fill_no_form_costs_no_credit(client, auth_headers):
    from app.services.usage import usage_store
    _use_session(FakeDriver([NO_FORM_HTML]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.json()["status"] == "no_form"
    assert sum(usage_store._counts.values()) == 0


def test_assist_fill_rejects_other_users_session(client, auth_headers):
    _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    other = {"Authorization": f"Bearer {make_token('user-2')}"}
    r = client.post("/apply/assist/fill", headers=other,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON), "language": "en"})
    assert r.status_code == 403


def test_assist_close_removes_the_session(client, auth_headers):
    session = _use_session(FakeDriver([FORM_HTML]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/close", headers=auth_headers, json={"session_id": sid})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert session.closed is True
    assert sid not in session_manager._sessions
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_apply_assist.py -q`
Expected: FAIL — the `/apply/assist/*` routes do not exist (404), and `assist_fill` is undefined.

- [x] **Step 3: Add the assist service to `apply.py`**

In `api/app/services/apply.py`, add after the existing `PrepareOut` class (near the top-level model definitions):

```python
ASSIST_SYSTEM = (
    "You fill ONE page of a job application form from a CV. "
    "Input JSON: cv, job_text, form (fields with id/label/type/options). "
    'Respond ONLY with JSON: {{"answers": [{{"field_id": str, "value": str}}]}}. '
    "One answer per field except type=file. Identity fields "
    "(name/email/phone/location) come from the CV. For select/radio pick EXACTLY "
    "one option verbatim from options. If the CV lacks the info, use value \"\" so "
    "the user fills it. NEVER invent facts. Answer in language: {language}."
)


class AssistIn(BaseModel):
    cv: CVData
    job_text: str
    form: list[FormField]


class AnswersOut(BaseModel):
    answers: list[FieldAnswer] = []


def assist_fill(session, cv: CVData, language: str,
                llm: LLMClient, user_id: str) -> dict:
    """Fill the CURRENT live page of an assisted session. Reads whatever the
    user navigated to; if there's a fillable form, answers its real fields."""
    html = session.snapshot()
    schema = extract_form(html)
    if not schema.fields:
        return {"status": "no_form"}
    # Real form present: charge one credit, then answer + fill.
    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
    job_text = _job_text(html)
    user_payload = AssistIn(cv=cv, job_text=job_text,
                            form=schema.fields).model_dump_json()
    out = llm.chat_json(MODEL_SMART, ASSIST_SYSTEM.format(language=language),
                        user_payload, AnswersOut)
    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    try:
        session.fill_form(schema, out.answers, tmp.name)
        shot = base64.b64encode(session.screenshot()).decode()
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    values = {a.field_id: a.value for a in out.answers}
    filled = [{"label": f.label, "value": values.get(f.id, "")}
              for f in schema.fields if f.type != "file"]
    return {"status": "filled", "filled": filled,
            "field_count": len(schema.fields), "screenshot": shot}
```

(No new imports needed: `base64`, `tempfile`, `Path`, `ats`, `extract_form`, `enforce_limit`, `usage_store`, `get_settings`, `MODEL_SMART`, `LLMClient`, `CVData`, `FieldAnswer`, `FormField`, `_job_text` are all already imported in `apply.py`.)

- [x] **Step 4: Add the endpoints to `routers/apply.py`**

In `api/app/routers/apply.py`, add these imports and routes. Update the import from the service and add the session import:

```python
from app.services.apply import assist_fill, prepare_application, submit_application
from app.services.session import get_session_factory, session_manager
```

Then append the routes:

```python
class AssistStartRequest(BaseModel):
    url: str


@router.post("/assist/start")
def assist_start(
    req: AssistStartRequest,
    user_id: str = Depends(get_current_user),
    make_session=Depends(get_session_factory),
):
    sid = session_manager.start(make_session, req.url, user_id)
    return {"session_id": sid}


class AssistFillRequest(BaseModel):
    session_id: str
    cv: CVData
    language: str = "tr"


@router.post("/assist/fill")
def assist_fill_route(
    req: AssistFillRequest,
    user_id: str = Depends(get_current_user),
    llm: LLMClient = Depends(get_llm),
):
    session = session_manager.get(req.session_id, user_id)
    return assist_fill(session, req.cv, req.language, llm, user_id)


class AssistCloseRequest(BaseModel):
    session_id: str


@router.post("/assist/close")
def assist_close(
    req: AssistCloseRequest,
    user_id: str = Depends(get_current_user),
):
    session_manager.close(req.session_id, user_id)
    return {"ok": True}
```

- [x] **Step 5: Close sessions on shutdown via `lifespan` in `main.py`**

In `api/app/main.py`, add a `lifespan` handler and pass it to `FastAPI(...)` (the modern replacement for the deprecated `@app.on_event("shutdown")`). Add the import at the top:

```python
from contextlib import asynccontextmanager
```

Add the lifespan function immediately before the `app = FastAPI(...)` line, and update that line:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.services.session import session_manager
    session_manager.close_all()


app = FastAPI(title="KRESUME.ai API", lifespan=lifespan)
```

(Replace the existing `app = FastAPI(title="KRESUME.ai API")` line.)

- [x] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_apply_assist.py -q`
Expected: PASS (5 tests). Then the full API suite: `.venv\Scripts\python -m pytest -q` — all green.

- [x] **Step 7: Commit**

```bash
git add api/app/services/apply.py api/app/routers/apply.py api/app/main.py api/tests/test_apply_assist.py
git commit -m "feat(api): assisted apply endpoints (start/fill/close) with per-fill credit"
```

---

### Task 3: Web — assist API client + types

**Files:**
- Modify: `web/src/types/api.ts` (append `AssistFillResult`)
- Modify: `web/src/lib/api.ts` (append `assistStart`, `assistFill`, `assistClose`)
- Modify: `web/src/lib/__tests__/api.test.ts` (append tests)

**Interfaces:**
- Consumes: existing `apiUrl`, `authHeaders`, `ensureOk`, `CVData`.
- Produces (used by Tasks 4–5):
  - `AssistFillResult` type.
  - `assistStart(url: string): Promise<{ session_id: string }>`
  - `assistFill(sessionId: string, cv: CVData, language: string): Promise<AssistFillResult>`
  - `assistClose(sessionId: string): Promise<void>`

- [x] **Step 1: Append the type**

Append to `web/src/types/api.ts`:

```ts
export type AssistFillResult =
  | { status: 'filled'; filled: { label: string; value: string }[]; field_count: number; screenshot: string }
  | { status: 'no_form' }
```

- [x] **Step 2: Append the failing api-client tests**

Append to `web/src/lib/__tests__/api.test.ts`:

```ts
it('assistStart posts the url and returns the session id', async () => {
  const { assistStart } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { session_id: 'sess-1' }))
  const out = await assistStart('https://j.com/1')
  expect(out.session_id).toBe('sess-1')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/start')
  expect(JSON.parse(init.body as string)).toEqual({ url: 'https://j.com/1' })
})

it('assistFill posts session+cv+language', async () => {
  const { assistFill } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, {
    status: 'filled', filled: [{ label: 'Email', value: 'a@b.c' }], field_count: 2, screenshot: 'AAA',
  }))
  const out = await assistFill('sess-1', CV, 'en')
  expect(out).toMatchObject({ status: 'filled', field_count: 2 })
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/fill')
  expect(JSON.parse(init.body as string)).toEqual({ session_id: 'sess-1', cv: CV, language: 'en' })
})

it('assistClose posts the session id', async () => {
  const { assistClose } = await import('@/lib/api')
  ;(global.fetch as Mock).mockResolvedValue(jsonResponse(200, { ok: true }))
  await assistClose('sess-1')
  const [url, init] = (global.fetch as Mock).mock.calls[0]
  expect(String(url)).toBe('http://localhost:8000/apply/assist/close')
  expect(JSON.parse(init.body as string)).toEqual({ session_id: 'sess-1' })
})
```

- [x] **Step 3: Run the tests to verify they fail**

Run (in `web/`): `npx vitest run src/lib/__tests__/api.test.ts`
Expected: FAIL — `assistStart`/`assistFill`/`assistClose` are not exported.

- [x] **Step 4: Implement the client functions**

Add `AssistFillResult` to the existing `import type ... from '@/types/api'` line in `web/src/lib/api.ts`, then append:

```ts
export async function assistStart(url: string): Promise<{ session_id: string }> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/assist/start'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
  )
  return res.json()
}

export async function assistFill(
  sessionId: string, cv: CVData, language: string
): Promise<AssistFillResult> {
  const res = await ensureOk(
    await fetch(apiUrl('/apply/assist/fill'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, cv, language }),
    })
  )
  return res.json()
}

export async function assistClose(sessionId: string): Promise<void> {
  await ensureOk(
    await fetch(apiUrl('/apply/assist/close'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    })
  )
}
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `npx vitest run src/lib/__tests__/api.test.ts`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add web/src/types/api.ts web/src/lib/api.ts web/src/lib/__tests__/api.test.ts
git commit -m "feat(web): assist API client (start/fill/close) + AssistFillResult type"
```

---

### Task 4: Web — AssistScreen component + i18n

**Files:**
- Create: `web/src/components/apply/AssistScreen.tsx`
- Create: `web/src/components/apply/__tests__/AssistScreen.test.tsx`
- Modify: `web/src/messages/en.json`, `web/src/messages/tr.json` (add keys to the `optimize` section)

**Interfaces:**
- Consumes: `AssistFillResult` from `@/types/api`; `Button` from `@/components/ui/button`; `ProgressBar` from `@/components/ProgressBar`.
- Produces (used by Task 5): `AssistScreen` with props
  `{ result: AssistFillResult | null; busy: boolean; onFill: () => void; onFinish: () => void }`.

- [x] **Step 1: Add the i18n keys (both languages)**

In `web/src/messages/en.json`, add these keys inside the existing `"optimize"` object (after `"statusFailed"`, adding a comma after `statusFailed`'s value):

```json
"assistCta": "Assisted apply",
"assist": "Assisted apply",
"assistIntro": "A browser window is open. Navigate to the application form there (choose a method, sign in, advance the steps). When the form is on screen, click \"Fill form\".",
"assistStarting": "Opening the browser…",
"assistFill": "Fill form",
"assistFilling": "Reading the page and filling…",
"assistNoForm": "No form found on this page. Go to the application form in the window, then try again.",
"assistFilledCount": "{count} fields filled",
"assistReviewNote": "Review the fields in the real browser and submit there yourself. If there's another step, click \"Fill form\" again.",
"assistFinish": "Finish"
```

In `web/src/messages/tr.json`, add the matching keys inside `"optimize"`:

```json
"assistCta": "Asistanlı başvuru",
"assist": "Asistanlı başvuru",
"assistIntro": "Bir tarayıcı penceresi açık. Başvuru formuna oradan ilerleyin (yöntem seçin, giriş yapın, adımları geçin). Form ekranda göründüğünde \"Formu doldur\"a basın.",
"assistStarting": "Tarayıcı açılıyor…",
"assistFill": "Formu doldur",
"assistFilling": "Sayfa okunuyor ve dolduruluyor…",
"assistNoForm": "Bu sayfada form bulunamadı. Penceredeki başvuru formuna gidip tekrar deneyin.",
"assistFilledCount": "{count} alan dolduruldu",
"assistReviewNote": "Alanları gerçek tarayıcıda gözden geçirip GÖNDER'e kendiniz basın. Sonraki adım varsa yine \"Formu doldur\".",
"assistFinish": "Bitir"
```

- [x] **Step 2: Write the failing AssistScreen test**

Create `web/src/components/apply/__tests__/AssistScreen.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import type { AssistFillResult } from '@/types/api'
import { AssistScreen } from '@/components/apply/AssistScreen'

const FILLED: AssistFillResult = {
  status: 'filled', field_count: 2, screenshot: 'PNGDATA',
  filled: [{ label: 'Motivasyon', value: 'API severim' }],
}

it('fill button triggers onFill', async () => {
  const onFill = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={onFill} onFinish={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Formu doldur' }))
  expect(onFill).toHaveBeenCalled()
})

it('shows the filled summary and screenshot', () => {
  renderWithIntl(<AssistScreen result={FILLED} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/2 alan dolduruldu/)).toBeInTheDocument()
  expect(screen.getByText(/API severim/)).toBeInTheDocument()
  expect((screen.getByRole('img') as HTMLImageElement).src).toContain('PNGDATA')
})

it('shows the no-form notice', () => {
  renderWithIntl(<AssistScreen result={{ status: 'no_form' }} busy={false} onFill={vi.fn()} onFinish={vi.fn()} />)
  expect(screen.getByText(/form bulunamadı/)).toBeInTheDocument()
})

it('finish button triggers onFinish', async () => {
  const onFinish = vi.fn()
  renderWithIntl(<AssistScreen result={null} busy={false} onFill={vi.fn()} onFinish={onFinish} />)
  await userEvent.click(screen.getByRole('button', { name: 'Bitir' }))
  expect(onFinish).toHaveBeenCalled()
})
```

- [x] **Step 3: Run the test to verify it fails**

Run: `npx vitest run "src/components/apply/__tests__/AssistScreen.test.tsx"`
Expected: FAIL — cannot resolve `@/components/apply/AssistScreen`.

- [x] **Step 4: Implement `AssistScreen`**

Create `web/src/components/apply/AssistScreen.tsx`:

```tsx
'use client'
import { useTranslations } from 'next-intl'
import { Wand2, CheckCircle2, Flag } from 'lucide-react'
import type { AssistFillResult } from '@/types/api'
import { Button } from '@/components/ui/button'
import { ProgressBar } from '@/components/ProgressBar'

export function AssistScreen({ result, busy, onFill, onFinish }: {
  result: AssistFillResult | null
  busy: boolean
  onFill: () => void
  onFinish: () => void
}) {
  const t = useTranslations('optimize')
  return (
    <div className="flex flex-col gap-6">
      <p className="rounded-lg bg-muted px-4 py-3 text-sm leading-relaxed text-muted-foreground">
        {t('assistIntro')}
      </p>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onFill} disabled={busy} className="h-11 gap-1.5 text-base">
          <Wand2 aria-hidden className="size-4" />
          {t('assistFill')}
        </Button>
        <Button variant="outline" onClick={onFinish} disabled={busy} className="h-11 gap-1.5 text-base">
          <Flag aria-hidden className="size-4" />
          {t('assistFinish')}
        </Button>
      </div>

      {busy && <ProgressBar label={t('assistFilling')} />}

      {result?.status === 'no_form' && (
        <p className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
          {t('assistNoForm')}
        </p>
      )}

      {result?.status === 'filled' && (
        <section className="flex flex-col gap-3">
          <p className="flex items-center gap-2 text-sm font-medium text-success">
            <CheckCircle2 aria-hidden className="size-4 shrink-0" />
            {t('assistFilledCount', { count: result.field_count })}
          </p>
          {result.filled.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
              {result.filled.map((f, i) => (
                <li key={i}><span className="text-foreground">{f.label}:</span> {f.value}</li>
              ))}
            </ul>
          )}
          <img src={`data:image/png;base64,${result.screenshot}`} alt={t('assistFilledCount', { count: result.field_count })}
            className="w-full rounded-xl border border-border" />
          <p className="text-sm leading-relaxed text-muted-foreground">{t('assistReviewNote')}</p>
        </section>
      )}
    </div>
  )
}
```

- [x] **Step 5: Run the test to verify it passes**

Run: `npx vitest run "src/components/apply/__tests__/AssistScreen.test.tsx"`
Expected: PASS (4 tests).

- [x] **Step 6: Commit**

```bash
git add web/src/components/apply/AssistScreen.tsx web/src/components/apply/__tests__/AssistScreen.test.tsx web/src/messages/en.json web/src/messages/tr.json
git commit -m "feat(web): AssistScreen (fill-form loop + screenshot) and assist i18n"
```

---

### Task 5: Web — `/optimize` page integration + final verification

**Files:**
- Modify: `web/src/components/apply/ApprovalScreen.tsx` (optional `onAssist` prop)
- Modify: `web/src/app/(app)/optimize/page.tsx` (assist step + wiring)
- Modify: `web/src/app/(app)/optimize/__tests__/page.test.tsx` (append test + mock)

**Interfaces:**
- Consumes: `assistStart`, `assistFill`, `assistClose` from `@/lib/api`; `AssistScreen` from `@/components/apply/AssistScreen`; `AssistFillResult` from `@/types/api`; existing `saveApplication`, `atsPdf`, `ApprovalScreen`, `ResultScreen`.
- Produces: the `assist` step on `/optimize`; `ApprovalScreen` gains an optional assisted-apply button.

- [x] **Step 1: Add the optional `onAssist` button to `ApprovalScreen`**

In `web/src/components/apply/ApprovalScreen.tsx`, add `onAssist` to the props type and render it as the primary button in delivery mode. Change the component signature and the button row.

Change the props destructure and type:

```tsx
export function ApprovalScreen({ payload, canSubmit, onSubmit, onDeliver, onAssist }: {
  payload: OptimizedPayload
  canSubmit: boolean
  onSubmit: (answers: FieldAnswer[], coverLetter: string) => void
  onDeliver: (answers: FieldAnswer[], coverLetter: string) => void
  onAssist?: () => void
}) {
```

Add the `Wand2` icon to the existing lucide import line:

```tsx
import { Send, PackageOpen, Wand2 } from 'lucide-react'
```

Replace the button row (`<div className="flex flex-wrap gap-3">…</div>`) with:

```tsx
      <div className="flex flex-wrap gap-3">
        {canSubmit && (
          <Button onClick={() => onSubmit(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
            <Send aria-hidden className="size-4" />
            {t('submit')}
          </Button>
        )}
        {onAssist && (
          <Button onClick={onAssist} className="h-11 gap-1.5 text-base">
            <Wand2 aria-hidden className="size-4" />
            {t('assistCta')}
          </Button>
        )}
        <Button variant="outline" onClick={() => onDeliver(answers(), coverLetter)} className="h-11 gap-1.5 text-base">
          <PackageOpen aria-hidden className="size-4" />
          {t('deliver')}
        </Button>
      </div>
```

- [x] **Step 2: Append the failing page test**

Append to `web/src/app/(app)/optimize/__tests__/page.test.tsx`. First extend the `@/lib/api` mock to include the assist functions — replace the existing `vi.mock('@/lib/api', …)` block with:

```tsx
vi.mock('@/lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...orig, applyPrepare: vi.fn(), applySubmit: vi.fn(), atsPdf: vi.fn(async () => new Blob(['%PDF'])),
    assistStart: vi.fn(), assistFill: vi.fn(), assistClose: vi.fn(),
  }
})
```

Add these imports alongside the existing `import { applyPrepare, applySubmit } from '@/lib/api'` line:

```tsx
import { applyPrepare, applySubmit, assistStart, assistFill, assistClose } from '@/lib/api'
```

Then append the test:

```tsx
it('form_not_found → assisted apply: fills the live form then finishes', async () => {
  ;(applyPrepare as Mock).mockResolvedValue({
    status: 'form_not_found', form: [], cv: CVS[0].parsed_data, changes: [], cover_letter: 'cl', answers: [], job_text: 'jt',
  })
  ;(assistStart as Mock).mockResolvedValue({ session_id: 'sess-1' })
  ;(assistFill as Mock).mockResolvedValue({
    status: 'filled', field_count: 3, screenshot: 'SHOT', filled: [{ label: 'Motivasyon', value: 'X' }],
  })
  ;(assistClose as Mock).mockResolvedValue(undefined)
  renderWithIntl(<OptimizePage />)
  await fillLinkAndPrepare()
  await userEvent.click(await screen.findByRole('button', { name: 'Asistanlı başvuru' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Formu doldur' }))
  expect(assistFill).toHaveBeenCalledWith('sess-1', CVS[0].parsed_data, expect.any(String))
  expect((await screen.findByRole('img') as HTMLImageElement).src).toContain('SHOT')
  await userEvent.click(screen.getByRole('button', { name: 'Bitir' }))
  await waitFor(() => expect(saveApplication).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ status: 'delivered' })))
  expect(assistClose).toHaveBeenCalledWith('sess-1')
})
```

- [x] **Step 3: Run the test to verify it fails**

Run: `npx vitest run "src/app/(app)/optimize/__tests__/page.test.tsx"`
Expected: FAIL — no `Asistanlı başvuru` button / assist step not implemented.

- [x] **Step 4: Wire the assist step into the page**

In `web/src/app/(app)/optimize/page.tsx`:

(a) Add imports:

```tsx
import { ApiError, applyPrepare, applySubmit, assistClose, assistFill, assistStart, atsPdf } from '@/lib/api'
import { AssistScreen } from '@/components/apply/AssistScreen'
import type { AssistFillResult, FieldAnswer, OptimizedPayload, PrepareResult } from '@/types/api'
```

(b) Extend the `Step` type and add state (after the existing `const [error, setError] = useState<string | null>(null)`):

```tsx
type Step = 'form' | 'preparing' | 'login' | 'approve' | 'submitting' | 'assist' | 'result'
```
```tsx
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [assistResult, setAssistResult] = useState<AssistFillResult | null>(null)
  const [assistBusy, setAssistBusy] = useState(false)
```

(c) Add the assist handlers (after the `onDeliver` function):

```tsx
  async function beginAssist() {
    const cv = cvs?.find((c) => c.id === selected)
    if (!cv || !url.trim()) return
    // login-mode has no optimized payload; synthesize one from the selected CV
    if (!payload) {
      setPayload({ status: 'form_not_found', cv: cv.parsed_data, form: [],
        changes: [], cover_letter: '', answers: [], job_text: '' })
    }
    setError(null)
    setAssistResult(null)
    setStep('assist')
    setAssistBusy(true)
    try {
      const { session_id } = await assistStart(url.trim())
      setSessionId(session_id)
    } catch (err) {
      showError(err)
      setStep(payload ? 'approve' : 'login')
    } finally {
      setAssistBusy(false)
    }
  }

  async function doAssistFill() {
    if (!sessionId) return
    const cv = payload?.cv ?? cvs!.find((c) => c.id === selected)!.parsed_data
    setError(null)
    setAssistBusy(true)
    try {
      setAssistResult(await assistFill(sessionId, cv, lang))
    } catch (err) {
      showError(err)
    } finally {
      setAssistBusy(false)
    }
  }

  async function finishAssist() {
    if (sessionId) { try { await assistClose(sessionId) } catch { /* already gone */ } }
    if (payload) await finish('delivered', payload, [], payload.cover_letter ?? '')
  }
```

(d) Pass `onAssist` to `ApprovalScreen` (delivery mode only) — replace the `<ApprovalScreen … />` line:

```tsx
          <ApprovalScreen payload={payload} canSubmit={payload.status === 'ready'}
            onSubmit={onSubmit} onDeliver={onDeliver}
            onAssist={payload.status === 'ready' ? undefined : beginAssist} />
```

(e) Add an assist CTA to the login step — inside the `step === 'login'` block, after the existing login `<Button>`:

```tsx
          <Button variant="outline" onClick={beginAssist} className="h-11 gap-1.5 text-base">
            <LogIn aria-hidden className="size-4" />
            {t('optimize.assistCta')}
          </Button>
```

(f) Render the assist step — add a branch before `step === 'result'`:

```tsx
      ) : step === 'assist' ? (
        <>
          <h1 className="text-xl font-semibold text-foreground">{t('optimize.assist')}</h1>
          {!sessionId ? (
            <ProgressBar label={t('optimize.assistStarting')} />
          ) : (
            <AssistScreen result={assistResult} busy={assistBusy}
              onFill={doAssistFill} onFinish={finishAssist} />
          )}
        </>
```

- [x] **Step 5: Run the test to verify it passes**

Run: `npx vitest run "src/app/(app)/optimize/__tests__/page.test.tsx"`
Expected: PASS (all page tests, including the new assisted-apply test).

- [x] **Step 6: Full verification**

Run (in `web/`):
- `npm test` — all green (includes message parity).
- `npx tsc --noEmit` — no type errors.
- `npm run build` — succeeds, `/optimize` route listed, no Suspense warnings.

Run (in `api/`): `.venv\Scripts\python -m pytest -q` — all green.

- [x] **Step 7: Commit**

```bash
git add "web/src/components/apply/ApprovalScreen.tsx" "web/src/app/(app)/optimize/page.tsx" "web/src/app/(app)/optimize/__tests__/page.test.tsx"
git commit -m "feat(web): assisted apply step on /optimize (live fill loop + finish)"
```

- [x] **Step 8: Whole-branch review**

Reviewed against `master`. Three findings, all fixed before merge:

1. **Shared Chromium profile** — one `browser_profile_dir` for every user meant a
   second user inherited the first one's job-site logins, and two concurrent
   sessions collided on the same directory. Now `browser.profile_dir_for()`
   gives each user their own hashed subdirectory, bound at the DI layer so no
   service below can forget it.
2. **Unbounded browser launches** — `SessionManager.start()` had no cap. Now
   capped by `settings.max_browser_sessions` (503 `TOO_MANY_SESSIONS`, localized
   in both languages) with one live session per user, which is also what keeps a
   per-user profile dir safe to reuse.
3. **Router read `session_manager._sessions`** — replaced with `live_count()`.

---
```
