"""Persistent headed browser sessions for assisted apply. Each session owns a
BrowserDriver on a dedicated thread, because sync Playwright objects are not
thread-safe and FastAPI's threadpool has no thread affinity."""
import queue
import threading
import time
import uuid
from typing import Callable, Protocol

from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.config import get_settings
from app.services.browser import BrowserDriver, driver_factory_for

SESSION_IDLE_TTL = 900  # seconds a session may sit idle before it is GC'd


class BrowserSession(Protocol):
    def url(self) -> str: ...
    def snapshot(self) -> str: ...
    def probe(self) -> list: ...
    def fill_verified(self, schema, answers, pdf_path: str) -> list: ...
    def screenshot(self) -> bytes: ...
    def close(self) -> None: ...


class ThreadedBrowserSession:
    """Owns a BrowserDriver on a dedicated thread; every command runs there."""

    def __init__(self, driver_factory: Callable[[bool], BrowserDriver], url: str):
        self._url = url
        self._in: "queue.Queue" = queue.Queue()
        self._ready: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, args=(driver_factory, url), daemon=True)
        self._thread.start()
        err = self._ready.get()      # block until the browser is up (or failed)
        if err is not None:
            raise err

    def _run(self, driver_factory, url):
        try:
            driver = driver_factory(True)   # headed
            driver.goto(url)
        except Exception as exc:            # startup failure -> surface to caller
            self._ready.put(exc)
            return
        self._ready.put(None)
        while True:
            fn, out = self._in.get()
            if fn is None:                  # close sentinel
                try:
                    driver.close()
                finally:
                    out.put((None, None))
                return
            try:
                out.put((fn(driver), None))
            except Exception as exc:        # relay to the calling thread
                out.put((None, exc))

    def _call(self, fn):
        out: "queue.Queue" = queue.Queue()
        self._in.put((fn, out))
        result, err = out.get()
        if err is not None:
            raise err
        return result

    def url(self) -> str:
        # the URL the session was opened on; the platform registry keys off it
        return self._url

    def snapshot(self) -> str:
        return self._call(lambda d: d.content())

    def probe(self) -> list:
        from app.services.page_probe import probe_controls
        return self._call(probe_controls)

    def fill_verified(self, schema, answers, pdf_path: str) -> list:
        from app.services.fill_strategies import fill_and_verify
        return self._call(lambda d: fill_and_verify(d, schema, answers, pdf_path))

    def screenshot(self) -> bytes:
        return self._call(lambda d: d.screenshot())

    def close(self) -> None:
        out: "queue.Queue" = queue.Queue()
        self._in.put((None, out))
        out.get()
        self._thread.join(timeout=10)


class _Entry:
    def __init__(self, session: BrowserSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.last_used = time.monotonic()


class SessionManager:
    def __init__(self, max_sessions: int | None = None):
        self._sessions: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._max_sessions = max_sessions

    @property
    def max_sessions(self) -> int:
        if self._max_sessions is not None:
            return self._max_sessions
        return get_settings().max_browser_sessions

    def live_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _take_user_sessions(self, user_id: str) -> list[_Entry]:
        with self._lock:
            return [self._sessions.pop(sid) for sid, entry
                    in list(self._sessions.items()) if entry.user_id == user_id]

    def start(self, factory: Callable[[str], BrowserSession], url: str, user_id: str) -> str:
        self._gc()
        # One live browser per user. Their profile directory can only be opened
        # by one Chromium at a time, and a session orphaned by a refreshed tab
        # would otherwise lock them out until the idle TTL expired.
        for entry in self._take_user_sessions(user_id):
            try:
                entry.session.close()
            except Exception:
                pass

        # Refuse before launching, not after: a browser we then throw away has
        # already cost the memory we are trying to protect.
        with self._lock:
            at_capacity = len(self._sessions) >= self.max_sessions
        if at_capacity:
            raise HTTPException(status_code=503,
                                detail={"code": "TOO_MANY_SESSIONS"})

        session = factory(url)
        sid = uuid.uuid4().hex
        with self._lock:
            self._sessions[sid] = _Entry(session, user_id)
        return sid

    def get(self, session_id: str, user_id: str) -> BrowserSession:
        self._gc()
        with self._lock:
            entry = self._sessions.get(session_id)
        if entry is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND"})
        if entry.user_id != user_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
        entry.last_used = time.monotonic()
        return entry.session

    def close(self, session_id: str, user_id: str) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            if entry.user_id != user_id:
                raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
            del self._sessions[session_id]
        entry.session.close()

    def _gc(self) -> None:
        now = time.monotonic()
        stale: list[_Entry] = []
        with self._lock:
            for sid in [s for s, e in self._sessions.items()
                        if now - e.last_used > SESSION_IDLE_TTL]:
                stale.append(self._sessions.pop(sid))
        for entry in stale:
            try:
                entry.session.close()
            except Exception:
                pass

    def close_all(self) -> None:
        with self._lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
        for entry in entries:
            try:
                entry.session.close()
            except Exception:
                pass


session_manager = SessionManager()


def get_session_factory(
    user_id: str = Depends(get_current_user),
) -> Callable[[str], BrowserSession]:
    driver_factory = driver_factory_for(user_id)
    return lambda url: ThreadedBrowserSession(driver_factory, url)
