"""A Gmail REST double. Mirrors tests/fake_browser.py: enough of the real
surface to exercise our code, none of the network."""
import base64
import json

import httpx


def encode_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def message(msg_id: str, *, thread_id="t1", sender="no-reply@greenhouse.io",
            subject="Your application", body="hello", date="Mon, 27 Jul 2026 10:00:00 +0000",
            calendar=False) -> dict:
    part = {"mimeType": "text/plain", "body": {"data": encode_body(body)}}
    parts = [part]
    if calendar:
        parts.append({"mimeType": "text/calendar", "body": {"data": encode_body("BEGIN:VCALENDAR")}})
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date},
            ],
            "parts": parts,
        },
    }


class FakeGmail:
    """Serves list/history/get. Set `quota_after` to start returning 429."""

    def __init__(self, messages: list[dict], *, history=None, history_status=200,
                 quota_after: int | None = None, profile_history_id="9100"):
        self.by_id = {m["id"]: m for m in messages}
        self.history = history
        self.history_status = history_status
        self.quota_after = quota_after
        self.profile_history_id = profile_history_id
        self.requests: list[httpx.Request] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        gets = sum(1 for r in self.requests if "/messages/" in r.url.path)
        if self.quota_after is not None and gets > self.quota_after:
            return httpx.Response(429, json={"error": {"message": "rateLimitExceeded"}})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "ada@example.com",
                                             "historyId": self.profile_history_id})
        if path.endswith("/history"):
            if self.history_status != 200:
                return httpx.Response(self.history_status, json={"error": {"message": "gone"}})
            return httpx.Response(200, json=self.history or {})
        if path.endswith("/messages"):
            return httpx.Response(200, json={
                "messages": [{"id": i, "threadId": self.by_id[i]["threadId"]}
                             for i in self.by_id],
            })
        msg_id = path.rsplit("/", 1)[-1]
        if msg_id not in self.by_id:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=self.by_id[msg_id])
