"""Persistent headed browser sessions for assisted apply. Each session owns a
BrowserDriver on a dedicated thread, because sync Playwright objects are not
thread-safe and FastAPI's threadpool has no thread affinity."""
import queue
import threading
import time
import uuid
from typing import Callable, Protocol

from fastapi import HTTPException

from app.services.browser import BrowserDriver, get_driver_factory

SESSION_IDLE_TTL = 900  # seconds a session may sit idle before it is GC'd


class BrowserSession(Protocol):
    def snapshot(self) -> str: ...
    def fill_form(self, schema, answers, pdf_path: str) -> None: ...
    def screenshot(self) -> bytes: ...
    def close(self) -> None: ...


class ThreadedBrowserSession:
    """Owns a BrowserDriver on a dedicated thread; every command runs there."""

    def __init__(self, driver_factory: Callable[[bool], BrowserDriver], url: str):
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

    def snapshot(self) -> str:
        return self._call(lambda d: d.content())

    def fill_form(self, schema, answers, pdf_path: str) -> None:
        from app.services.apply import _fill_form   # lazy: avoid import cycle
        self._call(lambda d: _fill_form(d, schema, answers, pdf_path))

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
    def __init__(self):
        self._sessions: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def start(self, factory: Callable[[str], BrowserSession], url: str, user_id: str) -> str:
        self._gc()
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


def get_session_factory() -> Callable[[str], BrowserSession]:
    driver_factory = get_driver_factory()
    return lambda url: ThreadedBrowserSession(driver_factory, url)
