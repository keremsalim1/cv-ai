# Apply Backend (Faz 2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend for "Optimize & Otomatik Başvuru": Playwright-driven application-form analysis, LLM optimization + form answering, and automated submission — `POST /apply/prepare` and `POST /apply/submit`, per the Faz 2 section of `docs/superpowers/specs/2026-07-16-app-shell-and-auto-apply-design.md`.

**Architecture:** Three layers. (1) `page_analysis.py` — pure functions over an HTML string (login/CAPTCHA detection, form-schema extraction via lxml, absolute-XPath selectors) — fully unit-testable without a browser. (2) `browser.py` — a minimal `BrowserDriver` protocol with a `PlaywrightDriver` implementation (persistent Chromium profile so user logins survive between calls) injected via a FastAPI dependency; tests inject a `FakeDriver`. (3) `apply.py` services + router orchestrating: goto → analyze → LLM (`chat_json`, existing retry/logging) → respond with statuses `ready | login_required | captcha | form_not_found`, and on submit: re-analyze → fill approved answers → upload ATS PDF → click submit → screenshot.

**Tech Stack:** FastAPI, Playwright (sync API, Chromium, persistent context), lxml (already a dependency), existing `LLMClient`/`render_pdf`/auth/usage services.

## Global Constraints

- Working dir: `C:\Users\ASUS\Desktop\cv-ai` (capital **D**). API commands run in `api/` with `.venv\Scripts\python`.
- Tests NEVER launch a real browser — every endpoint test injects `FakeDriver` via `app.dependency_overrides`. Real-browser verification is one manual smoke step in the final task.
- LLM is faked with the existing `override_llm` from `api/tests/conftest.py`; the prompt must escape literal `{`/`}` as `{{`/`}}` because `SYSTEM.format(language=...)` is applied (a real bug happened here before).
- No CAPTCHA bypass: detection returns a status and stops. Never store user credentials; login happens only in the visible browser window (persistent profile keeps the session).
- Follow existing error-shape convention: JSON `{"detail": {"code": ...}}` for HTTP errors; the new flow statuses (`ready`/`login_required`/`captcha`/`form_not_found`/`submitted`/`failed`) are 200-responses with a `status` field, per the spec.
- `POST /apply/prepare` counts against the daily AI limit (`check_usage`); `/apply/submit` only requires auth (`get_current_user`).
- New Python deps get exact-version pins appended to `api/requirements.txt` (pin whatever `pip show playwright` reports after install).

---

### Task 1: Page analysis — schemas, detection, form extraction (pure)

**Files:**
- Modify: `api/app/schemas.py` (append models)
- Create: `api/app/services/page_analysis.py`
- Create: `api/tests/fixtures/greenhouse_like.html`
- Create: `api/tests/fixtures/login_wall.html`
- Create: `api/tests/fixtures/captcha_page.html`
- Create: `api/tests/test_page_analysis.py`

**Interfaces:**
- Consumes: nothing new (lxml already installed).
- Produces (used by Tasks 3-4): `FormField`, `FormSchema` in `app.schemas`; `detect_login(html) -> bool`, `detect_captcha(html) -> bool`, `extract_form(html) -> FormSchema` in `app.services.page_analysis`. Selectors are absolute XPaths (Playwright locator syntax `xpath=<path>` is applied by the driver layer, not here).

- [ ] **Step 1: Append schemas**

Append to `api/app/schemas.py`:

```python
class FormField(BaseModel):
    id: str                      # stable key: name attr, else label slug, else field-N
    selector: str                # absolute XPath of the element
    label: str
    type: str                    # text | textarea | select | radio | checkbox | file
    options: list[str] = []      # visible labels (select options / radio choices)
    option_selectors: list[str] = []  # XPath per option (radio only; parallel to options)
    required: bool = False


class FormSchema(BaseModel):
    fields: list[FormField] = []
    submit_selector: str | None = None
```

- [ ] **Step 2: Write HTML fixtures**

`api/tests/fixtures/greenhouse_like.html`:

