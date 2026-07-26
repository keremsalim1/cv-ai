# Role-Based Form Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace field discovery and addressing in assisted apply with an engine that reads the live page's roles instead of parsing an HTML string, so shadow DOM, custom comboboxes and iframes stop being per-portal problems.

**Architecture:** Injected JS walks the DOM (descending into shadow roots), stamps every control with `data-cvai-ref`, and returns raw observations as JSON. A pure Python function turns those observations into the existing `FormSchema`. Fill strategies dispatch per role, and a second probe verifies what actually landed. Only assisted mode changes; the auto flow keeps `extract_form(html)`.

**Tech Stack:** Python 3 / FastAPI / pydantic / Playwright 1.61 (sync API) / pytest; Next.js + vitest on the web side.

**Spec:** `docs/superpowers/specs/2026-07-26-platform-layer-design.md`

## Global Constraints

- **Assisted mode only.** `prepare_application` and `submit_application` keep calling `extract_form(html)`. No task may change their behaviour. The 99 existing API tests must stay green throughout.
- **The probe collects, Python decides.** `probe.js` returns observations only — no naming policy, no field typing, no scope filtering. Anything resembling a decision belongs in `form_build.py`.
- **Refs are per-request.** `data-cvai-ref` stamps are never persisted across HTTP calls; each probe→fill→verify cycle stamps fresh.
- **Refinement to the spec:** the spec specifies `FormField.frame_path: list[int]`. Implement `FormField.frame: int = 0` instead — a flat index into `page.frames`, which Playwright already exposes as a flat list covering nested frames. Verified: `page.frames[1].locator('[data-cvai-ref="x0"]').fill(...)` reaches inside an iframe.
- **No selector-engine parameter.** Verified: Playwright auto-detects `//…` as XPath and `[attr="v"]` as CSS, so existing driver methods accept both. Do not add an engine argument.
- **Never auto-submit.** `build_form` always returns `submit_selector=None`.
- Python: 4-space indent, double quotes, comments explain *why*. Tests name the behaviour, not the function.

---

### Task 1: Frame-aware browser driver

**Files:**
- Modify: `api/app/services/browser.py`
- Modify: `api/tests/fake_browser.py`
- Create: `api/tests/test_browser_driver.py`

**Interfaces:**
- Consumes: nothing
- Produces: `BrowserDriver.evaluate(script: str, frame: int = 0) -> Any`, `BrowserDriver.frame_count() -> int`, and a `frame: int = 0` keyword on `fill`, `select_by_label`, `click`, `set_checked`, `set_files`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_browser_driver.py`:

```python
"""The driver is the boundary we cannot fake: these run a real Chromium."""
import pytest

from app.services.browser import PlaywrightDriver

OUTER = """
<html><body>
  <input id="top" type="text">
  <iframe id="f" srcdoc="<html><body><input id=&quot;inner&quot; type=&quot;text&quot;></body></html>"></iframe>
</body></html>
"""


@pytest.fixture
def driver(tmp_path):
    d = PlaywrightDriver(headed=False, profile_dir=str(tmp_path / "profile"))
    yield d
    d.close()


def test_evaluate_runs_in_the_requested_frame(driver):
    driver.goto("data:text/html," + OUTER)
    assert driver.frame_count() == 2
    assert driver.evaluate("() => !!document.getElementById('top')", frame=0) is True
    assert driver.evaluate("() => !!document.getElementById('inner')", frame=1) is True


def test_actions_reach_inside_an_iframe(driver):
    driver.goto("data:text/html," + OUTER)
    driver.fill("#inner", "typed inside the frame", frame=1)
    assert driver.evaluate(
        "() => document.getElementById('inner').value", frame=1
    ) == "typed inside the frame"


def test_xpath_and_css_both_work_without_an_engine_argument(driver):
    driver.goto("data:text/html," + OUTER)
    driver.fill("//input[@id='top']", "via xpath")
    assert driver.evaluate("() => document.getElementById('top').value") == "via xpath"
    driver.fill('[id="top"]', "via css")
    assert driver.evaluate("() => document.getElementById('top').value") == "via css"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_browser_driver.py -q`
Expected: FAIL — `PlaywrightDriver.__init__() got an unexpected keyword argument 'headed'` is fine to fix by using positional args; the real failure is `AttributeError: 'PlaywrightDriver' object has no attribute 'frame_count'`.

- [ ] **Step 3: Implement**

In `api/app/services/browser.py`, add to the `BrowserDriver` Protocol:

```python
    def evaluate(self, script: str, frame: int = 0): ...
    def frame_count(self) -> int: ...
```

and give every existing action method a `frame: int = 0` keyword. Replace the body of `PlaywrightDriver`'s action methods with a shared locator helper:

```python
    def _loc(self, selector: str, frame: int):
        # page.frames[0] IS the main frame, so one path serves both cases.
        # Playwright picks the engine itself: "//x" is XPath, "[a=b]" is CSS.
        return self._page.frames[frame].locator(selector)

    def evaluate(self, script: str, frame: int = 0):
        return self._page.frames[frame].evaluate(script)

    def frame_count(self) -> int:
        return len(self._page.frames)

    def fill(self, selector: str, value: str, frame: int = 0) -> None:
        self._loc(selector, frame).fill(value)

    def select_by_label(self, selector: str, label: str, frame: int = 0) -> None:
        self._loc(selector, frame).select_option(label=label)

    def click(self, selector: str, frame: int = 0) -> None:
        self._loc(selector, frame).click()

    def set_checked(self, selector: str, checked: bool, frame: int = 0) -> None:
        self._loc(selector, frame).set_checked(checked)

    def set_files(self, selector: str, path: str, frame: int = 0) -> None:
        self._loc(selector, frame).set_input_files(path)
```

In `api/tests/fake_browser.py`, add to `FakeDriver`:

```python
    def __init__(self, pages: list[str], evaluations: list | None = None):
        ...                                   # keep the existing assignments
        self._evaluations = list(evaluations or [])
        self.evaluated: list[tuple[str, int]] = []
        self.frames = 1

    def evaluate(self, script, frame=0):
        self.evaluated.append((script, frame))
        # queued results are consumed in order; the last one repeats, so a test
        # that probes twice without caring about the second call still works
        return self._evaluations.pop(0) if len(self._evaluations) > 1 else (
            self._evaluations[0] if self._evaluations else [])

    def frame_count(self):
        return self.frames

```

and add `frame=0` to every existing `FakeDriver` action method signature (do not
change what they record yet — Task 5 does that).

- [ ] **Step 4: Run the tests**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 99 existing + 3 new.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/browser.py api/tests/fake_browser.py api/tests/test_browser_driver.py
git commit -m "feat(api): frame-aware browser driver with in-page evaluate"
```

---

### Task 2: The probe — collector script and its Python wrapper

**Files:**
- Create: `api/app/services/probe.js`
- Create: `api/app/services/page_probe.py`
- Create: `api/tests/test_page_probe.py`

**Interfaces:**
- Consumes: `driver.evaluate(script, frame)`, `driver.frame_count()` from Task 1
- Produces: `RawControl` (pydantic model, fields listed below) and `probe_controls(driver) -> list[RawControl]`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_page_probe.py`:

```python
"""The collector must see what page.content() cannot: shadow roots, custom
widgets, and controls inside frames."""
import pytest

from app.services.browser import PlaywrightDriver
from app.services.page_probe import probe_controls

