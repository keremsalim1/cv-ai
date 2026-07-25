import pytest
from fastapi import HTTPException

from app.services.session import ThreadedBrowserSession, SessionManager
from tests.fake_browser import FakeDriver


def _factory(pages):
    return lambda headed: FakeDriver(list(pages))


def test_threaded_session_round_trips_on_its_own_thread():
    driver = FakeDriver(["<html><body><h1>Hi</h1></body></html>"])
    session = ThreadedBrowserSession(lambda headed: driver, "https://x.com/1")
    try:
        assert "Hi" in session.snapshot()
        assert session.screenshot() == b"\x89PNG-fake"
        assert driver.gotos == ["https://x.com/1"]
    finally:
        session.close()
    assert driver.closed is True


def test_manager_start_get_close_with_ownership():
    mgr = SessionManager()
    fake = FakeDriver(["<html><body>ok</body></html>"])
    session = _FakeSession(fake)
    sid = mgr.start(lambda url: session, "https://x.com", "user-1")
    assert mgr.get(sid, "user-1") is session
    with pytest.raises(HTTPException) as exc:
        mgr.get(sid, "user-2")
    assert exc.value.status_code == 403
    mgr.close(sid, "user-1")
    with pytest.raises(HTTPException) as exc2:
        mgr.get(sid, "user-1")
    assert exc2.value.status_code == 404


def test_manager_gc_closes_idle_sessions():
    mgr = SessionManager()
    session = _FakeSession(FakeDriver(["<html>x</html>"]))
    sid = mgr.start(lambda url: session, "https://x.com", "user-1")
    # force the entry to look old, then trigger lazy GC via another start
    mgr._sessions[sid].last_used -= 10_000
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>y</html>"])), "https://y.com", "user-1")
    assert session.closed is True


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver
        self.closed = False

    def snapshot(self):
        return self._driver.content()

    def fill_form(self, schema, answers, pdf_path):
        pass

    def screenshot(self):
        return self._driver.screenshot()

    def close(self):
        self.closed = True