```html
<!doctype html>
<html><body>
<header><nav><form class="search"><input type="text" name="q" placeholder="Search"></form></nav></header>
<main>
  <h1>Backend Developer</h1>
  <p>We are hiring a Backend Developer in Istanbul. 3+ years Python required.
     You will build APIs with FastAPI and PostgreSQL. Remote friendly.</p>
  <form id="application">
    <label for="fn">Full name</label>
    <input id="fn" name="full_name" type="text" required>
    <label for="em">Email</label>
    <input id="em" name="email" type="email" required>
    <label for="ph">Phone</label>
    <input id="ph" name="phone" type="tel">
    <label for="cvf">Resume/CV</label>
    <input id="cvf" name="resume" type="file">
    <label for="why">Why do you want to work here?</label>
    <textarea id="why" name="motivation"></textarea>
    <label for="exp">Years of Python experience</label>
    <select id="exp" name="experience">
      <option>0-1</option>
      <option>1-3</option>
      <option>3-5</option>
      <option>5+</option>
    </select>
    <fieldset>
      <legend>Work permit?</legend>
      <label><input type="radio" name="permit" value="yes"> Yes</label>
      <label><input type="radio" name="permit" value="no"> No</label>
    </fieldset>
    <label><input type="checkbox" name="kvkk" required> I accept the privacy policy</label>
    <input type="hidden" name="token" value="x">
    <button type="submit">Submit application</button>
  </form>
</main>
</body></html>
```

`api/tests/fixtures/login_wall.html`:

```html
<!doctype html>
<html><body>
  <h1>Sign in to continue</h1>
  <form action="/login">
    <input type="email" name="username" placeholder="Email">
    <input type="password" name="password" placeholder="Password">
    <button type="submit">Sign in</button>
  </form>
</body></html>
```

`api/tests/fixtures/captcha_page.html`:

```html
<!doctype html>
<html><body>
  <h1>Backend Developer</h1>
  <form id="application">
    <label for="fn">Full name</label><input id="fn" name="full_name" type="text">
    <label for="em">Email</label><input id="em" name="email" type="email">
    <label for="why">Why us?</label><textarea id="why" name="why"></textarea>
    <div class="g-recaptcha" data-sitekey="key"></div>
    <button type="submit">Apply</button>
  </form>
</body></html>
```

- [ ] **Step 3: Write the failing tests**

Create `api/tests/test_page_analysis.py`:

```python
from pathlib import Path

from app.services.page_analysis import detect_captcha, detect_login, extract_form

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_form_fields_and_types():
    schema = extract_form(_read("greenhouse_like.html"))
    by_id = {f.id: f for f in schema.fields}
    assert by_id["full_name"].type == "text"
    assert by_id["full_name"].required is True
    assert by_id["full_name"].label == "Full name"
    assert by_id["email"].type == "text"
    assert by_id["resume"].type == "file"
    assert by_id["motivation"].type == "textarea"
    assert by_id["experience"].type == "select"
    assert by_id["experience"].options == ["0-1", "1-3", "3-5", "5+"]
    assert by_id["permit"].type == "radio"
    assert by_id["permit"].options == ["Yes", "No"]
    assert len(by_id["permit"].option_selectors) == 2
    assert by_id["kvkk"].type == "checkbox"
    # hidden inputs and the tiny search form are ignored
    assert "token" not in by_id
    assert "q" not in by_id


def test_extract_form_picks_biggest_form_and_submit():
    schema = extract_form(_read("greenhouse_like.html"))
    assert schema.submit_selector is not None
    assert "button" in schema.submit_selector


def test_extract_form_selectors_are_xpaths():
    schema = extract_form(_read("greenhouse_like.html"))
    assert all(f.selector.startswith("/") for f in schema.fields)


def test_no_form_returns_empty():
    assert extract_form("<html><body><p>hi</p></body></html>").fields == []


def test_detect_login():
    assert detect_login(_read("login_wall.html")) is True
    assert detect_login(_read("greenhouse_like.html")) is False


def test_detect_captcha():
    assert detect_captcha(_read("captcha_page.html")) is True
    assert detect_captcha(_read("greenhouse_like.html")) is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run (in `api/`): `.venv\Scripts\python -m pytest tests/test_page_analysis.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.page_analysis`.

- [ ] **Step 5: Implement `page_analysis.py`**

Create `api/app/services/page_analysis.py`:

```python
"""Pure HTML analysis for application pages: no browser, no network."""
import re

from lxml import html as lxml_html

from app.schemas import FormField, FormSchema