SHADOW_PAGE = """
<html><body>
  <nav><input id="site-search" type="text" aria-label="Search jobs"></nav>
  <main>
    <div id="host"></div>
    <span id="lbl">Country</span>
    <div role="combobox" aria-labelledby="lbl" aria-autocomplete="list"></div>
  </main>
  <script>
    const r = document.getElementById('host').attachShadow({mode:'open'});
    const l = document.createElement('label');
    l.setAttribute('for','em'); l.textContent = 'Email';
    const i = document.createElement('input');
    i.id = 'em'; i.type = 'email'; i.required = true;
    r.append(l, i);
  </script>
</body></html>
"""


@pytest.fixture
def driver(tmp_path):
    d = PlaywrightDriver(headed=False, profile_dir=str(tmp_path / "profile"))
    yield d
    d.close()


def _by_label(controls, label):
    return next(c for c in controls if label in (
        c.label_text or c.labelledby_text or c.aria_label))


def test_probe_sees_a_control_inside_a_shadow_root(driver):
    driver.goto("data:text/html," + SHADOW_PAGE)
    controls = probe_controls(driver)
    email = _by_label(controls, "Email")
    assert email.role == "textbox"
    assert email.required is True


def test_probe_sees_a_div_combobox_as_a_combobox(driver):
    driver.goto("data:text/html," + SHADOW_PAGE)
    country = _by_label(probe_controls(driver), "Country")
    assert country.role == "combobox"
    assert country.autocomplete_hint == "list"


def test_probe_records_the_enclosing_landmark(driver):
    driver.goto("data:text/html," + SHADOW_PAGE)
    controls = probe_controls(driver)
    assert _by_label(controls, "Search jobs").landmark == "navigation"
    assert _by_label(controls, "Country").landmark == "main"


def test_probe_stamps_a_ref_that_addresses_the_control(driver):
    driver.goto("data:text/html," + SHADOW_PAGE)
    email = _by_label(probe_controls(driver), "Email")
    driver.fill(f'[data-cvai-ref="{email.ref}"]', "ada@example.com", frame=email.frame)
    assert driver.evaluate(
        "() => document.getElementById('host').shadowRoot"
        ".getElementById('em').value") == "ada@example.com"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_page_probe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.page_probe'`

- [ ] **Step 3: Write the collector**

Create `api/app/services/probe.js`. It is one arrow function taking the frame index, so Python can call it as `({SCRIPT})(3)`:

```javascript
(frameIndex) => {
  const CONTROL_ROLES = new Set(['combobox', 'listbox', 'textbox', 'searchbox',
    'checkbox', 'radio', 'switch', 'spinbutton', 'file', 'password']);
  const LANDMARK_ROLES = new Set(['banner', 'navigation', 'search',
    'contentinfo', 'main', 'form', 'dialog']);

  function* walk(root) {
    for (const el of root.querySelectorAll('*')) {
      yield el;
      if (el.shadowRoot) yield* walk(el.shadowRoot);
    }
  }

  function parentOf(node) {
    if (node.parentElement) return node.parentElement;
    const r = node.getRootNode();
    return r && r.host ? r.host : null;
  }

  function textOf(el) {
    return el ? (el.textContent || '').trim().replace(/\s+/g, ' ') : '';
  }

  function byId(el, id) {
    const r = el.getRootNode();
    return r.getElementById ? r.getElementById(id) : document.getElementById(id);
  }

  function labelledbyText(el) {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    return ids.map((id) => textOf(byId(el, id))).filter(Boolean).join(' ');
  }

  function labelText(el) {
    if (el.labels && el.labels.length) return textOf(el.labels[0]);
    if (el.id) {
      const r = el.getRootNode();
      const l = r.querySelector && r.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return textOf(l);
    }
    let p = parentOf(el);
    while (p) {
      if (p.tagName === 'LABEL') return textOf(p);
      if (p.tagName === 'FIELDSET') {
        const lg = p.querySelector('legend');
        if (lg) return textOf(lg);
      }
      p = parentOf(p);
    }
    return '';
  }

  function implicitRole(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag !== 'input') return '';
    // file and password are not ARIA roles; we carry them as pseudo-roles so
    // the Python side can type and drop them without re-reading the tag
    return ({ checkbox: 'checkbox', radio: 'radio', file: 'file',
      password: 'password', number: 'spinbutton', search: 'searchbox',
      range: 'slider', submit: '', button: '', hidden: '', image: '', reset: '',
    })[(el.getAttribute('type') || 'text').toLowerCase()] ?? 'textbox';
  }

  function landmarkOf(el) {
    let node = parentOf(el);
    while (node) {
      const role = (node.getAttribute('role') || '').toLowerCase();
      if (LANDMARK_ROLES.has(role)) return role;
      if (node.getAttribute('aria-modal') === 'true') return 'dialog';
      const tag = node.tagName.toLowerCase();
      if (tag === 'nav') return 'navigation';
      if (tag === 'header') return 'banner';
      if (tag === 'footer') return 'contentinfo';
      if (tag === 'main') return 'main';
      if (tag === 'form') return 'form';
      if (tag === 'dialog' && node.hasAttribute('open')) return 'dialog';
      node = parentOf(node);
    }
    return '';
  }

  function isVisible(el) {
    if (!el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  }

  function optionsOf(el) {
    if (el.tagName === 'SELECT') {
      return [...el.options].map(textOf).filter(Boolean);
    }
    const owns = el.getAttribute('aria-controls') || el.getAttribute('aria-owns');
    const box = owns ? byId(el, owns) : null;
    return box ? [...box.querySelectorAll('[role=option]')].map(textOf).filter(Boolean) : [];
  }

  let n = 0;
  const out = [];
  for (const el of walk(document)) {
    const role = (el.getAttribute('role') || '').toLowerCase() || implicitRole(el);
    if (!CONTROL_ROLES.has(role)) continue;
    const ref = frameIndex + '-' + (++n);
    el.setAttribute('data-cvai-ref', ref);
    out.push({
      ref, frame: frameIndex,
      tag: el.tagName.toLowerCase(),
      type: (el.getAttribute('type') || '').toLowerCase(),
      role,
      aria_label: (el.getAttribute('aria-label') || '').trim(),
      labelledby_text: labelledbyText(el),
      label_text: labelText(el),
      placeholder: (el.getAttribute('placeholder') || '').trim(),
      name: el.getAttribute('name') || '',
      value: el.value === undefined ? '' : String(el.value),
      required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      visible: isVisible(el),
      options: optionsOf(el),
      landmark: landmarkOf(el),
      autocomplete_hint: (el.getAttribute('aria-autocomplete') || '').toLowerCase(),
    });
  }
  return out;
};
```

Create `api/app/services/page_probe.py`:

```python
"""Runs the collector in every frame and returns raw observations.

The collector decides nothing: it reports what it saw and stamps each control
with an addressable ref. All naming, typing and scoping policy lives in
form_build, where it can be tested without a browser."""
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROBE_JS = (Path(__file__).parent / "probe.js").read_text(encoding="utf-8")


class RawControl(BaseModel):
    ref: str
    frame: int = 0
    tag: str = ""
    type: str = ""
    role: str = ""
    aria_label: str = ""
    labelledby_text: str = ""
    label_text: str = ""
    placeholder: str = ""
    name: str = ""
    value: str = ""
    required: bool = False
    disabled: bool = False
    visible: bool = True
    options: list[str] = []
    landmark: str = ""
    autocomplete_hint: str = ""


def probe_controls(driver) -> list[RawControl]:
    controls: list[RawControl] = []
    for frame in range(driver.frame_count()):
        try:
            raw = driver.evaluate(f"({PROBE_JS})({frame})", frame=frame)
        except Exception as exc:
            # A frame we cannot reach must not blank the whole page; the fields
            # we did find are still worth filling.
            logger.warning("[probe] frame %d unreadable: %s", frame, exc)
            continue
        controls.extend(RawControl(**c) for c in raw or [])
    return controls
```

