"""Fetching candidate mail. Knows Gmail; knows nothing about job applications.

The narrowing happens in Gmail's own query so unrelated mail is never
downloaded. Bodies are pulled only for messages that survive it.
"""
import base64
import logging
from dataclasses import dataclass
from email.utils import parsedate_to_datetime, parseaddr
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Senders whose mail is almost always an application response. Add an entry
# only when a real message proves the query missed something.
ATS_DOMAINS: tuple[str, ...] = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "myworkday.com",
    "ashbyhq.com", "successfactors.com", "icims.com", "smartrecruiters.com",
    "workable.com", "recruitee.com", "teamtailor.com", "jobvite.com",
    "taleo.net", "kariyer.net", "linkedin.com",
)

SUBJECT_WORDS: tuple[str, ...] = (
    "application", "interview", "position", "candidate",
    "başvuru", "mülakat", "pozisyon", "görüşme", "aday",
)


@dataclass(frozen=True)
class MailMessage:
    message_id: str
    thread_id: str
    from_address: str
    subject: str
    received_at: str | None
    body: str
    has_calendar_invite: bool


@dataclass
class FetchResult:
    messages: list[MailMessage]
    cursor: str | None
    partial: bool


class MailSource(Protocol):
    def fetch_new(self, cursor: str | None) -> FetchResult: ...


def build_query(days: int = 90) -> str:
    senders = " OR ".join(ATS_DOMAINS)
    words = " OR ".join(SUBJECT_WORDS)
    return f"newer_than:{days}d AND (from:({senders}) OR subject:({words}))"


class _QuotaExceeded(Exception):
    pass


class GmailSource:
    def __init__(self, http: httpx.Client, access_token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {access_token}"}

    # --- HTTP plumbing -------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._http.get(API + path, params=params, headers=self._headers)
        if resp.status_code == 429:
            raise _QuotaExceeded()
        if resp.status_code >= 400:
            raise httpx.HTTPError(f"gmail {path} failed: {resp.text}")
        return resp.json()

    # --- Public surface ------------------------------------------------

    def fetch_new(self, cursor: str | None) -> FetchResult:
        if cursor:
            try:
                return self._incremental(cursor)
            except httpx.HTTPError:
                # Cursor aged out (Gmail keeps ~a week of history). A full scan
                # is correct here, not an error the user should ever see.
                logger.warning("[inbox] history cursor %s expired; full scan", cursor)
        return self._full_scan()

    def _full_scan(self) -> FetchResult:
        listing = self._get("/messages", {"q": build_query(), "maxResults": 200})
        ids = [(m["id"], m["threadId"]) for m in listing.get("messages", [])]
        return self._hydrate(ids, advance_cursor=True)

    def _incremental(self, cursor: str) -> FetchResult:
        page = self._get("/history", {"startHistoryId": cursor,
                                      "historyTypes": "messageAdded"})
        ids = [
            (m["message"]["id"], m["message"].get("threadId", ""))
            for record in page.get("history", [])
            for m in record.get("messagesAdded", [])
        ]
        result = self._hydrate(ids, advance_cursor=False)
        if not result.partial:
            result.cursor = page.get("historyId", cursor)
        return result

    def _hydrate(self, ids, *, advance_cursor: bool) -> FetchResult:
        messages: list[MailMessage] = []
        for msg_id, _thread in ids:
            try:
                messages.append(self._one(msg_id))
            except _QuotaExceeded:
                # Return what we have and leave the cursor alone, so the next
                # sync re-reads the tail instead of skipping it.
                logger.warning("[inbox] gmail quota hit after %d messages", len(messages))
                return FetchResult(messages, cursor=None, partial=True)
        cursor = self._get("/profile").get("historyId") if advance_cursor else None
        return FetchResult(messages, cursor=cursor, partial=False)

    def _one(self, msg_id: str) -> MailMessage:
        raw = self._get(f"/messages/{msg_id}", {"format": "full"})
        headers = {h["name"].lower(): h["value"]
                   for h in raw.get("payload", {}).get("headers", [])}
        parts = raw.get("payload", {}).get("parts", [])
        return MailMessage(
            message_id=raw["id"],
            thread_id=raw.get("threadId", ""),
            from_address=parseaddr(headers.get("from", ""))[1].lower(),
            subject=headers.get("subject", ""),
            received_at=_iso(headers.get("date")),
            body=_plain_text(parts),
            has_calendar_invite=any(p.get("mimeType") == "text/calendar" for p in parts),
        )


def _iso(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return None


def _plain_text(parts: list[dict]) -> str:
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            return base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")
    return ""
