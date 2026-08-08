"""Thin Playwright wrapper. Everything above this file talks to the
BrowserDriver protocol so tests can inject a fake."""
import hashlib
from pathlib import Path
from typing import Callable, Protocol

from fastapi import Depends

from app.auth import get_current_user
from app.config import get_settings


class BrowserDriver(Protocol):
    def goto(self, url: str) -> None: ...
    def content(self) -> str: ...
    def evaluate(self, script: str, frame: int = 0): ...
    def frame_count(self) -> int: ...
    def fill(self, selector: str, value: str, frame: int = 0) -> None: ...
    def select_by_label(self, selector: str, label: str, frame: int = 0) -> None: ...
    def click(self, selector: str, frame: int = 0) -> None: ...
    def set_checked(self, selector: str, checked: bool, frame: int = 0) -> None: ...
    def set_files(self, selector: str, path: str, frame: int = 0) -> None: ...
    def wait(self, ms: int) -> None: ...
    def screenshot(self) -> bytes: ...
    def close(self) -> None: ...


def profile_dir_for(user_id: str) -> str:
    """A Chromium profile holds the user's job-site session cookies, so one
    shared directory would hand every user the previous user's LinkedIn login.
    Hashing the id keeps the path stable (their logins survive between
    applications) and safe (an id can never escape the base dir)."""
    digest = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    base = get_settings().browser_profile_dir
    return str(Path(base) / f"u-{digest}")


class PlaywrightDriver:
    def __init__(self, headed: bool, profile_dir: str):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            profile_dir,
            headless=not headed,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(15_000)

    @property
    def _live(self):
        """In assisted mode the user drives this browser by hand: portals open
        the application in a new tab, and the tab we started on is abandoned or
        closed. Resolve the page per call, newest first, so we always act on
        what the user is actually looking at."""
        for page in reversed(self._context.pages):
            if page.is_closed():
                continue
            if page is not self._page:
                page.set_default_timeout(15_000)
                self._page = page
            return page
        return self._page      # nothing left alive; let the caller see the error

    def goto(self, url: str) -> None:
        page = self._live
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # let client-side apps (Greenhouse, Lever) render the form
        page.wait_for_timeout(2_000)

    def content(self) -> str:
        return self._live.content()

    def _loc(self, selector: str, frame: int):
        # page.frames[0] IS the main frame, so one path serves both cases.
        # Playwright only auto-detects "//" and ".." as XPath, but lxml's
        # getpath() yields "/html/body/..." with a single slash, which would be
        # parsed as CSS. Prefix explicitly so the auto flow's paths keep working
        # alongside the probe's "[data-cvai-ref=...]" CSS refs.
        target = self._live.frames[frame]
        if selector.startswith("/") or selector.startswith(".."):
            return target.locator(f"xpath={selector}")
        return target.locator(selector)

    def evaluate(self, script: str, frame: int = 0):
        return self._live.frames[frame].evaluate(script)

    def frame_count(self) -> int:
        return len(self._live.frames)

    def fill(self, selector: str, value: str, frame: int = 0) -> None:
        self._loc(selector, frame).fill(value)

    def select_by_label(self, selector: str, label: str, frame: int = 0) -> None:
        self._loc(selector, frame).select_option(label=label)

    def click(self, selector: str, frame: int = 0) -> None:
        self._loc(selector, frame).click()

    def set_checked(self, selector: str, checked: bool, frame: int = 0) -> None:
        # idempotent: no-op if the box already matches, so we never toggle a
        # pre-checked control into the wrong state.
        self._loc(selector, frame).set_checked(checked)

    def set_files(self, selector: str, path: str, frame: int = 0) -> None:
        self._loc(selector, frame).set_input_files(path)

    def wait(self, ms: int) -> None:
        self._live.wait_for_timeout(ms)

    def screenshot(self) -> bytes:
        return self._live.screenshot(full_page=False)

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._pw.stop()


def driver_factory_for(user_id: str) -> Callable[[bool], BrowserDriver]:
    """Bind the profile once, here at the composition root, so no service below
    has to remember to keep users apart."""
    profile = profile_dir_for(user_id)
    return lambda headed: PlaywrightDriver(headed, profile)


def get_driver_factory(
    user_id: str = Depends(get_current_user),
) -> Callable[[bool], BrowserDriver]:
    return driver_factory_for(user_id)