- [ ] **Step 4: Run the tests**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_page_probe.py -q`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/probe.js api/app/services/page_probe.py api/tests/test_page_probe.py
git commit -m "feat(api): DOM collector that pierces shadow roots and frames"
```

---

### Task 3: Capture tool and real-portal fixtures (risk gate)

This task exists to settle Risk 1 in the spec before any per-portal assumption is baked into code. **Stop and report the measurements to the user at the end of this task.** If real Workday ARIA turns out to be poor, the remaining tasks need revisiting.

**Files:**
- Create: `api/tools/capture_page.py`
- Create: `api/tests/fixtures/inventories/` (captured `.json` files land here)

**Interfaces:**
- Consumes: `probe_controls(driver)` from Task 2
- Produces: fixture files `api/tests/fixtures/inventories/<platform>-<slug>.json`, each a JSON list of `RawControl` dicts

- [ ] **Step 1: Write the capture tool**

Create `api/tools/capture_page.py`:

```python
"""Capture a real application page as a test fixture.

Usage:
    python tools/capture_page.py <url> --platform workday --slug senior-dev

Opens a visible browser and waits for you to press Enter. Log in, click through
to the actual application form, THEN press Enter — the snapshot is taken of
whatever is on screen at that moment.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.browser import PlaywrightDriver          # noqa: E402
from app.services.page_probe import probe_controls          # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "inventories"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--platform", required=True)
    ap.add_argument("--slug", default="1")
    ap.add_argument("--profile", default=".capture-profile")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    driver = PlaywrightDriver(headed=True, profile_dir=args.profile)
    try:
        driver.goto(args.url)
        input("Navigate to the application form, then press Enter to capture... ")
        controls = probe_controls(driver)
        stem = f"{args.platform}-{args.slug}"
        (OUT / f"{stem}.json").write_text(
            json.dumps([c.model_dump() for c in controls], indent=2, ensure_ascii=False),
            encoding="utf-8")
        (OUT / f"{stem}.html").write_text(driver.content(), encoding="utf-8")
        (OUT / f"{stem}.png").write_bytes(driver.screenshot())
        visible = [c for c in controls if c.visible and not c.disabled]
        named = [c for c in visible
                 if c.aria_label or c.labelledby_text or c.label_text]
        print(f"captured {stem}: {len(controls)} controls, "
              f"{len(visible)} visible, {len(named)} with an accessible name")
        for c in visible:
            name = c.aria_label or c.labelledby_text or c.label_text or "(unnamed)"
            print(f"  {c.role:<10} {name[:60]}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Capture a real Workday posting**

Ask the user for a live Workday application URL. Run:

```bash
cd api && ./.venv/Scripts/python.exe tools/capture_page.py "<url>" --platform workday
```

Expected: a printed inventory where most visible controls have an accessible name and custom dropdowns appear as `combobox`.

- [ ] **Step 3: Capture Greenhouse, Lever and Kariyer.net the same way**

```bash
cd api && ./.venv/Scripts/python.exe tools/capture_page.py "<url>" --platform greenhouse
cd api && ./.venv/Scripts/python.exe tools/capture_page.py "<url>" --platform lever
cd api && ./.venv/Scripts/python.exe tools/capture_page.py "<url>" --platform kariyernet
```

- [ ] **Step 4: Report the measurement and decide**

For each platform report: total controls, visible controls, and how many carry an accessible name. Per the spec, the bet holds if named-visible is a large majority. Report to the user before continuing; if a platform scores poorly, note it as needing an adapter in Task 9 rather than silently proceeding.

- [ ] **Step 5: Commit**

```bash
git add api/tools/capture_page.py api/tests/fixtures/inventories
git commit -m "test(api): page capture tool and real-portal inventory fixtures"
```

---

### Task 4: Pure form builder

**Files:**
- Create: `api/app/services/form_build.py`
- Create: `api/tests/test_form_build.py`
- Modify: `api/app/schemas.py` (add `frame` to `FormField`)

**Interfaces:**
- Consumes: `RawControl` from Task 2, fixtures from Task 3
- Produces: `build_form(controls: list[RawControl]) -> FormSchema`, `accessible_name(control: RawControl) -> str`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_form_build.py`:

```python
import json
from pathlib import Path

from app.services.form_build import accessible_name, build_form
from app.services.page_probe import RawControl

FIXTURES = Path(__file__).parent / "fixtures" / "inventories"


def c(**kw) -> RawControl:
    kw.setdefault("ref", "0-1")
    return RawControl(**kw)


def test_accessible_name_prefers_labelledby_over_placeholder():
    assert accessible_name(c(labelledby_text="Country", placeholder="Pick one")) == "Country"


def test_accessible_name_falls_back_through_the_chain():
    assert accessible_name(c(aria_label="Email")) == "Email"
    assert accessible_name(c(label_text="Phone")) == "Phone"
    assert accessible_name(c(placeholder="Portfolio URL")) == "Portfolio URL"
    assert accessible_name(c(name="linkedin")) == "linkedin"


def test_page_chrome_is_dropped():
    form = build_form([
        c(ref="0-1", role="searchbox", aria_label="Search jobs", landmark="navigation"),
        c(ref="0-2", role="textbox", aria_label="Full name", landmark="main"),
    ])
    assert [f.label for f in form.fields] == ["Full name"]


def test_a_dialog_wins_over_the_rest_of_the_page():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Newsletter email", landmark="main"),
        c(ref="0-2", role="textbox", aria_label="Full name", landmark="dialog"),
        c(ref="0-3", role="combobox", aria_label="Country", landmark="dialog"),
    ])
    assert [f.label for f in form.fields] == ["Full name", "Country"]


def test_invisible_disabled_and_password_controls_never_become_fields():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Hidden", visible=False),
        c(ref="0-2", role="textbox", aria_label="Disabled", disabled=True),
        c(ref="0-3", role="password", aria_label="Password"),
        c(ref="0-4", role="textbox", aria_label="Full name"),
    ])
    assert [f.label for f in form.fields] == ["Full name"]


def test_a_typeahead_combobox_is_typed_apart_from_a_plain_one():
    form = build_form([
        c(ref="0-1", role="combobox", aria_label="Country"),
        c(ref="0-2", role="combobox", aria_label="City", autocomplete_hint="list"),
    ])
    assert [f.type for f in form.fields] == ["combobox", "typeahead"]


def test_radios_collapse_into_one_grouped_field():
    form = build_form([
        c(ref="0-1", role="radio", name="auth", label_text="Yes"),
        c(ref="0-2", role="radio", name="auth", label_text="No"),
    ])
    assert len(form.fields) == 1
    assert form.fields[0].type == "radio"
    assert form.fields[0].options == ["Yes", "No"]
    assert form.fields[0].option_selectors == [
        '[data-cvai-ref="0-1"]', '[data-cvai-ref="0-2"]']


def test_selector_and_frame_address_the_control():
    form = build_form([c(ref="2-7", frame=2, role="textbox", aria_label="Email")])
    assert form.fields[0].selector == '[data-cvai-ref="2-7"]'
    assert form.fields[0].frame == 2


def test_assisted_mode_never_exposes_a_submit_button():
    form = build_form([c(role="textbox", aria_label="Email")])
    assert form.submit_selector is None


def test_field_ids_stay_unique_when_labels_repeat():
    form = build_form([
        c(ref="0-1", role="textbox", aria_label="Name"),
        c(ref="0-2", role="textbox", aria_label="Name"),
    ])
    assert len({f.id for f in form.fields}) == 2


def test_real_captured_inventories_yield_fields():
    for path in FIXTURES.glob("*.json"):
        controls = [RawControl(**c) for c in json.loads(path.read_text(encoding="utf-8"))]
        form = build_form(controls)
        assert form.fields, f"{path.name} produced no fields"
        assert all(f.label for f in form.fields), f"{path.name} has an unlabelled field"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_form_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.form_build'`