_TEXT_INPUT_TYPES = {"text", "email", "tel", "url", "number", "date", None, ""}
_CAPTCHA_MARKERS = ("g-recaptcha", "h-captcha", "cf-turnstile", "recaptcha/api")


def detect_captcha(page_html: str) -> bool:
    return any(marker in page_html for marker in _CAPTCHA_MARKERS)


def detect_login(page_html: str) -> bool:
    doc = lxml_html.fromstring(page_html)
    return bool(doc.xpath("//input[@type='password']"))


def _label_text(el, doc) -> str:
    el_id = el.get("id")
    if el_id:
        labels = doc.xpath(f"//label[@for='{el_id}']")
        if labels:
            return labels[0].text_content().strip()
    parent = el.getparent()
    while parent is not None:
        if parent.tag == "label":
            return parent.text_content().strip()
        if parent.tag == "fieldset":
            legends = parent.xpath("./legend")
            if legends:
                return legends[0].text_content().strip()
        parent = parent.getparent()
    return (el.get("aria-label") or el.get("placeholder") or el.get("name") or "").strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "field"


def extract_form(page_html: str) -> FormSchema:
    doc = lxml_html.fromstring(page_html)
    tree = doc.getroottree()

    forms = doc.xpath("//form")
    best, best_count = None, 0
    for form in forms:
        count = len(form.xpath(
            ".//input[not(@type='hidden')] | .//textarea | .//select"))
        if count > best_count:
            best, best_count = form, count
    # fewer than 2 visible controls: not an application form (search bars etc.)
    if best is None or best_count < 2:
        return FormSchema()

    fields: list[FormField] = []
    used_ids: set[str] = set()
    radios_done: set[str] = set()

    def field_id(el, label: str) -> str:
        base = el.get("name") or _slug(label)
        candidate, n = base, 1
        while candidate in used_ids:
            n += 1
            candidate = f"{base}-{n}"
        used_ids.add(candidate)
        return candidate

    for el in best.xpath(".//input | .//textarea | .//select"):
        tag = el.tag
        itype = (el.get("type") or "").lower()
        if tag == "input" and itype in ("hidden", "submit", "button", "password"):
            continue
        label = _label_text(el, doc)
        required = el.get("required") is not None or el.get("aria-required") == "true"
        selector = tree.getpath(el)

        if tag == "textarea":
            ftype, options, opt_sel = "textarea", [], []
        elif tag == "select":
            ftype = "select"
            options = [o.text_content().strip() for o in el.xpath("./option")
                       if o.text_content().strip()]
            opt_sel = []
        elif itype == "radio":
            name = el.get("name") or ""
            if name in radios_done:
                continue
            radios_done.add(name)
            group = best.xpath(f".//input[@type='radio'][@name='{name}']")
            ftype = "radio"
            options = [_label_text(r, doc) for r in group]
            opt_sel = [tree.getpath(r) for r in group]
            # group label: the fieldset legend, not the first choice's label
            legends = el.xpath("ancestor::fieldset/legend")
            if legends:
                label = legends[0].text_content().strip()
        elif itype == "checkbox":
            ftype, options, opt_sel = "checkbox", [], []
        elif itype == "file":
            ftype, options, opt_sel = "file", [], []
        elif itype in _TEXT_INPUT_TYPES:
            ftype, options, opt_sel = "text", [], []
        else:
            continue

        fields.append(FormField(
            id=field_id(el, label), selector=selector, label=label,
            type=ftype, options=options, option_selectors=opt_sel,
            required=required,
        ))

    submit = best.xpath(".//button[@type='submit'] | .//input[@type='submit'] | .//button[not(@type)]")
    submit_selector = tree.getpath(submit[0]) if submit else None
    return FormSchema(fields=fields, submit_selector=submit_selector)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_page_analysis.py -q`
Expected: PASS (6 tests). Then full suite: `.venv\Scripts\python -m pytest -q` — all green.

- [ ] **Step 7: Commit**

```bash
git add api/app/schemas.py api/app/services/page_analysis.py api/tests/fixtures api/tests/test_page_analysis.py
git commit -m "feat(api): pure page analysis - form schema extraction, login/captcha detection"
```

---

### Task 2: Browser driver — Playwright wrapper + DI factory

**Files:**
- Create: `api/app/services/browser.py`
- Modify: `api/app/config.py` (profile dir setting)
- Modify: `api/requirements.txt` (playwright pin)
- Modify: `api/README.md` (setup note)
- Create: `api/tests/fake_browser.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces (used by Tasks 3-4): protocol `BrowserDriver` with methods `goto(url)`, `content() -> str`, `fill(xpath, value)`, `select_by_label(xpath, label)`, `click(xpath)`, `set_files(xpath, path)`, `wait(ms)`, `screenshot() -> bytes`, `close()`; `get_driver_factory()` FastAPI dependency returning `Callable[[bool], BrowserDriver]` (arg = headed). Tests use `FakeDriver` from `api/tests/fake_browser.py`.

