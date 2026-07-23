"""Records interactions; serves queued HTML snapshots."""


class FakeDriver:
    def __init__(self, pages: list[str]):
        self._pages = list(pages)   # served by successive content() calls
        self.gotos: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.selects: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.checks: list[tuple[str, bool]] = []
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

    def set_checked(self, xpath, checked):
        self.checks.append((xpath, checked))

    def set_files(self, xpath, path):
        self.files.append((xpath, path))

    def wait(self, ms):
        pass

    def screenshot(self):
        return b"\x89PNG-fake"

    def close(self):
        self.closed = True
