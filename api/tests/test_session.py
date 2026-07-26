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


def test_start_replaces_the_users_previous_session():
    """One live browser per user: their profile dir can only be opened once, and
    a stale session from a refreshed tab must never lock them out."""
    mgr = SessionManager(max_sessions=4)
    first = _FakeSession(FakeDriver(["<html>a</html>"]))
    sid1 = mgr.start(lambda url: first, "https://x.com", "user-1")
    sid2 = mgr.start(lambda url: _FakeSession(FakeDriver(["<html>b</html>"])),
                     "https://y.com", "user-1")

    assert first.closed is True
    assert sid1 != sid2
    assert mgr.live_count() == 1
    with pytest.raises(HTTPException) as exc:
        mgr.get(sid1, "user-1")
    assert exc.value.status_code == 404


def test_start_refuses_to_launch_past_the_server_capacity():
    """Each Chromium costs hundreds of MB; the box must not be talked into
    launching an unbounded number of them."""
    mgr = SessionManager(max_sessions=2)
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>a</html>"])), "https://x.com", "user-1")
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>b</html>"])), "https://x.com", "user-2")

    overflow = _FakeSession(FakeDriver(["<html>c</html>"]))
    with pytest.raises(HTTPException) as exc:
        mgr.start(lambda url: overflow, "https://x.com", "user-3")
    assert exc.value.status_code == 503
    assert exc.value.detail == {"code": "TOO_MANY_SESSIONS"}
    # rejected before the browser was ever launched
    assert overflow.closed is False
    assert mgr.live_count() == 2


def test_capacity_frees_up_when_a_session_closes():
    mgr = SessionManager(max_sessions=1)
    sid = mgr.start(lambda url: _FakeSession(FakeDriver(["<html>a</html>"])),
                    "https://x.com", "user-1")
    mgr.close(sid, "user-1")
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>b</html>"])),
              "https://x.com", "user-2")
    assert mgr.live_count() == 1


def test_manager_gc_closes_idle_sessions():
    mgr = SessionManager()
    session = _FakeSession(FakeDriver(["<html>x</html>"]))
    sid = mgr.start(lambda url: session, "https://x.com", "user-1")
    # force the entry to look old, then trigger lazy GC via another start
    mgr._sessions[sid].last_used -= 10_000
    # a DIFFERENT user, so this proves the idle GC closed it rather than the
    # one-session-per-user rule
    mgr.start(lambda url: _FakeSession(FakeDriver(["<html>y</html>"])), "https://y.com", "user-2")
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
