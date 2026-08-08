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
