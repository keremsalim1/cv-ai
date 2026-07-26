"""Records interactions; serves queued HTML snapshots."""


class FakeDriver:
    def __init__(self, pages: list[str], evaluations: list | None = None):
        self._pages = list(pages)   # served by successive content() calls
        self._evaluations = list(evaluations or [])
        self.gotos: list[str] = []
        self.fills: list[tuple[str, str, int]] = []
        self.selects: list[tuple[str, str, int]] = []
        self.clicks: list[str] = []
        self.checks: list[tuple[str, bool, int]] = []
        self.files: list[tuple[str, str, int]] = []
        self.evaluated: list[tuple[str, int]] = []
        self.frames = 1
        self.closed = False

    def goto(self, url):
        self.gotos.append(url)

    def content(self):
        return self._pages.pop(0) if len(self._pages) > 1 else self._pages[0]

    def evaluate(self, script, frame=0):
        self.evaluated.append((script, frame))
        # queued results are consumed in order; the last one repeats, so a test
        # that probes twice without caring about the second call still works
        if not self._evaluations:
            return []
        return (self._evaluations.pop(0) if len(self._evaluations) > 1
                else self._evaluations[0])

    def frame_count(self):
        return self.frames

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

    def wait(self, ms):
        pass

    def screenshot(self):
        return b"\x89PNG-fake"

    def close(self):
        self.closed = True