- [ ] **Step 1: Install Playwright**

Run (in `api/`):

```
.venv\Scripts\pip install playwright
.venv\Scripts\playwright install chromium
.venv\Scripts\pip show playwright
```

Append to `api/requirements.txt` (alphabetical position, with `greenlet` and `pyee` if pip installed them): `playwright==<version pip show reported>` plus exact pins of any new transitive deps `pip show`/`pip freeze` reveals (compare `pip freeze` against the file).

- [ ] **Step 2: Add the profile-dir setting**

In `api/app/config.py`, inside `Settings`, after `daily_ai_limit`:

```python
    # Persistent Chromium profile for /apply: user logins on job sites survive
    # between prepare/submit calls. Never stores passwords ourselves.
    browser_profile_dir: str = ".browser-profile"
```

Add `.browser-profile/` to the repo root `.gitignore`.

- [ ] **Step 3: Implement the driver**

Create `api/app/services/browser.py`:

```python
"""Thin Playwright wrapper. Everything above this file talks to the
BrowserDriver protocol so tests can inject a fake."""
from typing import Callable, Protocol

from app.config import get_settings


class BrowserDriver(Protocol):
    def goto(self, url: str) -> None: ...
    def content(self) -> str: ...
    def fill(self, xpath: str, value: str) -> None: ...
    def select_by_label(self, xpath: str, label: str) -> None: ...
    def click(self, xpath: str) -> None: ...
    def set_files(self, xpath: str, path: str) -> None: ...
    def wait(self, ms: int) -> None: ...
    def screenshot(self) -> bytes: ...
    def close(self) -> None: ...


class PlaywrightDriver:
    def __init__(self, headed: bool):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            get_settings().browser_profile_dir,
            headless=not headed,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(15_000)

    def goto(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # let client-side apps (Greenhouse, Lever) render the form
        self._page.wait_for_timeout(2_000)

    def content(self) -> str:
        return self._page.content()

    def fill(self, xpath: str, value: str) -> None:
        self._page.locator(f"xpath={xpath}").fill(value)

    def select_by_label(self, xpath: str, label: str) -> None:
        self._page.locator(f"xpath={xpath}").select_option(label=label)

    def click(self, xpath: str) -> None:
        self._page.locator(f"xpath={xpath}").click()

    def set_files(self, xpath: str, path: str) -> None:
        self._page.locator(f"xpath={xpath}").set_input_files(path)

    def wait(self, ms: int) -> None:
        self._page.wait_for_timeout(ms)

    def screenshot(self) -> bytes:
        return self._page.screenshot(full_page=False)

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._pw.stop()


def get_driver_factory() -> Callable[[bool], BrowserDriver]:
    return lambda headed: PlaywrightDriver(headed)
```

- [ ] **Step 4: Implement the FakeDriver for tests**

Create `api/tests/fake_browser.py`:

```python
"""Records interactions; serves queued HTML snapshots."""


class FakeDriver:
    def __init__(self, pages: list[str]):
        self._pages = list(pages)   # served by successive content() calls
        self.gotos: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.selects: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.files: list[tuple[str, str]] = []
        self.closed = False

    def goto(self, url):
        self.gotos.append(url)

    def content(self):
        return self._pages.pop(0) if len(self._pages) > 1 else self._pages[0]

    def fill(self, xpath, value):
        self.fills.append((xpath, value))

    def select_by_label(self, xpath, label):
        self.selects.append((xpath, label))

    def click(self, xpath):
        self.clicks.append(xpath)

    def set_files(self, xpath, path):
        self.files.append((xpath, path))

    def wait(self, ms):
        pass

    def screenshot(self):
        return b"\x89PNG-fake"

    def close(self):
        self.closed = True
```

