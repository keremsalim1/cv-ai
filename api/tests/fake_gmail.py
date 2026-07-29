"""A Gmail REST double. Mirrors tests/fake_browser.py: enough of the real
surface to exercise our code, none of the network."""
import base64

import httpx


def encode_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def part(mime_type: str, *, data: str | None = None, parts: list[dict] | None = None) -> dict:
    """Build one node of a MIME part tree. `data` is raw text (base64-encoded
    here); `parts` nests children, for multipart/* containers."""
    p: dict = {"mimeType": mime_type}
    if data is not None:
        p["body"] = {"data": encode_body(data)}
    if parts is not None:
        p["parts"] = parts
    return p


def message(msg_id: str, *, thread_id="t1", sender="no-reply@greenhouse.io",
            subject="Your application", body="hello", date="Mon, 27 Jul 2026 10:00:00 +0000",
            calendar=False, parts=None, multipart=True) -> dict:
    payload: dict = {
        "headers": [
            {"name": "From", "value": sender},
            {"name": "Subject", "value": subject},
            {"name": "Date", "value": date},
        ],
    }
    if parts is not None:
        # Caller supplies the whole part tree (nested multipart, HTML-only,
        # corrupt base64, calendar-part-nested-one-deep, etc).
        payload["parts"] = parts
    elif not multipart:
        # A simple, non-multipart message: content lives directly on the
        # payload node, there is no `parts` array at all.
        payload["mimeType"] = "text/plain"
        payload["body"] = {"data": encode_body(body)}
    else:
        built = [{"mimeType": "text/plain", "body": {"data": encode_body(body)}}]
        if calendar:
            built.append({"mimeType": "text/calendar", "body": {"data": encode_body("BEGIN:VCALENDAR")}})
        payload["parts"] = built
    return {"id": msg_id, "threadId": thread_id, "payload": payload}


class FakeGmail:
    """Serves list/history/get, with pagination and quota knobs.

    - `quota_after`: start returning a quota error from per-message GETs
      after N calls.
    - `quota_on`: make a specific endpoint ("list", "history", "profile")
      return a quota error unconditionally.
    - `quota_via_403` / `quota_reason`: serve the quota error as a Gmail-
      style 403 (error.errors[].reason) instead of a bare 429.
    - `list_pages` / `history_pages`: explicit pages, to exercise pagination.
      Omit either to keep the old single-page behavior.
    - `list_quota_on_page` / `history_quota_on_page`: return a quota error
      on a specific 0-indexed page instead of the first request.
    - `list_error_on_page` / `history_error_on_page`: return a plain 500 on a
      specific 0-indexed page — a transient failure that is *not* a quota
      error and must not be classified as one.
    - `profile_status`: make the trailing cursor lookup fail with a non-quota
      status.
    """

    def __init__(self, messages: list[dict], *, history=None, history_status=200,
                 quota_after: int | None = None, profile_history_id="9100",
                 quota_on: frozenset[str] = frozenset(),
                 quota_via_403: bool = False, quota_reason: str = "rateLimitExceeded",
                 list_pages: list[list[str]] | None = None,
                 history_pages: list[dict] | None = None,
                 list_quota_on_page: int | None = None,
                 history_quota_on_page: int | None = None,
                 list_error_on_page: int | None = None,
                 history_error_on_page: int | None = None,
                 profile_status: int = 200):
        self.by_id = {m["id"]: m for m in messages}
        self.history = history
        self.history_status = history_status
        self.quota_after = quota_after
        self.profile_history_id = profile_history_id
        self.quota_on = quota_on
        self.quota_via_403 = quota_via_403
        self.quota_reason = quota_reason
        self.list_pages = list_pages
        self.history_pages = history_pages
        self.list_quota_on_page = list_quota_on_page
        self.history_quota_on_page = history_quota_on_page
        self.list_error_on_page = list_error_on_page
        self.history_error_on_page = history_error_on_page
        self.profile_status = profile_status
        self.requests: list[httpx.Request] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def _quota_response(self) -> httpx.Response:
        if self.quota_via_403:
            return httpx.Response(403, json={
                "error": {
                    "errors": [{"domain": "usageLimits", "reason": self.quota_reason,
                                "message": "quota exceeded"}],
                    "code": 403, "message": "quota exceeded",
                },
            })
        return httpx.Response(429, json={"error": {"message": "rateLimitExceeded"}})

    @staticmethod
    def _page_index(request: httpx.Request) -> int:
        token = request.url.params.get("pageToken")
        return int(token) if token else 0

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/messages") and "list" in self.quota_on:
            return self._quota_response()
        if path.endswith("/history") and "history" in self.quota_on:
            return self._quota_response()
        if path.endswith("/profile") and "profile" in self.quota_on:
            return self._quota_response()
        gets = sum(1 for r in self.requests if "/messages/" in r.url.path)
        if self.quota_after is not None and gets > self.quota_after:
            return self._quota_response()
        if path.endswith("/profile"):
            if self.profile_status != 200:
                return httpx.Response(self.profile_status, json={"error": {"message": "boom"}})
            return httpx.Response(200, json={"emailAddress": "ada@example.com",
                                             "historyId": self.profile_history_id})
        if path.endswith("/history"):
            page_index = self._page_index(request)
            if self.history_quota_on_page is not None and page_index == self.history_quota_on_page:
                return self._quota_response()
            if self.history_error_on_page is not None and page_index == self.history_error_on_page:
                return httpx.Response(500, json={"error": {"message": "boom"}})
            if self.history_status != 200:
                return httpx.Response(self.history_status, json={"error": {"message": "gone"}})
            if self.history_pages is not None:
                body = dict(self.history_pages[page_index])
                if page_index + 1 < len(self.history_pages):
                    body["nextPageToken"] = str(page_index + 1)
                return httpx.Response(200, json=body)
            return httpx.Response(200, json=self.history or {})
        if path.endswith("/messages"):
            page_index = self._page_index(request)
            if self.list_quota_on_page is not None and page_index == self.list_quota_on_page:
                return self._quota_response()
            if self.list_error_on_page is not None and page_index == self.list_error_on_page:
                return httpx.Response(500, json={"error": {"message": "boom"}})
            if self.list_pages is not None:
                ids = self.list_pages[page_index]
                body = {"messages": [{"id": i, "threadId": self.by_id.get(i, {}).get("threadId", "t1")}
                                      for i in ids]}
                if page_index + 1 < len(self.list_pages):
                    body["nextPageToken"] = str(page_index + 1)
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={
                "messages": [{"id": i, "threadId": self.by_id[i]["threadId"]}
                             for i in self.by_id],
            })
        msg_id = path.rsplit("/", 1)[-1]
        if msg_id not in self.by_id:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=self.by_id[msg_id])