- [ ] **Step 3: Add `frame` to the schema**

In `api/app/schemas.py`, inside `FormField`, after the `selector` line:

```python
    frame: int = 0               # index into page.frames; 0 is the main frame
```

- [ ] **Step 4: Implement the builder**

Create `api/app/services/form_build.py`:

```python
"""Turns raw observations into a FormSchema. Pure: no browser, no network, so
every rule here is testable against a captured inventory."""
import re

from app.schemas import FormField, FormSchema
from app.services.page_probe import RawControl

# Controls living in page chrome are never part of an application form.
CHROME_LANDMARKS = {"banner", "navigation", "search", "contentinfo"}
# Scopes in priority order: the modal the user is looking at beats the form,
# which beats the main region, which beats "everything we found".
SCOPES = ("dialog", "form", "main")

_TEXTUAL_ROLES = {"textbox", "searchbox", "spinbutton"}


def accessible_name(control: RawControl) -> str:
    for candidate in (control.labelledby_text, control.aria_label,
                      control.label_text, control.placeholder, control.name):
        if candidate and candidate.strip():
            return candidate.strip()
    return ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "field"


def _field_type(control: RawControl) -> str | None:
    role = control.role
    if role == "combobox":
        if control.tag == "select":
            return "select"
        return "typeahead" if control.autocomplete_hint in ("list", "both") else "combobox"
    if role == "listbox":
        return "listbox"
    if role in ("checkbox", "switch"):
        return "checkbox"
    if role == "radio":
        return "radio"
    if role == "file":
        return "file"
    if role in _TEXTUAL_ROLES:
        if control.tag == "textarea":
            return "textarea"
        return "date" if control.type == "date" else "text"
    return None


def _in_scope(controls: list[RawControl]) -> list[RawControl]:
    usable = [c for c in controls
              if c.visible and not c.disabled
              and c.role != "password"
              and c.landmark not in CHROME_LANDMARKS]
    for scope in SCOPES:
        scoped = [c for c in usable if c.landmark == scope]
        if scoped:
            return scoped
    return usable


def build_form(controls: list[RawControl]) -> FormSchema:
    fields: list[FormField] = []
    used_ids: set[str] = set()
    radio_groups: dict[str, FormField] = {}

    def field_id(control: RawControl, label: str) -> str:
        base = control.name or _slug(label)
        candidate, n = base, 1
        while candidate in used_ids:
            n += 1
            candidate = f"{base}-{n}"
        used_ids.add(candidate)
        return candidate

    for control in _in_scope(controls):
        ftype = _field_type(control)
        if ftype is None:
            continue
        label = accessible_name(control)
        selector = f'[data-cvai-ref="{control.ref}"]'

        if ftype == "radio":
            # One field per radio group; each member contributes an option.
            group = radio_groups.get(control.name)
            if group is None:
                group = FormField(id=field_id(control, label), selector=selector,
                                  frame=control.frame, label=label, type="radio",
                                  required=control.required)
                radio_groups[control.name] = group
                fields.append(group)
            group.options.append(label)
            group.option_selectors.append(selector)
            continue

        fields.append(FormField(
            id=field_id(control, label), selector=selector, frame=control.frame,
            label=label, type=ftype, options=list(control.options),
            required=control.required,
        ))

    # Assisted mode always hands the submit back to the user, so no schema we
    # build here may carry a submit target.
    return FormSchema(fields=fields, submit_selector=None)
```

Note on the radio group label: the group's `label` is the first member's label, matching the current `extract_form` behaviour when no fieldset legend exists. Improving it is out of scope.

- [ ] **Step 5: Run the tests**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_form_build.py -q`
Expected: PASS — 11 tests.

- [ ] **Step 6: Run the whole suite**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, nothing regressed.

- [ ] **Step 7: Commit**

```bash
git add api/app/services/form_build.py api/app/schemas.py api/tests/test_form_build.py
git commit -m "feat(api): build a form schema from role observations"
```

---

### Task 5: Fill strategies

**Files:**
- Create: `api/app/services/fill_strategies.py`
- Create: `api/tests/test_fill_strategies.py`
- Modify: `api/app/schemas.py` (add `FieldOutcome`)

**Interfaces:**
- Consumes: `FormField` (with `frame`) from Task 4, `driver` from Task 1
- Produces: `FieldOutcome` (pydantic: `field_id, label, value, status, reason`) and `fill_field(driver, field, value, pdf_path) -> FieldOutcome`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_fill_strategies.py`:

```python
from app.schemas import FormField
from app.services.fill_strategies import fill_field
from tests.fake_browser import FakeDriver


def field(**kw) -> FormField:
    kw.setdefault("id", "f1")
    kw.setdefault("selector", '[data-cvai-ref="0-1"]')
    kw.setdefault("label", "Field")
    return FormField(**kw)


def test_text_is_typed_into_its_own_frame():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="text", frame=2), "Ada", pdf_path="/tmp/cv.pdf")
    assert d.fills == [('[data-cvai-ref="0-1"]', "Ada", 2)]
    assert out.status == "filled"


def test_a_native_select_uses_select_by_label():
    d = FakeDriver(["<html></html>"])
    fill_field(d, field(type="select", options=["Türkiye"]), "Türkiye", "/tmp/cv.pdf")
    assert d.selects == [('[data-cvai-ref="0-1"]', "Türkiye", 0)]


def test_a_combobox_opens_then_clicks_the_matching_option():
    # after the click that opens it, the collector reports the popup's options
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Türkiye", "frame": 0},
         {"ref": "0-10", "role": "option", "label_text": "Almanya", "frame": 0}],
    ])
    out = fill_field(d, field(type="combobox"), "Almanya", "/tmp/cv.pdf")
    assert d.clicks == ['[data-cvai-ref="0-1"]', '[data-cvai-ref="0-10"]']
    assert out.status == "filled"


def test_a_typeahead_types_before_picking():
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Ankara", "frame": 0}],
    ])
    fill_field(d, field(type="typeahead"), "Ankara", "/tmp/cv.pdf")
    assert d.fills == [('[data-cvai-ref="0-1"]', "Ankara", 0)]
    assert d.clicks == ['[data-cvai-ref="0-9"]']


def test_a_combobox_whose_option_never_appears_fails_loudly():
    d = FakeDriver(["<html></html>"], evaluations=[[]])
    out = fill_field(d, field(type="combobox"), "Mars", "/tmp/cv.pdf")
    assert out.status == "failed"
    assert "Mars" in out.reason


def test_an_empty_answer_is_skipped_not_failed():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="text"), "", "/tmp/cv.pdf")
    assert out.status == "skipped"
    assert d.fills == []


def test_a_file_field_uploads_the_cv_without_an_answer():
    d = FakeDriver(["<html></html>"])
    out = fill_field(d, field(type="file"), "", "/tmp/cv.pdf")
    assert d.files == [('[data-cvai-ref="0-1"]', "/tmp/cv.pdf", 0)]
    assert out.status == "filled"


def test_a_driver_error_becomes_a_failed_outcome_not_an_exception():
    class Boom(FakeDriver):
        def fill(self, selector, value, frame=0):
            raise RuntimeError("element is not visible")

    out = fill_field(Boom(["<html></html>"]), field(type="text"), "Ada", "/tmp/cv.pdf")
    assert out.status == "failed"
    assert "not visible" in out.reason
```

