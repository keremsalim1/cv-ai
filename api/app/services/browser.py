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
    def fill(self, xpath: str, value: str) -> None: ...
    def select_by_label(self, xpath: str, label: str) -> None: ...
    def click(self, xpath: str) -> None: ...
    def set_checked(self, xpath: str, checked: bool) -> None: ...
    def set_files(self, xpath: str, path: str) -> None: ...
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

    def set_checked(self, xpath: str, checked: bool) -> None:
        # idempotent: no-op if the box already matches, so we never toggle a
        # pre-checked control into the wrong state.
        self._page.locator(f"xpath={xpath}").set_checked(checked)

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


def driver_factory_for(user_id: str) -> Callable[[bool], BrowserDriver]:
    """Bind the profile once, here at the composition root, so no service below
    has to remember to keep users apart."""
    profile = profile_dir_for(user_id)
    return lambda headed: PlaywrightDriver(headed, profile)


def get_driver_factory(
    user_id: str = Depends(get_current_user),
) -> Callable[[bool], BrowserDriver]:
    return driver_factory_for(user_id)
