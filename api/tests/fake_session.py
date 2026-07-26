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