This test expects `FakeDriver` to record the frame on each action. Update `api/tests/fake_browser.py` so `fills`, `selects`, `clicks`, `checks` and `files` append the `frame` too — except `clicks`, which stays a list of selectors because no test needs its frame:

```python
    def fill(self, selector, value, frame=0):
        self.fills.append((selector, value, frame))

    def select_by_label(self, selector, label, frame=0):
        self.selects.append((selector, label, frame))

    def click(self, selector, frame=0):
        self.clicks.append(selector)

    def set_checked(self, selector, checked, frame=0):
        self.checks.append((selector, checked, frame))

    def set_files(self, selector, path, frame=0):
        self.files.append((selector, path, frame))
```

Three existing assertions read those recordings as 2-tuples and break. Fix them in this same commit:

- `api/tests/test_apply_submit.py:42` — `filled = dict(driver.fills)` raises
  `ValueError: dictionary update sequence element #0 has length 3`. Replace with
  `filled = {sel: val for sel, val, _frame in driver.fills}`.
- `api/tests/test_apply_submit.py:46,50,52` — `driver.selects[0][1]`,
  `driver.checks[0][1]`, `driver.files[0][1]` still index the value, which stays
  at position 1. These keep working; verify rather than edit.
- `api/tests/test_apply_assist.py:90` — same `dict(driver.fills)` problem. Task 7
  rewrites this test wholesale, so the minimal fix here is the same dict
  comprehension; do not invest in it further.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_fill_strategies.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.fill_strategies'`

- [ ] **Step 3: Add `FieldOutcome` to the schema**

In `api/app/schemas.py`, after `FieldAnswer`:

```python
class FieldOutcome(BaseModel):
    field_id: str
    label: str
    value: str = ""
    status: str                  # filled | skipped | failed
    reason: str = ""
```

- [ ] **Step 4: Implement the strategies**

Create `api/app/services/fill_strategies.py`:

```python
"""How to put a value into one control. Custom widgets are not <select>s: they
open a popup rendered somewhere else in the document, so picking an option means
clicking twice with a re-read in between."""
import logging

from app.schemas import FieldOutcome, FormField
from app.services.page_probe import PROBE_JS, RawControl

logger = logging.getLogger(__name__)

TRUTHY = ("yes", "true", "on", "evet", "1")


def _visible_options(driver, frame: int) -> list[RawControl]:
    """Re-read the page for popup options. They are usually rendered at the
    document root rather than inside the combobox, so scoping to the control
    would miss them."""
    raw = driver.evaluate(f"({PROBE_JS})({frame})", frame=frame) or []
    controls = [RawControl(**c) for c in raw]
    return [c for c in controls if c.role == "option"]


def _option_label(control: RawControl) -> str:
    return (control.label_text or control.aria_label
            or control.labelledby_text or "").strip()


def _pick_option(driver, field: FormField, value: str) -> None:
    for option in _visible_options(driver, field.frame):
        if _option_label(option).casefold() == value.casefold():
            driver.click(f'[data-cvai-ref="{option.ref}"]', frame=option.frame)
            return
    raise LookupError(f"no visible option matched {value!r}")


def fill_field(driver, field: FormField, value: str, pdf_path: str) -> FieldOutcome:
    def outcome(status: str, reason: str = "") -> FieldOutcome:
        return FieldOutcome(field_id=field.id, label=field.label, value=value,
                            status=status, reason=reason)

    if field.type == "file":
        try:
            driver.set_files(field.selector, pdf_path, frame=field.frame)
            return outcome("filled")
        except Exception as exc:
            return outcome("failed", str(exc))

    if not value:
        # The LLM answers "" when the CV does not carry the information; the
        # user fills those in themselves, so this is not a failure.
        return outcome("skipped", "no answer")

    try:
        if field.type in ("text", "textarea", "date"):
            driver.fill(field.selector, value, frame=field.frame)
        elif field.type == "select":
            driver.select_by_label(field.selector, value, frame=field.frame)
        elif field.type == "checkbox":
            driver.set_checked(field.selector, value.casefold() in TRUTHY,
                               frame=field.frame)
        elif field.type == "radio":
            if value not in field.options:
                return outcome("failed", f"{value!r} is not one of the choices")
            driver.click(field.option_selectors[field.options.index(value)],
                         frame=field.frame)
        elif field.type == "typeahead":
            driver.fill(field.selector, value, frame=field.frame)
            _pick_option(driver, field, value)
        elif field.type in ("combobox", "listbox"):
            driver.click(field.selector, frame=field.frame)
            _pick_option(driver, field, value)
        else:
            return outcome("failed", f"no strategy for type {field.type!r}")
    except Exception as exc:
        logger.warning("[fill] %s (%s): %s", field.id, field.type, exc)
        return outcome("failed", str(exc))
    return outcome("filled")
```

- [ ] **Step 5: Run the tests**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — including the existing tests you updated to 3-tuples.

- [ ] **Step 6: Commit**

```bash
git add api/app/services/fill_strategies.py api/app/schemas.py api/tests/test_fill_strategies.py api/tests/fake_browser.py api/tests
git commit -m "feat(api): per-role fill strategies with honest outcomes"
```

---

### Task 6: Verified fill

**Files:**
- Modify: `api/app/services/fill_strategies.py`
- Modify: `api/tests/test_fill_strategies.py`

**Interfaces:**
- Consumes: `fill_field` from Task 5, `probe_controls` from Task 2
- Produces: `fill_and_verify(driver, schema, answers, pdf_path) -> list[FieldOutcome]`

- [ ] **Step 1: Write the failing test**

Append to `api/tests/test_fill_strategies.py`:

```python
from app.schemas import FieldAnswer, FormSchema
from app.services.fill_strategies import fill_and_verify


def test_a_control_that_did_not_take_the_value_is_reported_as_failed():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    # the fill call reports success, but the verification probe shows the
    # control is still empty — a silently-ignored click looks exactly like this
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-1", "role": "textbox", "value": "", "frame": 0}],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="Ada")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "failed"
    assert "did not take" in outcomes[0].reason


def test_a_control_holding_the_value_stays_filled():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-1", "role": "textbox", "value": "Ada", "frame": 0}],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="Ada")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "filled"


def test_verification_never_downgrades_a_skipped_or_failed_field():
    schema = FormSchema(fields=[field(id="name", type="text", label="Full name")])
    d = FakeDriver(["<html></html>"], evaluations=[[]])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="name", value="")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "skipped"


def test_a_widget_we_cannot_read_back_is_left_as_filled():
    # comboboxes often keep their value in a hidden node; absence of evidence
    # must not be reported as evidence of failure
    schema = FormSchema(fields=[field(id="c", type="combobox", label="Country")])
    d = FakeDriver(["<html></html>"], evaluations=[
        [{"ref": "0-9", "role": "option", "label_text": "Türkiye", "frame": 0}],
        [],
    ])
    outcomes = fill_and_verify(d, schema, [FieldAnswer(field_id="c", value="Türkiye")],
                               "/tmp/cv.pdf")
    assert outcomes[0].status == "filled"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_fill_strategies.py -q`