- [ ] **Step 5: Verify imports and suite**

Run: `.venv\Scripts\python -c "from app.services.browser import get_driver_factory; print('ok')"`
Expected: `ok` (no browser launches at import time).
Run full suite: `.venv\Scripts\python -m pytest -q` — all green.

- [ ] **Step 6: Update api/README.md**

Add under Setup, after the pip install line:

```
    .venv\Scripts\playwright install chromium   # for /apply automation
```

- [ ] **Step 7: Commit**

```bash
git add api/app/services/browser.py api/app/config.py api/requirements.txt api/README.md api/tests/fake_browser.py .gitignore
git commit -m "feat(api): Playwright browser driver with persistent profile and DI factory"
```

---

### Task 3: `POST /apply/prepare` — analyze, optimize, answer

**Files:**
- Modify: `api/app/schemas.py` (append `FieldAnswer`)
- Create: `api/app/services/apply.py`
- Create: `api/app/routers/apply.py`
- Modify: `api/app/main.py` (register router)
- Create: `api/tests/test_apply_prepare.py`

**Interfaces:**
- Consumes: Task 1 (`extract_form`, `detect_login`, `detect_captcha`, `FormSchema`), Task 2 (`BrowserDriver`, `get_driver_factory`), existing `LLMClient.chat_json`, `MODEL_SMART`, `check_usage`, `trafilatura`.
- Produces: `POST /apply/prepare` body `{cv: CVData, url: str, language: str, headed: bool=false}` → 200 `{status: "ready", form: FormField[], cv, changes, cover_letter, answers, job_text}` or `{status: "login_required" | "captcha" | "form_not_found", job_text?}`. Service fn `prepare_application(cv, url, language, headed, llm, make_driver) -> dict` (Task 4's frontend plan consumes the endpoint; `FieldAnswer {field_id, value}`).

- [ ] **Step 1: Append the answer schema**

Append to `api/app/schemas.py`:

```python
class FieldAnswer(BaseModel):
    field_id: str
    value: str = ""
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `api/tests/test_apply_prepare.py`:

```python
import json
from pathlib import Path

from app.main import app
from app.services.browser import get_driver_factory
from tests.conftest import SAMPLE_CV_JSON, override_llm
from tests.fake_browser import FakeDriver

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _use_driver(driver: FakeDriver):
    app.dependency_overrides[get_driver_factory] = lambda: (lambda headed: driver)
    return driver


PREPARE_OUT = json.dumps({
    "cv": json.loads(SAMPLE_CV_JSON),
    "changes": ["Reordered skills to match the posting"],
    "cover_letter": "I am excited to apply...",
    "answers": [
        {"field_id": "full_name", "value": "Ada Lovelace"},
        {"field_id": "motivation", "value": "I love building APIs."},
        {"field_id": "experience", "value": "3-5"},
    ],
})


def test_prepare_ready(client, auth_headers):
    driver = _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert any(f["id"] == "motivation" for f in body["form"])
    assert body["answers"][2]["value"] == "3-5"
    assert body["cover_letter"].startswith("I am excited")
    assert "Backend Developer" in body["job_text"]
    assert driver.gotos == ["https://jobs.example.com/1"]
    assert driver.closed is True


def test_prepare_login_required(client, auth_headers):
    _use_driver(FakeDriver([_html("login_wall.html")]))
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "login_required"


def test_prepare_captcha(client, auth_headers):
    _use_driver(FakeDriver([_html("captcha_page.html")]))
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "captcha"


def test_prepare_form_not_found(client, auth_headers):
    _use_driver(FakeDriver(["<html><body><h1>Job</h1><p>" + "desc " * 60 + "</p></body></html>"]))
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "tr",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "form_not_found"


def test_prepare_headed_waits_for_login(client, auth_headers):
    # first snapshot: login wall; second: the real form (user logged in meanwhile)
    driver = _use_driver(FakeDriver([_html("login_wall.html"), _html("greenhouse_like.html")]))
    override_llm([PREPARE_OUT])
    r = client.post("/apply/prepare", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com", "language": "en",
        "headed": True,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert driver.closed is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_apply_prepare.py -q`
Expected: FAIL — 404 (router not registered) / import errors.

- [ ] **Step 4: Implement the service**

Create `api/app/services/apply.py`:

```python
import base64
import logging
import tempfile
import time
from pathlib import Path

import trafilatura
from pydantic import BaseModel

from app.schemas import CVData, FieldAnswer, FormField, FormSchema
from app.services import ats
from app.services.browser import BrowserDriver
from app.services.llm import MODEL_SMART, LLMClient
from app.services.page_analysis import detect_captcha, detect_login, extract_form

logger = logging.getLogger(__name__)

LOGIN_WAIT_SECONDS = 180
LOGIN_POLL_SECONDS = 2

SYSTEM = (
    "You optimize a CV for one specific job application and answer its form. "
    "Input JSON: cv, job_text, form (fields with id/label/type/options). "
    "Respond ONLY with JSON: "
    '{{"cv": <optimized CV, same schema>, "changes": [str], '
    '"cover_letter": str, "answers": [{{"field_id": str, "value": str}}]}}. '
    "Rules: NEVER invent facts absent from the CV — only reorder, reword and "
    "emphasize. changes = short user-facing list of what you altered. "
    "cover_letter: always write one, first person, active voice, grounded in "
    "the CV and the posting. answers: one per form field except type=file; "
    "identity fields (name/email/phone/location) come from the CV; for "
    "select/radio pick EXACTLY one option verbatim from options; if the CV "
    "lacks the information, use value \"\" so the user fills it. "
    "Answer in language: {language}."
)


class PrepareOut(BaseModel):
    cv: CVData
    changes: list[str] = []
    cover_letter: str | None = None
    answers: list[FieldAnswer] = []


def _job_text(html: str) -> str:
    text = trafilatura.extract(html)
    if text:
        return text
    # trafilatura is picky on minimal pages; crude fallback keeps the flow alive
    from lxml import html as lxml_html
    return lxml_html.fromstring(html).text_content().strip()[:8000]


def _page_state(html: str) -> tuple[bool, FormSchema]:
    """(is_login_wall, form). A password field ALWAYS means login wall — a
    login form's surviving fields must never be mistaken for the application
    form (password inputs are filtered out of extract_form)."""
    return detect_login(html), extract_form(html)


def _wait_for_login(driver: BrowserDriver) -> tuple[str, FormSchema]:
    """Headed mode: user is logging in by hand; poll until the login wall is
    gone and an application form appears (or the wait times out)."""
    deadline = time.monotonic() + LOGIN_WAIT_SECONDS
    while True:
        html = driver.content()
        is_login, schema = _page_state(html)
        if (schema.fields and not is_login) or time.monotonic() > deadline:
            return html, schema
        time.sleep(LOGIN_POLL_SECONDS)


class PrepareIn(BaseModel):
    cv: CVData
    job_text: str
    form: list[FormField]


def prepare_application(cv: CVData, url: str, language: str, headed: bool,
                        llm: LLMClient, make_driver) -> dict:
    driver: BrowserDriver = make_driver(headed)
    try:
        driver.goto(url)
        html = driver.content()
        is_login, schema = _page_state(html)
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login = detect_login(html)
        if detect_captcha(html):
            return {"status": "captcha", "job_text": _job_text(html)}
        if is_login:
            return {"status": "login_required"}
        if not schema.fields:
            return {"status": "form_not_found", "job_text": _job_text(html)}

        job_text = _job_text(html)
        user_payload = PrepareIn(cv=cv, job_text=job_text,
                                 form=schema.fields).model_dump_json()
        out = llm.chat_json(MODEL_SMART, SYSTEM.format(language=language),
                            user_payload, PrepareOut)
        return {
            "status": "ready",
            "form": [f.model_dump() for f in schema.fields],
            "cv": out.cv.model_dump(),
            "changes": out.changes,
            "cover_letter": out.cover_letter,
            "answers": [a.model_dump() for a in out.answers],
            "job_text": job_text,
        }
    finally:
        driver.close()
```

- [ ] **Step 5: Implement the router and register it**

Create `api/app/routers/apply.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas import CVData, FieldAnswer
from app.services.apply import prepare_application
from app.services.browser import get_driver_factory
from app.services.llm import LLMClient, get_llm
from app.services.usage import check_usage

router = APIRouter(prefix="/apply", tags=["apply"])


class PrepareRequest(BaseModel):
    cv: CVData
    url: str
    language: str = "tr"
    headed: bool = False


@router.post("/prepare")
def prepare(
    req: PrepareRequest,
    user_id: str = Depends(check_usage),
    llm: LLMClient = Depends(get_llm),
    make_driver=Depends(get_driver_factory),
):
    return prepare_application(req.cv, req.url, req.language, req.headed,
                               llm, make_driver)
```

In `api/app/main.py`: add `from app.routers import apply as apply_router` (alphabetical with the others) and `app.include_router(apply_router.router)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_apply_prepare.py -q`
Expected: PASS (5 tests). Full suite green: `.venv\Scripts\python -m pytest -q`.

- [ ] **Step 7: Commit**

```bash
git add api/app/schemas.py api/app/services/apply.py api/app/routers/apply.py api/app/main.py api/tests/test_apply_prepare.py
git commit -m "feat(api): POST /apply/prepare - form analysis, CV optimization, form answers"
```

---

### Task 4: `POST /apply/submit` — fill, upload, submit, screenshot

**Files:**
- Modify: `api/app/services/apply.py` (append submit logic)
- Modify: `api/app/routers/apply.py` (append endpoint)
- Create: `api/tests/test_apply_submit.py`

**Interfaces:**
- Consumes: Task 1-3 modules; existing `ats.render_pdf`.
- Produces: `POST /apply/submit` body `{cv: CVData, url: str, language: str, answers: FieldAnswer[], headed: bool=false}` → 200 `{status: "submitted", screenshot: <base64 png>}` or `{status: "failed", reason: str}` or `{status: "login_required"}` / `{status: "captcha"}`. Service fn `submit_application(cv, url, language, answers, headed, make_driver) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_apply_submit.py`:

```python
import base64
import json
from pathlib import Path

from app.main import app
from app.services.browser import get_driver_factory
from tests.conftest import SAMPLE_CV_JSON
from tests.fake_browser import FakeDriver

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _use_driver(driver: FakeDriver):
    app.dependency_overrides[get_driver_factory] = lambda: (lambda headed: driver)
    return driver


ANSWERS = [
    {"field_id": "full_name", "value": "Ada Lovelace"},
    {"field_id": "email", "value": "ada@example.com"},
    {"field_id": "motivation", "value": "I love APIs."},
    {"field_id": "experience", "value": "3-5"},
    {"field_id": "permit", "value": "Yes"},
    {"field_id": "kvkk", "value": "yes"},
]


def test_submit_fills_and_submits(client, auth_headers):
    driver = _use_driver(FakeDriver([_html("greenhouse_like.html")]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://jobs.example.com/1",
        "language": "en", "answers": ANSWERS,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "submitted"
    assert base64.b64decode(body["screenshot"]).startswith(b"\x89PNG")
    filled = dict(driver.fills)
    assert any("full_name" in sel or "input[1]" in sel for sel in filled)
    assert ("I love APIs." in filled.values())
    assert driver.selects and driver.selects[0][1] == "3-5"
    # radio "Yes" + checkbox + submit button all clicked
    assert len(driver.clicks) >= 3
    # the ATS PDF was attached to the file field
    assert driver.files and driver.files[0][1].endswith(".pdf")
    assert driver.closed is True


def test_submit_captcha_stops(client, auth_headers):
    _use_driver(FakeDriver([_html("captcha_page.html")]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "tr", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "captcha"
    assert r.json().get("screenshot") is None


def test_submit_form_gone_fails(client, auth_headers):
    _use_driver(FakeDriver(["<html><body><p>gone</p></body></html>"]))
    r = client.post("/apply/submit", headers=auth_headers, json={
        "cv": json.loads(SAMPLE_CV_JSON), "url": "https://x.com",
        "language": "tr", "answers": ANSWERS,
    })
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_apply_submit.py -q`
Expected: FAIL — 404 for /apply/submit.

- [ ] **Step 3: Implement submit in `apply.py`**

Append to `api/app/services/apply.py`:

```python
def _fill_form(driver: BrowserDriver, schema: FormSchema,
               answers: list[FieldAnswer], pdf_path: str) -> None:
    by_id = {f.id: f for f in schema.fields}
    values = {a.field_id: a.value for a in answers}
    for field in schema.fields:
        if field.type == "file":
            driver.set_files(field.selector, pdf_path)
            continue
        value = values.get(field.id, "")
        if not value:
            continue
        if field.type in ("text", "textarea"):
            driver.fill(field.selector, value)
        elif field.type == "select":
            driver.select_by_label(field.selector, value)
        elif field.type == "radio":
            if value in field.options:
                driver.click(field.option_selectors[field.options.index(value)])
        elif field.type == "checkbox":
            if value.lower() in ("yes", "true", "on", "evet", "1"):
                driver.click(field.selector)


def submit_application(cv: CVData, url: str, language: str,
                       answers: list[FieldAnswer], headed: bool,
                       make_driver) -> dict:
    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()

    driver: BrowserDriver = make_driver(headed)
    try:
        driver.goto(url)
        html = driver.content()
        is_login, schema = _page_state(html)
        if headed and (is_login or not schema.fields):
            html, schema = _wait_for_login(driver)
            is_login = detect_login(html)
        if detect_captcha(html):
            return {"status": "captcha"}
        if is_login:
            return {"status": "login_required"}
        if not schema.fields:
            return {"status": "failed", "reason": "form_not_found"}

        _fill_form(driver, schema, answers, tmp.name)
        if schema.submit_selector:
            driver.click(schema.submit_selector)
        else:
            return {"status": "failed", "reason": "no_submit_button"}
        driver.wait(3_000)
        shot = base64.b64encode(driver.screenshot()).decode()
        return {"status": "submitted", "screenshot": shot}
    except Exception as exc:  # site quirks must not become a 500
        logger.warning("submit failed for %s: %s", url, exc)
        return {"status": "failed", "reason": str(exc)}
    finally:
        driver.close()
        Path(tmp.name).unlink(missing_ok=True)
```

- [ ] **Step 4: Append the endpoint**

Append to `api/app/routers/apply.py`:

```python
from app.auth import get_current_user  # move to top imports
from app.services.apply import submit_application  # merge with existing import


class SubmitRequest(BaseModel):
    cv: CVData
    url: str
    language: str = "tr"
    answers: list[FieldAnswer] = []
    headed: bool = False


@router.post("/submit")
def submit(
    req: SubmitRequest,
    user_id: str = Depends(get_current_user),
    make_driver=Depends(get_driver_factory),
):
    return submit_application(req.cv, req.url, req.language, req.answers,
                              req.headed, make_driver)
```

(Adjust imports at the top of the file accordingly — no mid-file imports.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_apply_submit.py -q`
Expected: PASS (3 tests). Full suite: `.venv\Scripts\python -m pytest -q` — all green.

- [ ] **Step 6: Commit**

```bash
git add api/app/services/apply.py api/app/routers/apply.py api/tests/test_apply_submit.py
git commit -m "feat(api): POST /apply/submit - fill form, upload ATS PDF, submit, screenshot"
```

---

### Task 5: Real-browser smoke + docs

**Files:**
- Modify: `api/README.md` (endpoint docs)

- [ ] **Step 1: Manual smoke test with the real driver**

With the venv active in `api/`, run this one-off script (adjust nothing else):

```
.venv\Scripts\python -c "from app.services.browser import PlaywrightDriver; d = PlaywrightDriver(headed=True); d.goto('https://example.com'); print(len(d.content())); d.close(); print('browser ok')"
```

Expected: a Chromium window opens briefly, prints a content length and `browser ok`. This is the only step that launches a real browser.

- [ ] **Step 2: Document the endpoints**

In `api/README.md`, add a short section:

```
## Apply automation

- `POST /apply/prepare` — opens the application URL (headless; `headed: true`
  opens a visible window so the user can log in), extracts the form, and asks
  the LLM to optimize the CV and draft answers. Statuses: ready,
  login_required, captcha, form_not_found.
- `POST /apply/submit` — re-opens the page, fills the approved answers,
  uploads the ATS PDF, clicks submit, returns a screenshot. Statuses:
  submitted, failed, login_required, captcha.
- Browser state lives in `.browser-profile/` (git-ignored). CAPTCHAs are
  never bypassed; nothing is submitted without the user-approved answers.
```

- [ ] **Step 3: Full suite + commit**

Run: `.venv\Scripts\python -m pytest -q` — all green.

```bash
git add api/README.md
git commit -m "docs(api): apply automation endpoints and browser profile notes"
```
