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
from lxml import html as lxml_html

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


# Gmail's documented 403 quota reasons (error.errors[].reason), distinct from
# the plain 429 it also uses for some quota classes. Both must be treated the
# same way: as a throttle, never as a generic failure.
_QUOTA_403_REASONS = frozenset({
    "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded",
})

# A defensive cap on nextPageToken-following, in case a server bug (or a
# malicious response) hands back a token that never terminates. Hitting it
# is treated the same as a quota interruption: partial, cursor untouched.
_MAX_PAGES = 50


class GmailSource:
    def __init__(self, http: httpx.Client, access_token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {access_token}"}

    # --- HTTP plumbing -------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._http.get(API + path, params=params, headers=self._headers)
        if resp.status_code == 429 or self._is_quota_403(resp):
            raise _QuotaExceeded()
        if resp.status_code >= 400:
            raise httpx.HTTPError(f"gmail {path} failed: {resp.text}")
        return resp.json()

    @staticmethod
    def _is_quota_403(resp: httpx.Response) -> bool:
        if resp.status_code != 403:
            return False
        try:
            body = resp.json()
        except ValueError:
            return False
        reasons = {e.get("reason") for e in body.get("error", {}).get("errors", [])}
        return bool(reasons & _QUOTA_403_REASONS)

    def _list_pages(self, path: str, params: dict) -> tuple[list[dict], bool]:
        """Follow nextPageToken until it runs out, a quota error interrupts
        it, or the page cap is hit. Returns (pages fetched, was_interrupted).
        Interruption always means: use what was gathered, but the caller
        must treat the whole fetch as partial and not advance its cursor.
        """
        pages: list[dict] = []
        page_token: str | None = None
        for _ in range(_MAX_PAGES):
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            try:
                page = self._get(path, page_params)
            except _QuotaExceeded:
                logger.warning("[inbox] gmail quota hit paginating %s after %d page(s)",
                                path, len(pages))
                return pages, True
            pages.append(page)
            page_token = page.get("nextPageToken")
            if not page_token:
                return pages, False
        logger.warning("[inbox] gmail %s pagination did not terminate within %d pages; "
                        "treating as partial", path, _MAX_PAGES)
        return pages, True

    # --- Public surface ------------------------------------------------

    def fetch_new(self, cursor: str | None) -> FetchResult:
        try:
            if cursor:
                try:
                    return self._incremental(cursor)
                except httpx.HTTPError:
                    # Cursor aged out (Gmail keeps ~a week of history). A full
                    # scan is correct here, not an error the user should ever
                    # see. Note _QuotaExceeded is deliberately not a subtype
                    # of httpx.HTTPError, so a quota hit here falls through
                    # to the outer handler instead of retrying as a full
                    # scan, which would just hit the same quota again.
                    logger.warning("[inbox] history cursor %s expired; full scan", cursor)
            return self._full_scan()
        except _QuotaExceeded:
            # Nothing has been fetched yet (the list or history call itself
            # was throttled) — report a clean partial result instead of
            # letting the exception escape, and don't advance the cursor.
            logger.warning("[inbox] gmail quota hit before any messages were read")
            return FetchResult([], cursor=None, partial=True)

    def _full_scan(self) -> FetchResult:
        pages, interrupted = self._list_pages("/messages", {"q": build_query(), "maxResults": 200})
        ids = [(m["id"], m["threadId"]) for page in pages for m in page.get("messages", [])]
        result = self._hydrate(ids, advance_cursor=not interrupted)
        if interrupted:
            # We don't know what's on the pages we never reached, so the
            # fetch as a whole is partial even if every id we did get
            # hydrated cleanly.
            result.partial = True
            result.cursor = None
        return result

    def _incremental(self, cursor: str) -> FetchResult:
        pages, interrupted = self._list_pages(
            "/history", {"startHistoryId": cursor, "historyTypes": "messageAdded"})
        ids = [
            (m["message"]["id"], m["message"].get("threadId", ""))
            for page in pages
            for record in page.get("history", [])
            for m in record.get("messagesAdded", [])
            if "id" in m.get("message", {})
        ]
        result = self._hydrate(ids, advance_cursor=False)
        if interrupted:
            result.partial = True
            result.cursor = None
            return result
        if not result.partial:
            # historyId reflects the mailbox's latest state regardless of
            # pagination position, so it's only safe to adopt once every
            # page has actually been consumed.
            last_page = pages[-1] if pages else {}
            result.cursor = last_page.get("historyId", cursor)
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
            except httpx.HTTPError:
                # A message can vanish between the list call and the GET
                # (deleted/trashed race -> 404). One bad message shouldn't
                # cost the whole batch.
                logger.warning("[inbox] skipping message %s: fetch failed", msg_id)
                continue
            except ValueError:
                # Corrupt/undecodable body (base64.urlsafe_b64decode raises
                # binascii.Error, a ValueError). Same reasoning: skip it.
                logger.warning("[inbox] skipping message %s: could not decode body", msg_id)
                continue
        if not advance_cursor:
            return FetchResult(messages, cursor=None, partial=False)
        try:
            cursor = self._get("/profile").get("historyId")
        except _QuotaExceeded:
            # Messages are already in hand; don't discard them just because
            # the trailing cursor lookup got throttled.
            logger.warning("[inbox] gmail quota hit fetching profile after %d messages", len(messages))
            return FetchResult(messages, cursor=None, partial=True)
        return FetchResult(messages, cursor=cursor, partial=False)

    def _one(self, msg_id: str) -> MailMessage:
        raw = self._get(f"/messages/{msg_id}", {"format": "full"})
        headers = {h["name"].lower(): h["value"]
                   for h in raw.get("payload", {}).get("headers", [])}
        parts = list(_iter_parts(raw.get("payload", {})))
        return MailMessage(
            message_id=raw["id"],
            thread_id=raw.get("threadId", ""),
            from_address=parseaddr(headers.get("from", ""))[1].lower(),
            subject=headers.get("subject", ""),
            received_at=_iso(headers.get("date")),
            body=_extract_body(parts),
            has_calendar_invite=any(p.get("mimeType") == "text/calendar" for p in parts),
        )


def _iso(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return None


def _iter_parts(node: dict):
    """Depth-first walk of a MIME part tree, yielding `node` itself first.
    Yielding the top-level payload covers the non-multipart case for free:
    a simple message has no `parts` at all and carries its content directly
    on the payload node (mimeType + body.data)."""
    yield node
    for child in node.get("parts") or []:
        yield from _iter_parts(child)


def _extract_body(parts: list[dict]) -> str:
    for p in parts:
        if p.get("mimeType") == "text/plain":
            data = p.get("body", {}).get("data")
            if data:
                return _decode(data)
    for p in parts:
        if p.get("mimeType") == "text/html":
            data = p.get("body", {}).get("data")
            if data:
                return _html_to_text(_decode(data))
    return ""


def _decode(data: str) -> str:
    # base64.urlsafe_b64decode raises binascii.Error (a ValueError subclass)
    # on corrupt input; deliberately left to propagate so _hydrate's per-
    # message `except ValueError` can skip just this one message.
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")


def _html_to_text(raw_html: str) -> str:
    if not raw_html.strip():
        return ""
    try:
        tree = lxml_html.fromstring(raw_html)
    except Exception:
        # Malformed HTML shouldn't be able to take down the sync either;
        # fall back to the raw text rather than raising.
        return raw_html.strip()
    return " ".join(tree.text_content().split())