Expected: FAIL — `ImportError: cannot import name 'fill_and_verify'`

- [ ] **Step 3: Implement**

Append to `api/app/services/fill_strategies.py`:

```python
def fill_and_verify(driver, schema, answers, pdf_path: str) -> list[FieldOutcome]:
    """Fill every field, then re-read the page and check what actually landed.
    A click that silently did nothing is indistinguishable from success until
    you look again, and that is the failure users reported as 'it said it
    worked'."""
    values = {a.field_id: a.value for a in answers}
    outcomes = [fill_field(driver, f, values.get(f.id, ""), pdf_path)
                for f in schema.fields]

    from app.services.page_probe import probe_controls   # local: avoid a cycle
    after = {c.ref: c for c in probe_controls(driver)}

    by_id = {f.id: f for f in schema.fields}
    for outcome in outcomes:
        if outcome.status != "filled":
            continue                       # skipped/failed are already honest
        field = by_id[outcome.field_id]
        if field.type not in ("text", "textarea", "date", "select"):
            continue                       # widgets hide their value elsewhere
        ref = field.selector.split('"')[1]
        control = after.get(ref)
        if control is None:
            continue                       # re-rendered away; cannot judge
        if outcome.value.casefold() not in (control.value or "").casefold():
            outcome.status = "failed"
            outcome.reason = "the control did not take the value"
    return outcomes
```

- [ ] **Step 4: Run the tests**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/services/fill_strategies.py api/tests/test_fill_strategies.py
git commit -m "feat(api): verify fills by re-reading the page"
```

---

### Task 7: Wire the engine into assisted mode

**Files:**
- Modify: `api/app/services/session.py` (`ThreadedBrowserSession.probe_and_fill`)
- Modify: `api/app/services/apply.py` (`assist_fill`)
- Modify: `api/tests/test_apply_assist.py`
- Modify: `api/tests/fake_session.py`

**Interfaces:**
- Consumes: `probe_controls`, `build_form`, `fill_and_verify`
- Produces: `assist_fill` returns `{"status": "filled", "filled": [...], "unfilled": [...], "field_count": int, "screenshot": str}` or `{"status": "no_form", "reason": str}`

- [ ] **Step 1: Teach the session fake the new commands**

Every assisted test drives the flow through `FakeSession`, so it must speak the
new protocol before any test can. Rewrite `api/tests/fake_session.py`:

```python
"""Inline BrowserSession double: wraps a FakeDriver, no thread."""
from app.services.fill_strategies import fill_and_verify
from app.services.page_probe import probe_controls


class FakeSession:
    def __init__(self, driver, url: str = "https://jobs.example.com/1"):
        self._driver = driver
        self._url = url
        self.closed = False

    def url(self) -> str:
        return self._url

    def snapshot(self) -> str:
        return self._driver.content()

    def probe(self) -> list:
        return probe_controls(self._driver)

    def fill_verified(self, schema, answers, pdf_path: str) -> list:
        return fill_and_verify(self._driver, schema, answers, pdf_path)

    def screenshot(self) -> bytes:
        return self._driver.screenshot()

    def close(self) -> None:
        self.closed = True
        self._driver.close()
```

`fill_form` and the `_fill_form` import are gone: nothing calls them in assisted
mode any more, and the auto flow calls `_fill_form` directly.

- [ ] **Step 2: Convert the existing assisted tests to inventories**

These four tests feed HTML to `extract_form` and will find zero fields once the
engine reads roles instead. In `api/tests/test_apply_assist.py`, add inventories
beside the existing HTML constants:

```python
# What the collector reports for FORM_HTML. The second entry is the page as it
# looks AFTER filling, which is what the verification probe reads.
FORM_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "textarea", "role": "textbox",
     "name": "motivation", "label_text": "Motivation"},
    {"ref": "0-2", "frame": 0, "tag": "input", "type": "email", "role": "textbox",
     "name": "email", "label_text": "Email"},
]
FORM_INVENTORY_AFTER = [
    {**FORM_INVENTORY[0], "value": "I love APIs."},
    {**FORM_INVENTORY[1], "value": ""},
]

LINKS_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "input", "role": "textbox",
     "name": "linkedin", "label_text": "LinkedIn URL"},
    {"ref": "0-2", "frame": 0, "tag": "input", "role": "textbox",
     "name": "github", "label_text": "GitHub URL"},
    {"ref": "0-3", "frame": 0, "tag": "input", "role": "textbox",
     "name": "portfolio", "label_text": "Portfolio URL"},
]
LINKS_INVENTORY_AFTER = [
    {**LINKS_INVENTORY[0], "value": "https://linkedin.com/in/ada"},
    {**LINKS_INVENTORY[1], "value": "https://github.com/ada"},
    {**LINKS_INVENTORY[2], "value": "https://ada.dev"},
]
```

Then change the four `FakeDriver(...)` constructions:

```python
# test_assist_fill_fills_and_charges_one_credit
_use_session(FakeDriver([FORM_HTML], evaluations=[FORM_INVENTORY, FORM_INVENTORY_AFTER]))

# test_assist_fill_answers_profile_link_fields_from_the_cv
driver = FakeDriver([LINKS_HTML], evaluations=[LINKS_INVENTORY, LINKS_INVENTORY_AFTER])

# test_assist_fill_survives_a_locked_temp_pdf
_use_session(FakeDriver([FORM_HTML], evaluations=[FORM_INVENTORY, FORM_INVENTORY_AFTER]))

# test_assist_fill_no_form_costs_no_credit
_use_session(FakeDriver([NO_FORM_HTML], evaluations=[[]]))
```

and in the profile-links test, swap the XPath assertions for ref selectors:

```python
    filled = {sel: val for sel, val, _frame in driver.fills}
    assert filled['[data-cvai-ref="0-1"]'] == "https://linkedin.com/in/ada"
    assert filled['[data-cvai-ref="0-2"]'] == "https://github.com/ada"
    assert filled['[data-cvai-ref="0-3"]'] == "https://ada.dev"
```

The field ids the LLM answers against (`motivation`, `email`, `linkedin`,
`github`, `portfolio`) are unchanged, because `build_form` derives an id from
`control.name` exactly as `extract_form` did.

- [ ] **Step 3: Write the failing tests for the new behaviour**

Add to `api/tests/test_apply_assist.py`:

```python
COUNTRY_INVENTORY = [
    {"ref": "0-1", "frame": 0, "tag": "input", "role": "textbox",
     "name": "motivation", "label_text": "Motivation"},
    {"ref": "0-2", "frame": 0, "tag": "div", "role": "combobox",
     "name": "country", "label_text": "Country"},
]


def test_assist_fill_reports_the_fields_it_could_not_fill(client, auth_headers):
    """A partial fill is normal with custom widgets, and staying silent about it
    is what made the tool claim success it had not earned."""
    # the combobox opens but its popup never offers "Türkiye", so the option
    # lookup finds nothing and the field is reported back to the user
    driver = FakeDriver([FORM_HTML], evaluations=[
        COUNTRY_INVENTORY,      # discovery
        [],                     # the popup after clicking the combobox
        COUNTRY_INVENTORY,      # verification
    ])
    _use_session(driver)
    override_llm([json.dumps({"answers": [
        {"field_id": "motivation", "value": "I love APIs."},
        {"field_id": "country", "value": "Türkiye"},
    ]})])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "filled"
    assert [f["label"] for f in body["unfilled"]] == ["Country"]


