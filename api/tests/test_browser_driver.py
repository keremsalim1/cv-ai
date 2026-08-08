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


OPEN_TAB = ("() => { const w = window.open('about:blank');"
            " w.document.write('<input id=\"applicant\">'); }")


def test_the_driver_reads_the_tab_the_user_moved_to(driver):
    # Portals open the application in a new tab. The form the user is looking
    # at is there, not on the page the session was started on.
    driver.goto("data:text/html," + OUTER)
    driver.evaluate(OPEN_TAB)
    driver.wait(500)
    assert driver.evaluate("() => !!document.getElementById('applicant')") is True


def test_closing_the_original_tab_does_not_take_the_session_down(driver):
    driver.goto("data:text/html," + OUTER)
    driver.evaluate(OPEN_TAB)
    driver.wait(500)
    # models the user closing the tab we started on, an actor outside the driver
    driver._context.pages[0].close()
    assert driver.content()
    assert driver.evaluate("() => !!document.getElementById('applicant')") is True


def test_a_single_slash_absolute_path_is_still_xpath(driver):
    # lxml's getpath() produces exactly this shape, and the auto flow still
    # feeds it to the driver; Playwright would read it as CSS on its own.
    driver.goto("data:text/html," + OUTER)
    driver.fill("/html/body/input", "via absolute path")
    assert driver.evaluate(
        "() => document.getElementById('top').value") == "via absolute path"
