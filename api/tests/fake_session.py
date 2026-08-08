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