def test_assist_fill_says_why_it_found_no_form(client, auth_headers):
    _use_session(FakeDriver([NO_FORM_HTML], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    body = r.json()
    assert body["status"] == "no_form"
    assert body["reason"] == "no_controls"


def test_assist_fill_names_a_login_wall_as_the_reason(client, auth_headers):
    login_html = "<html><body><form><input type='password'></form></body></html>"
    _use_session(FakeDriver([login_html], evaluations=[[]]))
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.json()["reason"] == "login_wall"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_apply_assist.py -q`
Expected: FAIL — `AttributeError: 'FakeSession' object has no attribute 'probe'`
is raised from `assist_fill`, which still calls `extract_form`.

- [ ] **Step 5: Give the session probe/fill commands and remember its URL**

In `api/app/services/session.py`, add to the `BrowserSession` Protocol:

```python
    def url(self) -> str: ...
    def probe(self) -> list: ...
    def fill_verified(self, schema, answers, pdf_path: str) -> list: ...
```

and to `ThreadedBrowserSession` — store the URL in `__init__` (`self._url = url`,
alongside the existing thread setup) and add:

```python
    def url(self) -> str:
        # the URL the session was opened on; Task 9 uses it to look up a platform
        return self._url

    def probe(self) -> list:
        from app.services.page_probe import probe_controls
        return self._call(probe_controls)

    def fill_verified(self, schema, answers, pdf_path: str) -> list:
        from app.services.fill_strategies import fill_and_verify
        return self._call(lambda d: fill_and_verify(d, schema, answers, pdf_path))
```

`probe` and `fill_verified` must go through `_call`, because Playwright objects
are bound to the session's own thread. Drop `fill_form`, which no longer has a
caller.

- [ ] **Step 6: Rewrite `assist_fill`**

In `api/app/services/apply.py`, replace the body of `assist_fill` down to the `session.fill_form(...)` call:

```python
def _no_form_reason(html: str, controls: list) -> str:
    if detect_captcha(html):
        return "captcha"
    if detect_login(html):
        return "login_wall"
    return "no_controls" if not controls else "unsupported"


def assist_fill(session, cv: CVData, language: str,
                llm: LLMClient, user_id: str) -> dict:
    """Fill the CURRENT live page of an assisted session, reading it by role."""
    controls = session.probe()
    schema = build_form(controls)
    if not schema.fields:
        html = session.snapshot()
        reason = _no_form_reason(html, controls)
        logger.warning("[assist] no_form reason=%s controls=%d",
                       reason, len(controls))
        return {"status": "no_form", "reason": reason}

    enforce_limit(usage_store, user_id, get_settings().daily_ai_limit)
    job_text = _job_text(session.snapshot())
    user_payload = AssistIn(cv=cv, job_text=job_text,
                            form=schema.fields).model_dump_json()
    out = llm.chat_json(MODEL_SMART, ASSIST_SYSTEM.format(language=language),
                        user_payload, AnswersOut)

    pdf_bytes = ats.render_pdf(cv, language)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    try:
        outcomes = session.fill_verified(schema, out.answers, tmp.name)
        shot = base64.b64encode(session.screenshot()).decode()
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("temp PDF still held by the browser, leaving it "
                           "to the OS temp dir: %s (%s)", tmp.name, exc)

    filled = [{"label": o.label, "value": o.value}
              for o in outcomes if o.status == "filled"]
    unfilled = [{"label": o.label, "reason": o.reason}
                for o in outcomes if o.status == "failed"]
    return {"status": "filled", "filled": filled, "unfilled": unfilled,
            "field_count": len(schema.fields), "screenshot": shot}
```

Add `from app.services.form_build import build_form` to the imports. Leave `prepare_application` and `submit_application` untouched.

- [ ] **Step 7: Run the whole suite**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/app/services/session.py api/app/services/apply.py api/tests
git commit -m "feat(api): assisted fill reads the page by role and reports what it missed"
```

---

### Task 8: Show unfilled fields and no-form reasons in the UI

**Files:**
- Modify: `web/src/types/api.ts`
- Modify: `web/src/components/apply/AssistScreen.tsx`
- Modify: `web/src/components/apply/__tests__/AssistScreen.test.tsx`
- Modify: `web/src/messages/tr.json`, `web/src/messages/en.json`
- Modify: `web/src/messages/__tests__/parity.test.ts`

**Interfaces:**
- Consumes: the `assist_fill` response shape from Task 7
- Produces: no exported API; UI only

- [ ] **Step 1: Write the failing test**

Add to `web/src/components/apply/__tests__/AssistScreen.test.tsx`:

```tsx
it('names the fields the user still has to fill in by hand', () => {
  render(<AssistScreen busy={false} onFill={() => {}} onFinish={() => {}}
    result={{ status: 'filled', field_count: 3, screenshot: '', 
      filled: [{ label: 'Full name', value: 'Ada' }],
      unfilled: [{ label: 'Country', reason: 'no visible option matched' }] }} />)
  expect(screen.getByText(/Country/)).toBeInTheDocument()
})

it('explains why no form was found instead of just saying none', () => {
  render(<AssistScreen busy={false} onFill={() => {}} onFinish={() => {}}
    result={{ status: 'no_form', reason: 'login_wall' }} />)
  expect(screen.getByText(/giriş/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/components/apply/__tests__/AssistScreen.test.tsx`
Expected: FAIL — the unfilled list is not rendered.

- [ ] **Step 3: Extend the types**

In `web/src/types/api.ts`, extend `AssistFillResult`:

```ts
  unfilled?: { label: string; reason: string }[]
  reason?: 'login_wall' | 'captcha' | 'no_controls' | 'unsupported'
```

- [ ] **Step 4: Add the messages**

In `web/src/messages/tr.json` under `optimize`:

```json
    "assistUnfilled": "Şu alanları dolduramadım, elle tamamlaman gerekiyor:",
    "assistReasonLoginWall": "Bu sayfa giriş istiyor. Tarayıcıda giriş yapıp tekrar dene.",
    "assistReasonCaptcha": "Bu sayfada bir doğrulama (captcha) var. Onu geçtikten sonra tekrar dene.",
    "assistReasonNoControls": "Bu sayfada doldurulacak bir alan bulamadım. Başvuru formuna ilerleyip tekrar dene.",
    "assistReasonUnsupported": "Bu sayfanın yapısını okuyamadım."
```

and in `en.json`:

```json
    "assistUnfilled": "I could not fill these — please complete them by hand:",
    "assistReasonLoginWall": "This page wants you to sign in. Log in in the browser and try again.",
    "assistReasonCaptcha": "This page has a captcha. Clear it and try again.",
    "assistReasonNoControls": "I found no fillable fields here. Move to the application form and try again.",
    "assistReasonUnsupported": "I could not read this page's structure."
```

Add `assistUnfilled` and the four reason keys to the key list in `web/src/messages/__tests__/parity.test.ts` if that test enumerates them; the identical-keys test covers them automatically.

- [ ] **Step 5: Render them**

In `web/src/components/apply/AssistScreen.tsx`, replace the `no_form` block:

```tsx
      {result?.status === 'no_form' && (
        <p className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning">
          {t(result.reason === 'login_wall' ? 'assistReasonLoginWall'
            : result.reason === 'captcha' ? 'assistReasonCaptcha'
            : result.reason === 'unsupported' ? 'assistReasonUnsupported'
            : 'assistReasonNoControls')}
        </p>
      )}
```

and inside the `filled` section, after the filled list:

```tsx
          {result.unfilled && result.unfilled.length > 0 && (
            <div className="rounded-lg bg-warning/10 px-4 py-3 text-sm text-warning">
              <p>{t('assistUnfilled')}</p>
              <ul className="mt-1 flex flex-col gap-1">
                {result.unfilled.map((f, i) => <li key={i}>{f.label}</li>)}
              </ul>
            </div>
          )}
```

- [ ] **Step 6: Run the web checks**

Run in `web/`: `npm test`, then `npx tsc --noEmit`, then `npm run build`.
Expected: all pass; `/optimize` still listed in the build output.

- [ ] **Step 7: Commit**

```bash
git add web/src/types/api.ts web/src/components/apply web/src/messages
git commit -m "feat(web): show unfilled fields and explain why no form was found"
```

---

### Task 9: Platform registry seam and measurement

**Files:**
- Create: `api/app/services/platforms/__init__.py`
- Create: `api/tests/test_platforms.py`
- Create: `api/tools/measure_fixtures.py`
- Modify: `api/app/services/form_build.py`

**Interfaces:**
- Consumes: `build_form` from Task 4
- Produces: `platform_for(url: str) -> Platform | None`, `Platform(name, hosts, scope_landmark)`, and `build_form(controls, platform=None)`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_platforms.py`:

```python
from app.services.form_build import build_form
from app.services.page_probe import RawControl
from app.services.platforms import Platform, platform_for


def test_an_unknown_host_has_no_platform():
    assert platform_for("https://jobs.example.com/apply") is None


def test_a_platform_can_pin_the_scope_that_generic_rules_would_miss():
    # generic scoping would pick the dialog; this platform says the real form
    # is the main region
    controls = [
        RawControl(ref="0-1", role="textbox", aria_label="Cookie consent",
                   landmark="dialog", visible=True),
        RawControl(ref="0-2", role="textbox", aria_label="Full name",
                   landmark="main", visible=True),
    ]
    assert [f.label for f in build_form(controls).fields] == ["Cookie consent"]
    pinned = Platform(name="test", hosts=("t.example",), scope_landmark="main")
    assert [f.label for f in build_form(controls, pinned).fields] == ["Full name"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest tests/test_platforms.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.platforms'`

- [ ] **Step 3: Implement the registry**

Create `api/app/services/platforms/__init__.py`:

```python
"""Per-portal overrides. Deliberately empty: an entry is added only when a
captured fixture shows the generic role-based rules failing on that portal.
Speculative entries are how this becomes four modules nobody can retire."""
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Platform:
    name: str
    hosts: tuple[str, ...]
    scope_landmark: str | None = None   # pin the scope generic rules get wrong


REGISTRY: tuple[Platform, ...] = ()


def platform_for(url: str) -> Platform | None:
    host = (urlparse(url).hostname or "").lower()
    for platform in REGISTRY:
        if any(host == h or host.endswith("." + h) for h in platform.hosts):
            return platform
    return None
```

In `api/app/services/form_build.py`, change the signature and the scope step:

```python
def build_form(controls: list[RawControl], platform=None) -> FormSchema:
```

and inside `_in_scope`, accept the pin:

```python
def _in_scope(controls: list[RawControl], platform=None) -> list[RawControl]:
    usable = [c for c in controls
              if c.visible and not c.disabled
              and c.role != "password"
              and c.landmark not in CHROME_LANDMARKS]
    scopes = (platform.scope_landmark,) if platform and platform.scope_landmark else SCOPES
    for scope in scopes:
        scoped = [c for c in usable if c.landmark == scope]
        if scoped:
            return scoped
    return usable
```

Update the call inside `build_form` to `_in_scope(controls, platform)`.

- [ ] **Step 4: Consult the registry from the live path**

Without this the registry is dead code. In `api/app/services/apply.py`, inside
`assist_fill`, replace the `build_form(controls)` call:

```python
    controls = session.probe()
    schema = build_form(controls, platform_for(session.url()))
```

and add `from app.services.platforms import platform_for` to the imports.

Add the test that proves the wiring, in `api/tests/test_apply_assist.py`:

```python
def test_a_registered_platform_overrides_the_generic_scope(client, auth_headers,
                                                           monkeypatch):
    import app.services.platforms as platforms_mod
    monkeypatch.setattr(platforms_mod, "REGISTRY", (platforms_mod.Platform(
        name="test", hosts=("jobs.example.com",), scope_landmark="main"),))
    # generic rules would scope to the dialog; the platform pins main
    inventory = [
        {"ref": "0-1", "frame": 0, "role": "textbox", "name": "consent",
         "label_text": "Cookie consent", "landmark": "dialog"},
        {"ref": "0-2", "frame": 0, "role": "textbox", "name": "motivation",
         "label_text": "Motivation", "landmark": "main"},
    ]
    _use_session(FakeDriver([FORM_HTML], evaluations=[inventory, inventory]))
    override_llm([json.dumps({"answers": [
        {"field_id": "motivation", "value": "I love APIs."}]})])
    sid = _start(client, auth_headers)
    r = client.post("/apply/assist/fill", headers=auth_headers,
                    json={"session_id": sid, "cv": json.loads(SAMPLE_CV_JSON),
                          "language": "en"})
    assert r.json()["field_count"] == 1
```

`FakeSession.url()` returns `https://jobs.example.com/1`, which is why the host
in the registry entry matches.

- [ ] **Step 5: Write the measurement script**

Create `api/tools/measure_fixtures.py`:

```python
"""How well does the generic engine do on each captured portal? This is the
number that decides whether a platform needs an adapter."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.form_build import build_form                # noqa: E402
from app.services.page_probe import RawControl                # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "inventories"

for path in sorted(FIXTURES.glob("*.json")):
    controls = [RawControl(**c) for c in json.loads(path.read_text(encoding="utf-8"))]
    form = build_form(controls)
    named = sum(1 for f in form.fields if f.label)
    print(f"{path.stem:<28} controls={len(controls):>3} "
          f"fields={len(form.fields):>3} named={named:>3}")
    for f in form.fields:
        print(f"    {f.type:<10} {f.label[:60]}")
```

- [ ] **Step 6: Run it and report**

Run: `cd api && ./.venv/Scripts/python.exe tools/measure_fixtures.py`

Report the table to the user. Any portal whose fields are missing or unnamed is a candidate for a `Platform` entry — add entries only for those, each with a test in `test_platforms.py` built from that portal's fixture.

- [ ] **Step 7: Run the whole suite**

Run: `cd api && ./.venv/Scripts/python.exe -m pytest -q` and, in `web/`, `npm test`.
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add api/app/services/platforms api/app/services/form_build.py api/app/services/apply.py api/tools/measure_fixtures.py api/tests
git commit -m "feat(api): platform override seam and fixture measurement"
```

---

## Done when

- Assisted apply discovers fields on a real Workday posting captured in Task 3, which today yields zero.
- A div-combobox is filled by clicking through its popup, and a fill that silently fails is reported to the user as unfilled rather than as success.
- `/apply/prepare` and `/apply/submit` behave exactly as before.
- `api`: full suite green. `web`: `npm test`, `npx tsc --noEmit`, `npm run build` all green.
