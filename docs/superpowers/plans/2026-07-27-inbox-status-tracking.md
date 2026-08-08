# Inbox Status Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the user's Gmail, and show each job application as one of five stages — Alındı, Değerlendirmede, Mülakat, Teklif, Ret — each traceable to the email that produced it.

**Architecture:** A Gmail-side query narrows the mailbox before anything is downloaded. Surviving messages go through a four-stage pipeline — fetch → classify → match → advance — orchestrated by a single function, `sync_user_inbox(user_id)`, which the HTTP layer calls on demand. Classification tries deterministic patterns first and falls back to Gemini only on ambiguity; when neither is confident, nothing moves. Every processed message is recorded so the UI can justify each badge.

**Tech Stack:** FastAPI, pytest, httpx (already a dependency), `cryptography`/Fernet (already a dependency), `tld` (already a dependency), Gmail REST API v1, Supabase PostgREST, Next.js 16, next-intl, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-07-27-inbox-status-tracking-design.md`

## Global Constraints

- **No new Python dependencies.** `httpx`, `cryptography`, `tld`, `pytest`, `pydantic` are already in `api/requirements.txt`. Do not add `google-api-python-client` or `supabase-py`; the raw REST calls in this plan are deliberate.
- **Python 3.11**, FastAPI style as in `api/app/routers/apply.py`: a thin router that delegates to a service in `api/app/services/`.
- **Tests are offline.** No test may make a real network call. HTTP is faked by injecting an `httpx.MockTransport` or a fake client, following the existing `tests/fake_browser.py` pattern.
- **TDD.** Write the failing test, run it, watch it fail for the right reason, implement, watch it pass, commit.
- **Every user-facing string exists in both `web/src/messages/tr.json` and `web/src/messages/en.json`.** A key present in only one is a bug.
- **The refresh token never leaves the API.** No endpoint returns it, no log line prints it, no browser-readable table stores it.
- **Never invent a stage.** If the classifier is unsure, the event is recorded with `detected_stage = null` and the application's stage does not change.
- **Stage vocabulary, exactly:** `received`, `in_review`, `interview`, `offer`, `rejected`.
- Run API tests with `.venv\Scripts\python -m pytest` from `api/`; web tests with `npm test` from `web/`.

## Design amendment discovered during planning

The spec assumed the API could read and write application rows. **It cannot today.** Every database call in this codebase happens in the browser through the Supabase JS client, protected by RLS (`web/src/lib/db.ts`); `api/` holds no database client at all and its `.env` has no Supabase URL or key — only the JWT verification settings.

The sync pipeline cannot follow that pattern, because the Gmail refresh token must never be readable by a browser. So the API gains database access in **Task 2**: a small PostgREST client using a service-role key, scoped to the inbox feature. Because the service role bypasses RLS, every query it issues filters on `user_id` explicitly, and that filtering is what Task 2's tests pin down.

One spec element falls away as a result. The spec had the browser read connection state from an `email_connection_status` view over the token table. Once the API owns that table, `GET /inbox/status` answers the same question with no extra database surface, so the view is not built — a view nothing reads is one more thing to keep correct for no benefit. Applications and their events stay browser-read under RLS, exactly as the rest of the product works.

## File Structure

**Database**
- Create `supabase/migrations/0003_inbox.sql` — new tables and `applications` columns.

**API — one responsibility per module**
- Create `api/app/services/supabase_db.py` — PostgREST client. Knows HTTP and tables; knows nothing about email.
- Create `api/app/services/inbox_connect.py` — Google OAuth exchange, token encryption, connection lifecycle.
- Create `api/app/services/mailbox.py` — `MailSource` protocol, `MailMessage`, `GmailSource`. Knows Gmail; knows nothing about job applications.
- Create `api/app/services/inbox_classify.py` — rules, LLM fallback, `Signal`. Pure given a `MailMessage`.
- Create `api/app/services/inbox_match.py` — company-name normalization and the four-step match. Pure.
- Create `api/app/services/inbox_stage.py` — the stage machine. Pure.
- Create `api/app/services/inbox_sync.py` — `sync_user_inbox`, the only orchestrator.
- Create `api/app/routers/inbox.py` — four endpoints, no logic.
- Modify `api/app/config.py` — new settings.
- Modify `api/app/main.py` — register the router.
- Modify `api/README.md` — env vars and endpoints.

**API tests**
- Create `api/tests/fixtures/mail/` — the fixture corpus (JSON files).
- Create `api/tests/fake_gmail.py` — fake Gmail transport, mirroring `tests/fake_browser.py`.
- Create `api/tests/test_supabase_db.py`, `test_inbox_connect.py`, `test_mailbox.py`, `test_inbox_classify.py`, `test_inbox_match.py`, `test_inbox_stage.py`, `test_inbox_sync.py`, `test_inbox_router.py`.

**Web**
- Modify `web/src/types/db.ts` — extend `ApplicationRow`, add `ApplicationEventRow`, `EmailConnectionStatus`.
- Modify `web/src/lib/db.ts` — list applications with their events.
- Modify `web/src/lib/api.ts` — four inbox calls.
- Create `web/src/app/auth/gmail/callback/route.ts` — OAuth landing.
- Create `web/src/app/(app)/applications/page.tsx`.
- Create `web/src/components/applications/StageBadge.tsx`, `ConnectGmailCard.tsx`, `ApplicationCard.tsx`.
- Modify `web/src/components/AppSidebar.tsx`, `web/src/lib/protected.ts`, `web/src/messages/{tr,en}.json`.

---

### Task 1: Database schema and web types

**Files:**
- Create: `supabase/migrations/0003_inbox.sql`
- Modify: `web/src/types/db.ts`
- Modify: `web/src/lib/db.ts`
- Test: `web/src/lib/__tests__/db.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: tables `email_connections`, `application_events`; new `applications` columns `company`, `title`, `stage`, `stage_updated_at`, `source`. TS: `ApplicationRow` gains those fields; `ApplicationEventRow`; `listApplicationEvents(sb, applicationId): Promise<ApplicationEventRow[]>`.

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/0003_inbox.sql`:

```sql
-- KRESUME.ai Faz 4: inbox status tracking

-- `status` answers "could we deliver it"; `stage` answers "what did the company
-- say". An email-discovered application has no delivery attempt of ours, hence
-- the new 'external' status.
alter table public.applications
  add column company text,
  add column title text,
  add column stage text not null default 'received'
    check (stage in ('received', 'in_review', 'interview', 'offer', 'rejected')),
  add column stage_updated_at timestamptz,
  add column source text not null default 'assisted'
    check (source in ('assisted', 'email'));

alter table public.applications drop constraint applications_status_check;
alter table public.applications add constraint applications_status_check
  check (status in ('submitted', 'delivered', 'failed', 'external'));

-- The refresh token lives here and is never exposed to a browser: RLS is on and
-- no policy grants the `authenticated` role anything, so every browser query
-- returns nothing. The API reaches it with the service role and filters by
-- user_id itself. The UI learns the connection state from GET /inbox/status,
-- never from this table.
create table public.email_connections (
  user_id           uuid primary key references public.profiles (id) on delete cascade,
  provider          text not null default 'gmail' check (provider in ('gmail')),
  email_address     text not null,
  refresh_token_enc text not null,
  last_history_id   text,
  last_synced_at    timestamptz,
  status            text not null default 'active'
                      check (status in ('active', 'revoked', 'error')),
  created_at        timestamptz not null default now()
);

alter table public.email_connections enable row level security;
revoke all on public.email_connections from anon, authenticated;
-- Deliberately no policy: with RLS on and no grant, this table is invisible to
-- every browser session, which is the whole point.

-- One row per processed message, whether or not it moved the stage. This is
-- what lets the UI answer "why does it say Ret?".
create table public.application_events (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (id) on delete cascade,
  application_id uuid not null references public.applications (id) on delete cascade,
  source         text not null default 'email' check (source in ('email')),
  message_id     text not null,
  thread_id      text,
  from_address   text,
  subject        text,
  received_at    timestamptz,
  detected_stage text
    check (detected_stage is null
           or detected_stage in ('received', 'in_review', 'interview', 'offer', 'rejected')),
  confidence     real,
  evidence       text,
  created_at     timestamptz not null default now(),
  unique (user_id, message_id)
);

alter table public.application_events enable row level security;

create policy "own application events" on public.application_events
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index application_events_application_idx
  on public.application_events (application_id, received_at desc);
```

- [ ] **Step 2: Write the failing test for the new db helper**

`web/src/lib/__tests__/db.test.ts` already defines a chainable `stubClient(result)` helper at the top of the file — use it rather than a bespoke mock. Add `listApplicationEvents` to the existing import from `@/lib/db`, then append:

```ts
it('lists an application\'s events newest first', async () => {
  const { sb, from, q } = stubClient({ data: [{ id: 'e1' }], error: null })

  const rows = await listApplicationEvents(sb, 'app-1')

  expect(from).toHaveBeenCalledWith('application_events')
  expect(q.eq).toHaveBeenCalledWith('application_id', 'app-1')
  expect(q.order).toHaveBeenCalledWith('received_at', { ascending: false })
  expect(rows).toEqual([{ id: 'e1' }])
})
```

- [ ] **Step 3: Run it and watch it fail**

Run: `npm test -- src/lib/__tests__/db.test.ts`
Expected: FAIL — `listApplicationEvents` is not exported.

- [ ] **Step 4: Extend the types**

In `web/src/types/db.ts`, replace the `ApplicationRow` interface and append:

```ts
export type ApplicationStage = 'received' | 'in_review' | 'interview' | 'offer' | 'rejected'

export interface ApplicationRow {
  id: string
  user_id: string
  cv_id: string | null
  optimized_cv_id: string | null
  url: string
  job_text: string | null
  cover_letter: string | null
  qa: unknown
  changes: string[]
  status: 'submitted' | 'delivered' | 'failed' | 'external'
  company: string | null
  title: string | null
  stage: ApplicationStage
  stage_updated_at: string | null
  source: 'assisted' | 'email'
  created_at: string
}
export type NewApplication = Omit<
  ApplicationRow, 'id' | 'created_at' | 'company' | 'title' | 'stage' | 'stage_updated_at' | 'source'
> & Partial<Pick<ApplicationRow, 'company' | 'title' | 'stage' | 'source'>>

export interface ApplicationEventRow {
  id: string
  user_id: string
  application_id: string
  source: 'email'
  message_id: string
  thread_id: string | null
  from_address: string | null
  subject: string | null
  received_at: string | null
  detected_stage: ApplicationStage | null
  confidence: number | null
  evidence: string | null
  created_at: string
}

export interface EmailConnectionStatus {
  user_id: string
  email_address: string
  last_synced_at: string | null
  status: 'active' | 'revoked' | 'error'
}
```

- [ ] **Step 5: Add the helper**

Append to `web/src/lib/db.ts` (and add `ApplicationEventRow` to the type import at the top):

```ts
export async function listApplicationEvents(
  sb: SupabaseClient, applicationId: string
): Promise<ApplicationEventRow[]> {
  const { data, error } = await sb
    .from('application_events').select('*')
    .eq('application_id', applicationId)
    .order('received_at', { ascending: false })
  if (error) throw error
  return (data ?? []) as ApplicationEventRow[]
}
```

- [ ] **Step 6: Run the web tests**

Run: `npm test`
Expected: PASS, including the pre-existing `RecentApplications` and `applications` tests. `NewApplication` stayed structurally compatible with `saveApplication` in `src/lib/applications.ts`, so nothing there needs changing — if TypeScript disagrees, fix `applications.ts` rather than widening the type.

- [ ] **Step 7: Typecheck**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 8: Apply the migration to the Supabase project**

Run the SQL in the Supabase SQL editor (or `supabase db push` if the CLI is linked). Then confirm in the dashboard that `applications` shows the five new columns and both new tables exist.

- [ ] **Step 9: Commit**

```bash
git add supabase/migrations/0003_inbox.sql web/src/types/db.ts web/src/lib/db.ts web/src/lib/__tests__/db.test.ts
git commit -m "feat(db): application stages, email connections, and an event trail"
```

---

### Task 2: PostgREST client for the API

**Files:**
- Create: `api/app/services/supabase_db.py`
- Modify: `api/app/config.py`
- Test: `api/tests/test_supabase_db.py`

**Interfaces:**
- Consumes: `get_settings()` from `app.config`.
- Produces:
  ```python
  class SupabaseDB:
      def __init__(self, client: httpx.Client, url: str, key: str) -> None: ...
      def select(self, table: str, params: dict[str, str]) -> list[dict]: ...
      def insert(self, table: str, row: dict, *, on_conflict: str | None = None) -> dict | None: ...
      def update(self, table: str, params: dict[str, str], patch: dict) -> list[dict]: ...
      def delete(self, table: str, params: dict[str, str]) -> None: ...

  def get_db() -> SupabaseDB: ...   # FastAPI dependency
  ```
  `insert` returns `None` when an `on_conflict` clause swallowed a duplicate.
- New settings: `supabase_url: str = ""`, `supabase_service_key: str = ""`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_supabase_db.py`:

```python
import httpx
import pytest

from app.services.supabase_db import SupabaseDB


def make_db(handler) -> SupabaseDB:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseDB(client, "https://proj.supabase.co", "service-key")


def test_select_sends_the_service_key_and_returns_rows():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["apikey"] = request.headers["apikey"]
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=[{"id": "a1"}])

    rows = make_db(handler).select("applications", {"user_id": "eq.u1", "select": "*"})

    assert rows == [{"id": "a1"}]
    assert seen["path"] == "/rest/v1/applications"
    assert seen["params"] == {"user_id": "eq.u1", "select": "*"}
    assert seen["apikey"] == "service-key"
    assert seen["auth"] == "Bearer service-key"


def test_insert_returns_the_created_row():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Prefer"] == "return=representation"
        return httpx.Response(201, json=[{"id": "new"}])

    assert make_db(handler).insert("applications", {"url": "x"}) == {"id": "new"}


def test_insert_with_on_conflict_returns_none_when_the_row_already_existed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["on_conflict"] == "user_id,message_id"
        assert "resolution=ignore-duplicates" in request.headers["Prefer"]
        return httpx.Response(201, json=[])   # PostgREST returns [] on ignore

    result = make_db(handler).insert(
        "application_events", {"message_id": "m1"}, on_conflict="user_id,message_id"
    )
    assert result is None


def test_update_returns_the_patched_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(200, json=[{"id": "a1", "stage": "rejected"}])

    rows = make_db(handler).update(
        "applications", {"id": "eq.a1"}, {"stage": "rejected"}
    )
    assert rows == [{"id": "a1", "stage": "rejected"}]


def test_an_error_response_raises_with_the_body_visible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "column does not exist"})

    with pytest.raises(RuntimeError, match="column does not exist"):
        make_db(handler).select("applications", {})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_supabase_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.supabase_db'`.

- [ ] **Step 3: Add the settings**

In `api/app/config.py`, inside `Settings`, after `daily_ai_limit`:

```python
    # The inbox feature is the only server-side database consumer. It needs the
    # service role because the Gmail refresh token must be unreadable by any
    # browser, which means no RLS policy can grant access to it. Every query
    # this key issues filters on user_id explicitly — see supabase_db callers.
    supabase_url: str = ""
    supabase_service_key: str = ""
```

- [ ] **Step 4: Implement the client**

Create `api/app/services/supabase_db.py`:

```python
"""Server-side database access, used only by the inbox feature.

Everything else in this product reaches Supabase from the browser under RLS
(see web/src/lib/db.ts). The inbox cannot: it stores a Gmail refresh token that
no browser may read, so no RLS policy can exist for it. That forces the service
role, which bypasses RLS — so every caller here must filter on user_id itself.
"""
import httpx

from app.config import get_settings


class SupabaseDB:
    def __init__(self, client: httpx.Client, url: str, key: str) -> None:
        self._client = client
        self._base = url.rstrip("/") + "/rest/v1/"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _send(self, method: str, table: str, *, params=None, json=None,
              prefer: str | None = None) -> list[dict]:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        resp = self._client.request(
            method, self._base + table, params=params, json=json, headers=headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"supabase {method} {table} failed: {resp.text}")
        if not resp.content:
            return []
        body = resp.json()
        return body if isinstance(body, list) else [body]

    def select(self, table: str, params: dict[str, str]) -> list[dict]:
        return self._send("GET", table, params=params)

    def insert(self, table: str, row: dict, *,
               on_conflict: str | None = None) -> dict | None:
        params = {"on_conflict": on_conflict} if on_conflict else None
        prefer = "return=representation"
        if on_conflict:
            prefer += ",resolution=ignore-duplicates"
        rows = self._send("POST", table, params=params, json=row, prefer=prefer)
        return rows[0] if rows else None

    def update(self, table: str, params: dict[str, str], patch: dict) -> list[dict]:
        return self._send("PATCH", table, params=params, json=patch,
                          prefer="return=representation")

    def delete(self, table: str, params: dict[str, str]) -> None:
        self._send("DELETE", table, params=params)


def get_db() -> SupabaseDB:
    settings = get_settings()
    return SupabaseDB(httpx.Client(timeout=20.0),
                      settings.supabase_url, settings.supabase_service_key)
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_supabase_db.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/supabase_db.py app/config.py tests/test_supabase_db.py
git commit -m "feat(api): server-side database access for the inbox feature"
```

---

### Task 3: The token vault

**Files:**
- Create: `api/app/services/inbox_connect.py`
- Modify: `api/app/config.py`
- Test: `api/tests/test_inbox_connect.py`

**Interfaces:**
- Consumes: `SupabaseDB` from Task 2.
- Produces: `encrypt_token(plain: str) -> str`, `decrypt_token(blob: str) -> str`, `TokenError`.
- New settings: `email_token_key: str`, `google_client_id: str`, `google_client_secret: str`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_inbox_connect.py`:

```python
import pytest
from cryptography.fernet import Fernet

from app.services.inbox_connect import TokenError, decrypt_token, encrypt_token


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


def test_a_token_survives_a_round_trip():
    assert decrypt_token(encrypt_token("1//refresh-abc")) == "1//refresh-abc"


def test_the_ciphertext_does_not_contain_the_token():
    assert "refresh-abc" not in encrypt_token("1//refresh-abc")


def test_two_encryptions_of_the_same_token_differ():
    # Fernet embeds a random IV; identical ciphertexts would leak equality
    assert encrypt_token("same") != encrypt_token("same")


def test_a_tampered_blob_is_refused_rather_than_returning_garbage():
    blob = encrypt_token("1//refresh-abc")
    tampered = blob[:-4] + ("aaaa" if not blob.endswith("aaaa") else "bbbb")
    with pytest.raises(TokenError):
        decrypt_token(tampered)


def test_a_missing_key_is_a_clear_error_not_a_crash(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", "")
    with pytest.raises(TokenError, match="EMAIL_TOKEN_KEY"):
        encrypt_token("anything")
    get_settings.cache_clear()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_connect.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Add the settings**

In `api/app/config.py`, after the two Supabase settings from Task 2:

```python
    # Fernet key (44-char urlsafe base64) protecting stored Gmail refresh
    # tokens. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    email_token_key: str = ""
    # Our own Google OAuth client — deliberately not Supabase's. Supabase's
    # provider_token expires in an hour and vanishes on session refresh, so it
    # cannot serve a sync that runs whenever the user opens the page.
    google_client_id: str = ""
    google_client_secret: str = ""
```

- [ ] **Step 4: Implement encryption**

Create `api/app/services/inbox_connect.py`:

```python
"""Gmail connection lifecycle: OAuth exchange, token storage, revocation."""
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)


class TokenError(Exception):
    pass


def _cipher() -> Fernet:
    key = get_settings().email_token_key
    if not key:
        raise TokenError("EMAIL_TOKEN_KEY is not set; cannot store Gmail tokens")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenError(f"EMAIL_TOKEN_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_token(plain: str) -> str:
    return _cipher().encrypt(plain.encode()).decode()


def decrypt_token(blob: str) -> str:
    try:
        return _cipher().decrypt(blob.encode()).decode()
    except InvalidToken as exc:
        raise TokenError("stored Gmail token could not be decrypted") from exc
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_connect.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/inbox_connect.py app/config.py tests/test_inbox_connect.py
git commit -m "feat(api): encrypt Gmail refresh tokens at rest"
```

---

### Task 4: Connecting and disconnecting a mailbox

**Files:**
- Modify: `api/app/services/inbox_connect.py`
- Test: `api/tests/test_inbox_connect.py`

**Interfaces:**
- Consumes: `encrypt_token`/`decrypt_token` (Task 3), `SupabaseDB` (Task 2).
- Produces:
  ```python
  def connect_gmail(db, http, user_id: str, code: str, redirect_uri: str) -> dict: ...
      # -> {"connected": True, "email": str}
  def disconnect_gmail(db, http, user_id: str) -> None: ...
  def connection_status(db, user_id: str) -> dict: ...
      # -> {"connected": bool, "email": str | None,
      #     "last_synced_at": str | None, "status": str | None}
  def access_token_for(db, http, user_id: str) -> str: ...
  class ConnectionError_(Exception): ...   # raised when the grant is gone
  ```

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_inbox_connect.py`:

```python
import httpx

from app.services.inbox_connect import (
    ConnectionError_, access_token_for, connect_gmail, connection_status,
    disconnect_gmail,
)


class FakeDB:
    """Records writes; serves whatever rows the test seeded."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict, dict]] = []
        self.deleted: list[tuple[str, dict]] = []

    def select(self, table, params):
        return list(self.rows)

    def insert(self, table, row, *, on_conflict=None):
        self.inserted.append((table, row))
        self.rows.append(row)
        return row

    def update(self, table, params, patch):
        self.updated.append((table, params, patch))
        for r in self.rows:
            r.update(patch)
        return self.rows

    def delete(self, table, params):
        self.deleted.append((table, params))
        self.rows.clear()


def http_returning(*responses):
    queue = list(responses)
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_connecting_stores_an_encrypted_token_and_the_address(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    from app.config import get_settings
    get_settings.cache_clear()

    db = FakeDB()
    http = http_returning(
        (200, {"access_token": "at", "refresh_token": "1//rt"}),
        (200, {"emailAddress": "ada@example.com", "historyId": "9001"}),
    )

    result = connect_gmail(db, http, "u1", code="auth-code",
                           redirect_uri="http://localhost:3000/auth/gmail/callback")

    assert result == {"connected": True, "email": "ada@example.com"}
    table, row = db.inserted[0]
    assert table == "email_connections"
    assert row["user_id"] == "u1"
    assert row["email_address"] == "ada@example.com"
    assert row["last_history_id"] == "9001"
    assert "1//rt" not in row["refresh_token_enc"]   # stored encrypted
    get_settings.cache_clear()


def test_connecting_without_a_refresh_token_is_an_error_not_a_half_connection():
    # Google omits refresh_token when the user already granted consent and we
    # forgot prompt=consent. Storing nothing is better than storing a dead row.
    db = FakeDB()
    http = http_returning((200, {"access_token": "at"}))
    with pytest.raises(ConnectionError_, match="refresh token"):
        connect_gmail(db, http, "u1", code="c", redirect_uri="r")
    assert db.inserted == []


def test_status_reports_a_missing_connection_without_raising():
    assert connection_status(FakeDB(), "u1") == {
        "connected": False, "email": None, "last_synced_at": None, "status": None,
    }


def test_status_reports_an_existing_connection():
    db = FakeDB([{"email_address": "ada@example.com",
                  "last_synced_at": "2026-07-27T10:00:00Z", "status": "active"}])
    assert connection_status(db, "u1") == {
        "connected": True, "email": "ada@example.com",
        "last_synced_at": "2026-07-27T10:00:00Z", "status": "active",
    }


def test_disconnecting_revokes_at_google_before_deleting_the_row():
    db = FakeDB([{"refresh_token_enc": encrypt_token("1//rt")}])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    disconnect_gmail(db, httpx.Client(transport=httpx.MockTransport(handler)), "u1")

    assert any("oauth2.googleapis.com/revoke" in c for c in calls)
    assert db.deleted == [("email_connections", {"user_id": "eq.u1"})]


def test_disconnecting_deletes_the_row_even_if_google_refuses_the_revoke():
    # A grant the user already revoked at Google returns 400. Leaving our row
    # behind would show a connection that cannot work.
    db = FakeDB([{"refresh_token_enc": encrypt_token("1//rt")}])
    http = http_returning((400, {"error": "invalid_token"}))
    disconnect_gmail(db, http, "u1")
    assert db.deleted


def test_a_revoked_grant_marks_the_connection_and_raises():
    db = FakeDB([{"refresh_token_enc": encrypt_token("1//rt"), "status": "active"}])
    http = http_returning((400, {"error": "invalid_grant"}))

    with pytest.raises(ConnectionError_):
        access_token_for(db, http, "u1")

    assert db.updated[0][2] == {"status": "revoked"}


def test_an_access_token_is_minted_from_the_stored_refresh_token():
    db = FakeDB([{"refresh_token_enc": encrypt_token("1//rt")}])
    http = http_returning((200, {"access_token": "fresh-at"}))
    assert access_token_for(db, http, "u1") == "fresh-at"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_connect.py -v`
Expected: FAIL — `ImportError: cannot import name 'connect_gmail'`.

- [ ] **Step 3: Implement the lifecycle**

Append to `api/app/services/inbox_connect.py`:

```python
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class ConnectionError_(Exception):
    """The Gmail grant is missing, revoked, or was never completed."""


def _connection(db, user_id: str) -> dict | None:
    rows = db.select("email_connections",
                     {"user_id": f"eq.{user_id}", "select": "*"})
    return rows[0] if rows else None


def connect_gmail(db, http, user_id: str, code: str, redirect_uri: str) -> dict:
    settings = get_settings()
    resp = http.post(TOKEN_URL, data={
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    if resp.status_code >= 400:
        raise ConnectionError_(f"Google refused the authorization code: {resp.text}")
    payload = resp.json()

    refresh = payload.get("refresh_token")
    if not refresh:
        # Happens when consent was already granted and prompt=consent was
        # omitted. Without it we could sync once and then go silent forever.
        raise ConnectionError_("Google returned no refresh token; re-consent required")

    access = payload["access_token"]
    profile = http.get(PROFILE_URL, headers={"Authorization": f"Bearer {access}"})
    if profile.status_code >= 400:
        raise ConnectionError_(f"Gmail profile unreadable: {profile.text}")
    info = profile.json()

    db.delete("email_connections", {"user_id": f"eq.{user_id}"})
    db.insert("email_connections", {
        "user_id": user_id,
        "provider": "gmail",
        "email_address": info["emailAddress"],
        "refresh_token_enc": encrypt_token(refresh),
        "last_history_id": info.get("historyId"),
        "status": "active",
    })
    return {"connected": True, "email": info["emailAddress"]}


def disconnect_gmail(db, http, user_id: str) -> None:
    row = _connection(db, user_id)
    if row:
        try:
            http.post(REVOKE_URL, params={"token": decrypt_token(row["refresh_token_enc"])})
        except (TokenError, httpx.HTTPError) as exc:
            # Already revoked, or unreachable. Keeping our row would advertise a
            # connection that cannot work, so delete it regardless.
            logger.warning("[inbox] revoke failed for %s: %s", user_id, exc)
    db.delete("email_connections", {"user_id": f"eq.{user_id}"})


def connection_status(db, user_id: str) -> dict:
    row = _connection(db, user_id)
    if not row:
        return {"connected": False, "email": None,
                "last_synced_at": None, "status": None}
    return {
        "connected": True,
        "email": row["email_address"],
        "last_synced_at": row.get("last_synced_at"),
        "status": row.get("status"),
    }


def access_token_for(db, http, user_id: str) -> str:
    row = _connection(db, user_id)
    if not row:
        raise ConnectionError_("no Gmail connection for this user")
    settings = get_settings()
    resp = http.post(TOKEN_URL, data={
        "refresh_token": decrypt_token(row["refresh_token_enc"]),
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    })
    if resp.status_code >= 400:
        # invalid_grant means the user revoked us at Google. Record that, so the
        # UI can say so instead of silently returning stale stages forever.
        db.update("email_connections", {"user_id": f"eq.{user_id}"},
                  {"status": "revoked"})
        raise ConnectionError_(f"Gmail grant is no longer valid: {resp.text}")
    return resp.json()["access_token"]
```

Add `import httpx` to the module's imports.

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_connect.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/inbox_connect.py tests/test_inbox_connect.py
git commit -m "feat(api): connect, revoke, and refresh a Gmail grant"
```

---

### Task 5: Reading the mailbox

**Files:**
- Create: `api/app/services/mailbox.py`
- Create: `api/tests/fake_gmail.py`
- Test: `api/tests/test_mailbox.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (the access token is passed in).
- Produces:
  ```python
  @dataclass(frozen=True)
  class MailMessage:
      message_id: str
      thread_id: str
      from_address: str
      subject: str
      received_at: str | None    # ISO 8601
      body: str
      has_calendar_invite: bool

  @dataclass
  class FetchResult:
      messages: list[MailMessage]
      cursor: str | None
      partial: bool

  ATS_DOMAINS: tuple[str, ...]
  def build_query(days: int = 90) -> str: ...
  class GmailSource:
      def __init__(self, http, access_token: str) -> None: ...
      def fetch_new(self, cursor: str | None) -> FetchResult: ...
  ```

- [ ] **Step 1: Write the fake transport**

Create `api/tests/fake_gmail.py`:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Create `api/tests/test_mailbox.py`:

```python
from app.services.mailbox import GmailSource, build_query
from tests.fake_gmail import FakeGmail, message


def test_the_query_narrows_on_ats_senders_and_application_words():
    q = build_query(days=90)
    assert "newer_than:90d" in q
    assert "greenhouse.io" in q
    assert "myworkdayjobs.com" in q or "myworkday.com" in q
    assert "başvuru" in q
    assert "interview" in q


def test_a_first_sync_lists_messages_and_returns_a_cursor():
    gmail = FakeGmail([message("m1", subject="Application received")])
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.cursor == "9100"      # from users/me/profile
    assert result.partial is False


def test_a_message_carries_its_headers_and_decoded_body():
    gmail = FakeGmail([message("m1", sender="Acme HR <hr@acme.com>",
                                subject="Görüşme daveti", body="Merhaba Ada")])
    msg = GmailSource(gmail.client(), "at").fetch_new(None).messages[0]

    assert msg.from_address == "hr@acme.com"     # display name stripped
    assert msg.subject == "Görüşme daveti"
    assert msg.body == "Merhaba Ada"
    assert msg.thread_id == "t1"
    assert msg.received_at.startswith("2026-07-27")


def test_a_calendar_attachment_is_flagged():
    gmail = FakeGmail([message("m1", calendar=True)])
    assert GmailSource(gmail.client(), "at").fetch_new(None).messages[0].has_calendar_invite


def test_an_incremental_sync_only_fetches_what_history_reports():
    gmail = FakeGmail(
        [message("m1"), message("m2")],
        history={"historyId": "9200",
                 "history": [{"messagesAdded": [{"message": {"id": "m2", "threadId": "t1"}}]}]},
    )
    result = GmailSource(gmail.client(), "9100").fetch_new("9100")

    assert [m.message_id for m in result.messages] == ["m2"]
    assert result.cursor == "9200"


def test_an_expired_cursor_falls_back_to_a_full_query_scan():
    # Gmail keeps history for about a week; a stale cursor 404s.
    gmail = FakeGmail([message("m1")], history_status=404)
    result = GmailSource(gmail.client(), "at-old").fetch_new("1")

    assert [m.message_id for m in result.messages] == ["m1"]
    assert result.partial is False


def test_a_quota_error_returns_what_was_read_and_says_it_is_partial():
    gmail = FakeGmail([message("m1"), message("m2"), message("m3")], quota_after=1)
    result = GmailSource(gmail.client(), "at").fetch_new(None)

    assert len(result.messages) == 1
    assert result.partial is True
    # the cursor must not advance past unread mail
    assert result.cursor is None


def test_history_with_no_new_messages_returns_nothing_and_advances_the_cursor():
    gmail = FakeGmail([message("m1")], history={"historyId": "9300"})
    result = GmailSource(gmail.client(), "at").fetch_new("9100")

    assert result.messages == []
    assert result.cursor == "9300"
```

- [ ] **Step 3: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_mailbox.py -v`
Expected: FAIL — `No module named 'app.services.mailbox'`.

- [ ] **Step 4: Implement the source**

Create `api/app/services/mailbox.py`:

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_mailbox.py -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/mailbox.py tests/test_mailbox.py tests/fake_gmail.py
git commit -m "feat(api): read candidate mail from Gmail, incrementally"
```

---

### Task 6: The fixture corpus and the rule classifier

**Files:**
- Create: `api/tests/fixtures/mail/corpus.json`
- Create: `api/app/services/inbox_classify.py`
- Test: `api/tests/test_inbox_classify.py`

**Interfaces:**
- Consumes: `MailMessage` from Task 5.
- Produces:
  ```python
  Stage = Literal["received", "in_review", "interview", "offer", "rejected"]

  @dataclass(frozen=True)
  class Signal:
      stage: Stage | None
      company: str | None
      title: str | None
      confidence: float
      evidence: str
      job_related: bool

  def classify_by_rules(msg: MailMessage) -> Signal | None: ...
  ```
  `classify_by_rules` returns `None` when no rule fires or two stages tie — Task 7 turns that into the LLM call.

- [ ] **Step 1: Write the corpus**

Create `api/tests/fixtures/mail/corpus.json`. Each entry is `{id, from, subject, body, calendar, expect}` where `expect` is a stage, `"unsure"`, or `"ignore"`.

```json
[
  {"id": "gh-rej-en", "from": "no-reply@greenhouse.io",
   "subject": "Update on your application to Acme",
   "body": "Thank you for your interest in Acme. After careful review, we have decided to move forward with other candidates for the Backend Engineer role.",
   "calendar": false, "expect": "rejected"},

  {"id": "wd-rej-tr", "from": "noreply@myworkday.com",
   "subject": "Başvurunuz hakkında",
   "body": "Sayın Ada, Yazılım Mühendisi pozisyonuna yaptığınız başvuru olumsuz sonuçlanmıştır. İlginiz için teşekkür ederiz.",
   "calendar": false, "expect": "rejected"},

  {"id": "lever-rej-en", "from": "no-reply@lever.co",
   "subject": "Your application to Globex",
   "body": "We have decided not to proceed with your application at this time.",
   "calendar": false, "expect": "rejected"},

  {"id": "gh-ack-en", "from": "no-reply@greenhouse.io",
   "subject": "We received your application",
   "body": "Thanks for applying to Acme. We have received your application for Backend Engineer and will be in touch.",
   "calendar": false, "expect": "received"},

  {"id": "ashby-ack-tr", "from": "no-reply@ashbyhq.com",
   "subject": "Başvurunuz alındı",
   "body": "Merhaba, Initech için yaptığınız başvuru alınmıştır. Değerlendirme sonrası size döneceğiz.",
   "calendar": false, "expect": "received"},

  {"id": "lever-review-en", "from": "sara@globex.com",
   "subject": "Your application - next stage",
   "body": "Good news: you have been shortlisted and we are moving you to the next stage of the process for the Data Engineer role.",
   "calendar": false, "expect": "in_review"},

  {"id": "wd-review-tr", "from": "ik@initech.com.tr",
   "subject": "Başvurunuz değerlendirmede",
   "body": "Merhaba Ada, başvurunuz değerlendirmeye alındı. Bir sonraki aşama için sizinle iletişime geçeceğiz.",
   "calendar": false, "expect": "in_review"},

  {"id": "gh-interview-en", "from": "no-reply@greenhouse.io",
   "subject": "Interview invitation - Acme",
   "body": "We would love to schedule a call with you next week. Please book a time using the link below.",
   "calendar": true, "expect": "interview"},

  {"id": "ashby-interview-tr", "from": "ik@initech.com.tr",
   "subject": "Mülakat daveti",
   "body": "Merhaba Ada, sizi teknik mülakata davet etmek istiyoruz. Uygun olduğunuz saati seçebilir misiniz?",
   "calendar": false, "expect": "interview"},

  {"id": "offer-en", "from": "sara@globex.com",
   "subject": "Offer - Data Engineer at Globex",
   "body": "We are pleased to offer you the Data Engineer position at Globex. The details are attached.",
   "calendar": false, "expect": "offer"},

  {"id": "offer-tr", "from": "ik@initech.com.tr",
   "subject": "İş teklifi",
   "body": "Merhaba Ada, Yazılım Mühendisi pozisyonu için size iş teklifimizi sunmaktan mutluluk duyarız.",
   "calendar": false, "expect": "offer"},

  {"id": "newsletter", "from": "jobs-noreply@linkedin.com",
   "subject": "30 new jobs for Backend Engineer",
   "body": "Here are this week's recommended positions matching your profile.",
   "calendar": false, "expect": "ignore"},

  {"id": "cold-outreach", "from": "recruiter@headhunt.example",
   "subject": "Exciting position for you",
   "body": "I came across your profile and wanted to see if you would be open to a new opportunity.",
   "calendar": false, "expect": "ignore"},

  {"id": "personal", "from": "mom@example.com",
   "subject": "Yemek",
   "body": "Akşam gelecek misin?",
   "calendar": false, "expect": "ignore"},

  {"id": "ambiguous", "from": "ik@initech.com.tr",
   "subject": "Acme - başvurunuz",
   "body": "Merhaba Ada, süreçle ilgili size kısa bir güncelleme yapmak istedim.",
   "calendar": false, "expect": "unsure"}
]
```

- [ ] **Step 2: Write the failing tests**

Create `api/tests/test_inbox_classify.py`:

```python
import json
from pathlib import Path

import pytest

from app.services.inbox_classify import classify_by_rules
from app.services.mailbox import MailMessage

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "mail" / "corpus.json").read_text(encoding="utf-8")
)


def as_message(entry: dict) -> MailMessage:
    return MailMessage(
        message_id=entry["id"], thread_id="t-" + entry["id"],
        from_address=entry["from"], subject=entry["subject"],
        received_at="2026-07-27T10:00:00+00:00", body=entry["body"],
        has_calendar_invite=entry["calendar"],
    )


def entries(expect: str) -> list[dict]:
    return [e for e in CORPUS if e["expect"] == expect]


@pytest.mark.parametrize("entry", [e for e in CORPUS if e["expect"] not in ("unsure", "ignore")],
                         ids=lambda e: e["id"])
def test_rules_read_the_stage_from_real_ats_wording(entry):
    signal = classify_by_rules(as_message(entry))
    assert signal is not None, f"{entry['id']} produced no rule hit"
    assert signal.stage == entry["expect"]
    assert signal.evidence, "a stage without evidence cannot be justified to the user"


@pytest.mark.parametrize("entry", entries("ignore"), ids=lambda e: e["id"])
def test_non_application_mail_is_marked_not_job_related_or_left_unsure(entry):
    signal = classify_by_rules(as_message(entry))
    assert signal is None or signal.job_related is False


@pytest.mark.parametrize("entry", entries("unsure"), ids=lambda e: e["id"])
def test_vague_mail_abstains_rather_than_guessing(entry):
    assert classify_by_rules(as_message(entry)) is None


def test_rejection_wins_over_an_acknowledgement_in_the_same_mail():
    # ATS rejections routinely restate "we received your application" first.
    msg = as_message({
        "id": "mixed", "from": "no-reply@greenhouse.io", "subject": "Update",
        "body": ("We have received your application for Backend Engineer. "
                 "After review we have decided to move forward with other candidates."),
        "calendar": False,
    })
    assert classify_by_rules(msg).stage == "rejected"


def test_a_calendar_invite_alone_is_not_enough_to_call_it_an_interview():
    # Automated "add this to your calendar" footers exist; require wording too.
    msg = as_message({
        "id": "cal-only", "from": "ik@initech.com.tr", "subject": "Bilgilendirme",
        "body": "Merhaba, sürece dair genel bir bilgilendirme.", "calendar": True,
    })
    assert classify_by_rules(msg) is None


def test_the_evidence_is_the_sentence_that_decided_it():
    signal = classify_by_rules(as_message(entries("rejected")[0]))
    assert "move forward with other candidates" in signal.evidence.lower()
```

- [ ] **Step 3: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_classify.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the rules**

Create `api/app/services/inbox_classify.py`:

```python
"""Turning a mail into a stage.

Rules first: ATS templates are near-identical across employers, so most mail is
classifiable for free. The LLM (added in the next task) only sees what the rules
cannot settle. Silence is a valid answer — a wrong badge costs the user more
than a missing one.
"""
import re
from dataclasses import dataclass
from typing import Literal

from app.services.mailbox import ATS_DOMAINS, MailMessage

Stage = Literal["received", "in_review", "interview", "offer", "rejected"]

# Ordered most-decisive first: the first stage with a hit wins, which is why
# rejection outranks the acknowledgement wording ATS mails repeat above it.
STAGE_PATTERNS: tuple[tuple[Stage, tuple[str, ...]], ...] = (
    ("rejected", (
        r"move forward with other candidate",
        r"decided not to (proceed|move forward)",
        r"unfortunately.{0,40}(not|unable to) (be )?(proceed|continu|select)",
        r"will not be moving forward",
        r"olumsuz sonu[çc]lan",
        r"ba[şs]ka adaylarla (devam|ilerle)",
        r"de[ğg]erlendirmeye alamad",
        r"uygun bulunma",
    )),
    ("offer", (
        r"pleased to offer",
        r"we are happy to offer",
        r"offer letter",
        r"i[şs] teklif",
        r"teklifimizi sunmak",
    )),
    ("interview", (
        r"interview invitation",
        r"invite you to (an? )?(interview|conversation)",
        r"schedule a call",
        r"book a time",
        r"m[üu]lakat(a)? davet",
        r"g[öo]r[üu][şs]meye davet",
        r"teknik m[üu]lakat",
    )),
    ("in_review", (
        r"shortlisted",
        r"next stage",
        r"moving you (on )?to the next",
        r"under review by",
        r"de[ğg]erlendirmeye al[ıi]nd",
        r"bir sonraki a[şs]ama",
        r"s[üu]reciniz devam ediyor",
    )),
    ("received", (
        r"we have received your application",
        r"thanks? for applying",
        r"thank you for applying",
        r"application (has been )?received",
        r"ba[şs]vurunuz al[ıi]n",
        r"ba[şs]vurunuz i[çc]in te[şs]ekk[üu]r",
    )),
)

# Mail that mentions jobs but is not a response to one of ours.
NOT_A_RESPONSE: tuple[str, ...] = (
    r"new jobs? (for|matching)",
    r"recommended (jobs?|positions?)",
    r"jobs? (alert|digest)",
    r"came across your profile",
    r"would you be open to",
    r"yeni i[şs] ilanlar",
)

_COMPANY_FROM_SUBJECT = re.compile(
    r"(?:application to|apply to|position at|offer[^-]*at)\s+([A-Z][\w&.\- ]{1,40})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Signal:
    stage: Stage | None
    company: str | None
    title: str | None
    confidence: float
    evidence: str
    job_related: bool


def _haystack(msg: MailMessage) -> str:
    return f"{msg.subject}\n{msg.body[:2000]}"


def _sentence_containing(text: str, match: re.Match) -> str:
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()


def _from_ats(msg: MailMessage) -> bool:
    domain = msg.from_address.rsplit("@", 1)[-1]
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


def classify_by_rules(msg: MailMessage) -> Signal | None:
    """A confident stage, an explicit not-job-related, or None for 'ask the LLM'."""
    text = _haystack(msg)

    for pattern in NOT_A_RESPONSE:
        if re.search(pattern, text, re.IGNORECASE):
            return Signal(stage=None, company=None, title=None, confidence=0.9,
                          evidence="", job_related=False)

    for stage, patterns in STAGE_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # A calendar attachment corroborates an interview but never
                # establishes one on its own — automated footers carry them too.
                confidence = 0.95 if (stage != "interview" or msg.has_calendar_invite) else 0.85
                return Signal(
                    stage=stage,
                    company=_company_hint(msg),
                    title=None,
                    confidence=confidence,
                    evidence=_sentence_containing(text, match),
                    job_related=True,
                )
    return None


def _company_hint(msg: MailMessage) -> str | None:
    found = _COMPANY_FROM_SUBJECT.search(msg.subject)
    if found:
        return found.group(1).strip()
    domain = msg.from_address.rsplit("@", 1)[-1]
    if _from_ats(msg):
        return None          # the ATS domain names the vendor, not the employer
    return domain.split(".")[0].title() or None
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_classify.py -v`
Expected: PASS. If a corpus entry fails, fix the *pattern*, not the fixture — the fixture is the specification of real ATS wording.

- [ ] **Step 6: Commit**

```bash
git add app/services/inbox_classify.py tests/test_inbox_classify.py tests/fixtures/mail/corpus.json
git commit -m "feat(api): read application stages from ATS wording, TR and EN"
```

---

### Task 7: The LLM fallback

**Files:**
- Modify: `api/app/services/inbox_classify.py`
- Test: `api/tests/test_inbox_classify.py`

**Interfaces:**
- Consumes: `LLMClient`, `MODEL_FAST`, `LLMError` from `app.services.llm`; `classify_by_rules` from Task 6.
- Produces: `def classify(msg: MailMessage, llm: LLMClient | None) -> Signal: ...` — always returns a `Signal`; `stage=None` means unresolved.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_inbox_classify.py`:

```python
import json as _json

from app.services.inbox_classify import classify
from app.services.llm import LLMClient, LLMError
from tests.conftest import FakeOpenAI


def llm_saying(payload: dict) -> LLMClient:
    return LLMClient(FakeOpenAI([_json.dumps(payload)]))


def test_a_rule_hit_never_reaches_the_llm():
    fake = FakeOpenAI([])          # popping from an empty list would raise
    signal = classify(as_message(entries("rejected")[0]), LLMClient(fake))
    assert signal.stage == "rejected"
    assert fake.calls == []


def test_ambiguous_mail_is_resolved_by_the_llm():
    llm = llm_saying({"stage": "in_review", "company": "Acme", "title": "Backend Engineer",
                      "confidence": 0.8, "evidence": "süreçle ilgili güncelleme",
                      "job_related": True})
    signal = classify(as_message(entries("unsure")[0]), llm)
    assert signal.stage == "in_review"
    assert signal.company == "Acme"


def test_a_low_confidence_llm_answer_is_treated_as_unresolved():
    llm = llm_saying({"stage": "offer", "company": None, "title": None,
                      "confidence": 0.3, "evidence": "maybe", "job_related": True})
    assert classify(as_message(entries("unsure")[0]), llm).stage is None


def test_an_llm_answer_of_not_job_related_discards_the_mail():
    llm = llm_saying({"stage": None, "company": None, "title": None,
                      "confidence": 0.9, "evidence": "", "job_related": False})
    signal = classify(as_message(entries("unsure")[0]), llm)
    assert signal.job_related is False
    assert signal.stage is None


def test_an_llm_outage_leaves_the_stage_unresolved_instead_of_failing_the_sync():
    class Broken:
        def chat_json(self, *a, **k):
            raise LLMError("no quota")

    signal = classify(as_message(entries("unsure")[0]), Broken())
    assert signal.stage is None
    assert signal.job_related is True    # unknown, not disproven


def test_no_llm_available_still_returns_a_signal():
    assert classify(as_message(entries("unsure")[0]), None).stage is None


def test_the_llm_is_told_the_exact_stage_vocabulary():
    fake = FakeOpenAI([_json.dumps({"stage": "received", "company": None, "title": None,
                                    "confidence": 0.9, "evidence": "x", "job_related": True})])
    classify(as_message(entries("unsure")[0]), LLMClient(fake))
    system = fake.calls[0]["messages"][0]["content"]
    for stage in ("received", "in_review", "interview", "offer", "rejected"):
        assert stage in system
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_classify.py -v`
Expected: FAIL — `cannot import name 'classify'`.

- [ ] **Step 3: Implement the fallback**

Append to `api/app/services/inbox_classify.py` (and add the imports `import logging`, `from pydantic import BaseModel`, `from app.services.llm import MODEL_FAST, LLMClient, LLMError`, plus `logger = logging.getLogger(__name__)`):

```python
MIN_CONFIDENCE = 0.6

CLASSIFY_SYSTEM = """You read one email and decide what it says about a job application.

Reply with JSON only:
{"stage": one of "received" | "in_review" | "interview" | "offer" | "rejected" | null,
 "company": employer name or null,
 "title": job title or null,
 "confidence": 0.0-1.0,
 "evidence": the single sentence from the email that decided it,
 "job_related": true if this is a response to a job application the reader made}

Meanings:
- received: an automated acknowledgement that the application arrived.
- in_review: a human says the application is progressing or under consideration.
- interview: the reader is invited to talk, or asked to pick a time.
- offer: a job is being offered.
- rejected: the reader is not continuing in the process.

Set job_related to false for job-board newsletters, job alerts, and recruiter
cold outreach about roles the reader never applied to.

If the email does not clearly say any of these, return stage null with a low
confidence. Never guess: an invented stage is worse than no stage."""


class _LLMSignal(BaseModel):
    stage: str | None = None
    company: str | None = None
    title: str | None = None
    confidence: float = 0.0
    evidence: str = ""
    job_related: bool = True


UNRESOLVED = Signal(stage=None, company=None, title=None, confidence=0.0,
                    evidence="", job_related=True)


def classify(msg: MailMessage, llm: "LLMClient | None") -> Signal:
    """Always returns a Signal. `stage is None` means we could not tell."""
    ruled = classify_by_rules(msg)
    if ruled is not None:
        return ruled
    if llm is None:
        return UNRESOLVED

    user = (f"From: {msg.from_address}\n"
            f"Subject: {msg.subject}\n\n"
            f"{msg.body[:4000]}")
    try:
        answer = llm.chat_json(MODEL_FAST, CLASSIFY_SYSTEM, user, _LLMSignal)
    except LLMError as exc:
        # Quota or outage. The mail stays unclassified and is retried next sync;
        # the alternative — guessing — is the one outcome we refuse.
        logger.warning("[inbox] classifier LLM unavailable: %s", exc)
        return UNRESOLVED

    if not answer.job_related:
        return Signal(stage=None, company=None, title=None,
                      confidence=answer.confidence, evidence="", job_related=False)

    valid = answer.stage in ("received", "in_review", "interview", "offer", "rejected")
    if not valid or answer.confidence < MIN_CONFIDENCE:
        return UNRESOLVED

    return Signal(stage=answer.stage, company=answer.company, title=answer.title,
                  confidence=answer.confidence, evidence=answer.evidence,
                  job_related=True)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_classify.py -v`
Expected: PASS (all rule tests plus 7 new ones).

- [ ] **Step 5: Commit**

```bash
git add app/services/inbox_classify.py tests/test_inbox_classify.py
git commit -m "feat(api): ask the LLM only when the wording is genuinely ambiguous"
```

---

### Task 8: Matching a mail to an application

**Files:**
- Create: `api/app/services/inbox_match.py`
- Test: `api/tests/test_inbox_match.py`

**Interfaces:**
- Consumes: `MailMessage` (Task 5), `Signal` (Task 6).
- Produces:
  ```python
  def normalize_company(raw: str | None) -> str: ...
  def registrable_domain(value: str) -> str: ...   # accepts a URL or a bare domain

  @dataclass(frozen=True)
  class MatchResult:
      application: dict | None    # existing row, or None when one must be created
      reason: str                 # "thread" | "domain" | "company" | "new"

  def match_application(msg, signal, applications: list[dict],
                        threads: dict[str, str]) -> MatchResult: ...
  ```
  `threads` maps `thread_id -> application_id` from previously recorded events.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_inbox_match.py`:

```python
from app.services.inbox_classify import Signal
from app.services.inbox_match import (
    match_application, normalize_company, registrable_domain,
)
from app.services.mailbox import MailMessage


def mail(sender="hr@acme.com", thread="t1") -> MailMessage:
    return MailMessage(message_id="m1", thread_id=thread, from_address=sender,
                       subject="s", received_at=None, body="b",
                       has_calendar_invite=False)


def signal(company=None) -> Signal:
    return Signal(stage="rejected", company=company, title=None, confidence=0.9,
                  evidence="e", job_related=True)


def test_legal_suffixes_and_case_do_not_distinguish_companies():
    assert normalize_company("Acme A.Ş.") == normalize_company("ACME Inc.")
    assert normalize_company("Initech Ltd. Şti.") == normalize_company("initech")
    assert normalize_company("Globex GmbH") == normalize_company("Globex B.V.")


def test_turkish_characters_normalize_consistently():
    assert normalize_company("Öztürk Yazılım") == normalize_company("ozturk yazilim")


def test_normalizing_nothing_is_an_empty_string_not_a_crash():
    assert normalize_company(None) == ""


def test_the_registrable_domain_ignores_subdomains_and_schemes():
    assert registrable_domain("https://acme.wd3.myworkdayjobs.com/job/1") == "myworkdayjobs.com"
    assert registrable_domain("careers.acme.co.uk") == "acme.co.uk"
    assert registrable_domain("hr@acme.com") == "acme.com"


def test_a_known_thread_wins_over_everything_else():
    apps = [{"id": "a1", "url": "https://other.com/j", "company": "Other"},
            {"id": "a2", "url": "https://acme.com/j", "company": "Acme"}]
    result = match_application(mail(thread="t9"), signal("Acme"), apps, {"t9": "a1"})
    assert result.application["id"] == "a1"
    assert result.reason == "thread"


def test_the_sender_domain_matches_the_application_url():
    apps = [{"id": "a1", "url": "https://careers.acme.com/jobs/5", "company": None}]
    result = match_application(mail("no-reply@acme.com"), signal(), apps, {})
    assert result.application["id"] == "a1"
    assert result.reason == "domain"


def test_an_ats_sender_domain_does_not_match_an_unrelated_application():
    # Two applications both routed through Greenhouse must not collide.
    apps = [{"id": "a1", "url": "https://boards.greenhouse.io/globex/jobs/1",
             "company": "Globex"}]
    result = match_application(mail("no-reply@greenhouse.io"), signal("Acme"), apps, {})
    assert result.application is None
    assert result.reason == "new"


def test_the_company_name_matches_when_the_domain_cannot():
    apps = [{"id": "a1", "url": "https://boards.greenhouse.io/acme/jobs/1",
             "company": "Acme A.Ş."}]
    result = match_application(mail("no-reply@greenhouse.io"), signal("ACME Inc."), apps, {})
    assert result.application["id"] == "a1"
    assert result.reason == "company"


def test_no_match_asks_for_a_new_application():
    result = match_application(mail("hr@unknown.example"), signal("Unknown"), [], {})
    assert result.application is None
    assert result.reason == "new"


def test_a_blank_company_never_matches_an_application_with_a_blank_company():
    # Both empty must not be treated as equal, or every unmatched mail collides.
    apps = [{"id": "a1", "url": "https://x.example/j", "company": None}]
    result = match_application(mail("hr@other.example"), signal(None), apps, {})
    assert result.application is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_match.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement matching**

Create `api/app/services/inbox_match.py`:

```python
"""Deciding which application a mail belongs to.

Four steps, first hit wins. Step four is what makes the list complete rather
than merely accurate: an application made outside KRESUME appears the moment a
company replies to it.
"""
import re
import unicodedata
from dataclasses import dataclass

from tld import get_fld

from app.services.inbox_classify import Signal
from app.services.mailbox import ATS_DOMAINS, MailMessage

# Compared token by token after punctuation is stripped, so "A.Ş.", "AS" and
# "a.s." all collapse to the same thing. Matching on trailing substrings instead
# would mangle a company genuinely called "Sabancı".
LEGAL_TOKENS = frozenset({
    "as", "sti", "ltd", "limited", "sirketi", "anonim", "inc", "llc", "gmbh",
    "bv", "sa", "srl", "corp", "co", "company", "plc", "ag", "ab", "oy", "holding",
})

_TR_MAP = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def normalize_company(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.translate(_TR_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    tokens = [re.sub(r"[^a-z0-9]+", "", token) for token in text.split()]
    tokens = [t for t in tokens if t]
    kept = [t for t in tokens if t not in LEGAL_TOKENS]
    # A company literally named "Holding" would otherwise normalize to nothing
    # and then match every other empty name.
    return "".join(kept or tokens)


def registrable_domain(value: str) -> str:
    """The registrable domain of a URL, bare host, or email address."""
    if "@" in value and "://" not in value:
        value = value.rsplit("@", 1)[-1]
    if "://" not in value:
        value = "https://" + value
    return (get_fld(value, fail_silently=True) or "").lower()


def _is_ats(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


@dataclass(frozen=True)
class MatchResult:
    application: dict | None
    reason: str


def match_application(msg: MailMessage, signal: Signal, applications: list[dict],
                      threads: dict[str, str]) -> MatchResult:
    by_id = {a["id"]: a for a in applications}

    linked = threads.get(msg.thread_id)
    if linked and linked in by_id:
        return MatchResult(by_id[linked], "thread")

    sender_domain = registrable_domain(msg.from_address)
    # An ATS domain names the vendor, not the employer: two applications routed
    # through Greenhouse would otherwise collide into one.
    if sender_domain and not _is_ats(sender_domain):
        for app in applications:
            if registrable_domain(app.get("url") or "") == sender_domain:
                return MatchResult(app, "domain")

    wanted = normalize_company(signal.company)
    if wanted:
        for app in applications:
            if normalize_company(app.get("company")) == wanted:
                return MatchResult(app, "company")
        for app in applications:
            # The employer slug often sits in the ATS board URL:
            # boards.greenhouse.io/acme/jobs/1
            if wanted in re.sub(r"[^a-z0-9]+", "", (app.get("url") or "").casefold()):
                return MatchResult(app, "company")

    return MatchResult(None, "new")
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_match.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/inbox_match.py tests/test_inbox_match.py
git commit -m "feat(api): match a mail to its application, or admit it is a new one"
```

---

### Task 9: The stage machine

**Files:**
- Create: `api/app/services/inbox_stage.py`
- Test: `api/tests/test_inbox_stage.py`

**Interfaces:**
- Consumes: `Stage` from Task 6.
- Produces:
  ```python
  STAGE_ORDER: dict[str, int]
  def next_stage(current: str | None, detected: str | None) -> str | None: ...
      # returns the new stage, or None when nothing should change
  ```

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_inbox_stage.py`:

```python
import pytest

from app.services.inbox_stage import next_stage


@pytest.mark.parametrize("current,detected,expected", [
    ("received", "in_review", "in_review"),
    ("received", "interview", "interview"),
    ("in_review", "offer", "offer"),
    ("received", "rejected", "rejected"),
    ("interview", "rejected", "rejected"),
])
def test_a_later_stage_moves_the_application_forward(current, detected, expected):
    assert next_stage(current, detected) == expected


@pytest.mark.parametrize("current,detected", [
    ("interview", "received"),
    ("offer", "in_review"),
    ("in_review", "received"),
])
def test_a_delayed_earlier_mail_does_not_rewind_the_badge(current, detected):
    # Mail arrival order is not event order: an auto-acknowledgement can land
    # after an interview invitation.
    assert next_stage(current, detected) is None


def test_the_same_stage_twice_changes_nothing():
    assert next_stage("interview", "interview") is None


def test_rejection_is_terminal():
    for detected in ("received", "in_review", "interview", "offer"):
        assert next_stage("rejected", detected) is None


def test_an_unresolved_classification_changes_nothing():
    assert next_stage("received", None) is None


def test_an_application_with_no_stage_yet_takes_whatever_arrives():
    assert next_stage(None, "interview") == "interview"


def test_an_unknown_stage_string_is_refused_rather_than_stored():
    assert next_stage("received", "hired") is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_stage.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the machine**

Create `api/app/services/inbox_stage.py`:

```python
"""Stages move forward only, and rejection ends the story.

Mail arrival order is not event order: ATS acknowledgements are routinely
delivered late, and letting one rewind an interview badge would make the whole
feature look broken.
"""

STAGE_ORDER: dict[str, int] = {
    "received": 1, "in_review": 2, "interview": 3, "offer": 4,
}
TERMINAL = "rejected"


def next_stage(current: str | None, detected: str | None) -> str | None:
    """The stage to store, or None when the application should not change."""
    if detected is None:
        return None
    if detected != TERMINAL and detected not in STAGE_ORDER:
        return None          # not a stage we recognise; refuse to store it
    if current == TERMINAL:
        return None
    if detected == TERMINAL:
        return TERMINAL
    if current is None:
        return detected
    if current == TERMINAL or current not in STAGE_ORDER:
        return None
    return detected if STAGE_ORDER[detected] > STAGE_ORDER[current] else None
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_stage.py -v`
Expected: PASS (14 parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add app/services/inbox_stage.py tests/test_inbox_stage.py
git commit -m "feat(api): stages move forward only; rejection is terminal"
```

---

### Task 10: The sync orchestrator

**Files:**
- Create: `api/app/services/inbox_sync.py`
- Test: `api/tests/test_inbox_sync.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9.
- Produces:
  ```python
  @dataclass
  class SyncReport:
      scanned: int
      classified: int
      created: int
      updated: list[dict]     # {application_id, company, from_stage, to_stage}
      partial: bool

  def sync_user_inbox(db, http, llm, user_id: str,
                      source_factory=None) -> SyncReport: ...
  ```
  `source_factory(http, access_token) -> MailSource` exists so tests inject a fake source; production defaults to `GmailSource`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_inbox_sync.py`:

```python
import pytest

from app.services.inbox_connect import ConnectionError_, encrypt_token
from app.services.inbox_sync import sync_user_inbox
from app.services.mailbox import FetchResult, MailMessage
from tests.test_inbox_connect import FakeDB, http_returning


class FakeSource:
    def __init__(self, result: FetchResult):
        self._result = result
        self.cursors: list[str | None] = []

    def fetch_new(self, cursor):
        self.cursors.append(cursor)
        return self._result


def mail(msg_id="m1", sender="no-reply@greenhouse.io", subject="Update",
         body="We have decided to move forward with other candidates.",
         thread="t1") -> MailMessage:
    return MailMessage(message_id=msg_id, thread_id=thread, from_address=sender,
                       subject=subject, received_at="2026-07-27T10:00:00+00:00",
                       body=body, has_calendar_invite=False)


class InboxDB(FakeDB):
    """FakeDB plus per-table routing, which the sync needs."""

    def __init__(self, connections=None, applications=None, events=None):
        super().__init__()
        self.tables = {
            "email_connections": list(connections or []),
            "applications": list(applications or []),
            "application_events": list(events or []),
        }

    def select(self, table, params):
        return list(self.tables[table])

    def insert(self, table, row, *, on_conflict=None):
        if on_conflict and any(
            r.get("message_id") == row.get("message_id") for r in self.tables[table]
        ):
            return None
        self.inserted.append((table, row))
        stored = dict(row, id=row.get("id", f"{table}-{len(self.tables[table])}"))
        self.tables[table].append(stored)
        return stored

    def update(self, table, params, patch):
        self.updated.append((table, params, patch))
        target = params.get("id", "").removeprefix("eq.")
        for r in self.tables[table]:
            if not target or r.get("id") == target:
                r.update(patch)
        return self.tables[table]

    def delete(self, table, params):
        self.deleted.append((table, params))


def connected_db(**kwargs) -> InboxDB:
    return InboxDB(
        connections=[{"user_id": "u1", "refresh_token_enc": encrypt_token("1//rt"),
                      "last_history_id": "9100", "status": "active"}],
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_TOKEN_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


def test_a_rejection_moves_a_matching_application_and_says_so():
    db = connected_db(applications=[
        {"id": "a1", "url": "https://boards.greenhouse.io/acme/jobs/1",
         "company": "Acme", "stage": "received"},
    ])
    source = FakeSource(FetchResult([mail(subject="Your application to Acme")],
                                     cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.scanned == 1
    assert report.updated == [{"application_id": "a1", "company": "Acme",
                               "from_stage": "received", "to_stage": "rejected"}]
    assert ("applications", {"id": "eq.a1"}, ) == db.updated[0][:2]
    assert db.updated[0][2]["stage"] == "rejected"


def test_every_processed_mail_is_recorded_even_when_nothing_moves():
    db = connected_db(applications=[
        {"id": "a1", "url": "https://acme.com/j", "company": "Acme", "stage": "rejected"},
    ])
    source = FakeSource(FetchResult([mail(sender="hr@acme.com")],
                                     cursor="9200", partial=False))

    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)

    events = [row for table, row in db.inserted if table == "application_events"]
    assert len(events) == 1
    assert events[0]["detected_stage"] == "rejected"
    assert events[0]["evidence"]
    assert db.updated == [] or db.updated[0][1] != {"id": "eq.a1"}


def test_an_unmatched_mail_creates_an_external_application():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="hr@initech.com.tr", subject="Initech - başvurunuz",
              body="Başvurunuz olumsuz sonuçlanmıştır.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.created == 1
    created = [row for table, row in db.inserted if table == "applications"][0]
    assert created["source"] == "email"
    assert created["status"] == "external"
    assert created["stage"] == "rejected"
    assert created["user_id"] == "u1"


def test_a_mail_the_classifier_cannot_read_creates_nothing():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="hr@initech.com.tr", subject="Bilgilendirme",
              body="Merhaba, kısa bir güncelleme.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.created == 0
    assert report.updated == []
    assert [t for t, _ in db.inserted] == []   # not even an orphan event


def test_a_mail_that_is_not_job_related_is_skipped_entirely():
    db = connected_db()
    source = FakeSource(FetchResult(
        [mail(sender="jobs-noreply@linkedin.com", subject="30 new jobs",
              body="Here are this week's recommended jobs for you.")],
        cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.classified == 0
    assert db.inserted == []


def test_the_same_message_seen_twice_cannot_advance_a_stage_twice():
    db = connected_db(
        applications=[{"id": "a1", "url": "https://acme.com/j", "company": "Acme",
                       "stage": "received"}],
        events=[{"message_id": "m1", "thread_id": "t1", "application_id": "a1"}],
    )
    source = FakeSource(FetchResult([mail(sender="hr@acme.com")],
                                     cursor="9200", partial=False))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.updated == []
    assert report.scanned == 1


def test_the_cursor_and_sync_time_are_stored_after_a_clean_run():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor="9200", partial=False))

    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)

    patch = [p for table, _, p in db.updated if table == "email_connections"][0]
    assert patch["last_history_id"] == "9200"
    assert patch["last_synced_at"]


def test_a_partial_fetch_does_not_advance_the_cursor():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor=None, partial=True))

    report = sync_user_inbox(db, http_returning((200, {"access_token": "at"})),
                             None, "u1", source_factory=lambda *_: source)

    assert report.partial is True
    patch = [p for table, _, p in db.updated if table == "email_connections"][0]
    assert "last_history_id" not in patch


def test_the_stored_cursor_is_handed_to_the_source():
    db = connected_db()
    source = FakeSource(FetchResult([], cursor="9200", partial=False))
    sync_user_inbox(db, http_returning((200, {"access_token": "at"})), None, "u1",
                    source_factory=lambda *_: source)
    assert source.cursors == ["9100"]


def test_a_revoked_grant_surfaces_instead_of_returning_an_empty_report():
    db = connected_db()
    with pytest.raises(ConnectionError_):
        sync_user_inbox(db, http_returning((400, {"error": "invalid_grant"})),
                        None, "u1", source_factory=lambda *_: FakeSource(
                            FetchResult([], cursor=None, partial=False)))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_sync.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the orchestrator**

Create `api/app/services/inbox_sync.py`:

```python
"""The one function that runs a sync.

Everything else in this feature is a pure unit or a thin client; this is where
they meet. When background scanning is added later, cron calls this same
function and nothing else moves.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.inbox_classify import classify
from app.services.inbox_connect import access_token_for
from app.services.inbox_match import match_application
from app.services.inbox_stage import next_stage
from app.services.mailbox import GmailSource

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    scanned: int = 0
    classified: int = 0
    created: int = 0
    updated: list[dict] = field(default_factory=list)
    partial: bool = False


def _default_source(http, access_token):
    return GmailSource(http, access_token)


def sync_user_inbox(db, http, llm, user_id: str, source_factory=None) -> SyncReport:
    source_factory = source_factory or _default_source

    connections = db.select("email_connections",
                            {"user_id": f"eq.{user_id}", "select": "*"})
    if not connections:
        return SyncReport()
    connection = connections[0]

    # Raises ConnectionError_ when the user revoked us at Google; the router
    # turns that into a message rather than a silent empty result.
    access_token = access_token_for(db, http, user_id)

    fetched = source_factory(http, access_token).fetch_new(connection.get("last_history_id"))

    applications = db.select("applications", {"user_id": f"eq.{user_id}", "select": "*"})
    events = db.select("application_events",
                       {"user_id": f"eq.{user_id}", "select": "message_id,thread_id,application_id"})
    seen = {e["message_id"] for e in events}
    threads = {e["thread_id"]: e["application_id"] for e in events if e.get("thread_id")}

    report = SyncReport(partial=fetched.partial)

    for msg in fetched.messages:
        report.scanned += 1
        if msg.message_id in seen:
            continue

        signal = classify(msg, llm)
        if not signal.job_related:
            continue
        report.classified += 1
        if signal.stage is None:
            # Nothing to attach an event to, and no stage to record. Leave it
            # for a later sync rather than inventing an application.
            continue

        matched = match_application(msg, signal, applications, threads)
        application = matched.application
        if application is None:
            application = db.insert("applications", {
                "user_id": user_id,
                "url": "",
                "company": signal.company,
                "title": signal.title,
                "status": "external",
                "source": "email",
                "stage": signal.stage,
                "stage_updated_at": _now(),
                "qa": {},
                "changes": [],
            })
            applications.append(application)
            report.created += 1
        else:
            moved = next_stage(application.get("stage"), signal.stage)
            if moved:
                db.update("applications", {"id": f"eq.{application['id']}"},
                          {"stage": moved, "stage_updated_at": _now()})
                report.updated.append({
                    "application_id": application["id"],
                    "company": application.get("company"),
                    "from_stage": application.get("stage"),
                    "to_stage": moved,
                })
                application["stage"] = moved

        db.insert("application_events", {
            "user_id": user_id,
            "application_id": application["id"],
            "source": "email",
            "message_id": msg.message_id,
            "thread_id": msg.thread_id,
            "from_address": msg.from_address,
            "subject": msg.subject,
            "received_at": msg.received_at,
            "detected_stage": signal.stage,
            "confidence": signal.confidence,
            "evidence": signal.evidence,
        }, on_conflict="user_id,message_id")
        seen.add(msg.message_id)
        threads[msg.thread_id] = application["id"]

    patch = {"last_synced_at": _now()}
    if not fetched.partial and fetched.cursor:
        # A truncated fetch must re-read its tail next time, so the cursor only
        # advances on a clean run.
        patch["last_history_id"] = fetched.cursor
    db.update("email_connections", {"user_id": f"eq.{user_id}"}, patch)

    return report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_sync.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Run the whole API suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/services/inbox_sync.py tests/test_inbox_sync.py
git commit -m "feat(api): sync a user's inbox into application stages"
```

---

### Task 11: The HTTP surface

**Files:**
- Create: `api/app/routers/inbox.py`
- Modify: `api/app/main.py`
- Modify: `api/README.md`
- Test: `api/tests/test_inbox_router.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_db`, `get_llm`, and the inbox services.
- Produces: `POST /inbox/connect`, `DELETE /inbox/connect`, `GET /inbox/status`, `POST /inbox/sync`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_inbox_router.py`:

```python
from app.main import app
from app.services.inbox_connect import ConnectionError_
from app.services.supabase_db import get_db
from tests.test_inbox_sync import InboxDB


def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    return db


def test_status_requires_authentication(client):
    assert client.get("/inbox/status").status_code == 401


def test_status_reports_a_disconnected_mailbox(client, auth_headers):
    override_db(InboxDB())
    resp = client.get("/inbox/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "email": None,
                           "last_synced_at": None, "status": None}


def test_sync_returns_what_changed(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    from app.services.inbox_sync import SyncReport
    monkeypatch.setattr(router_mod, "sync_user_inbox",
                        lambda *a, **k: SyncReport(scanned=3, classified=2, created=1,
                                                   updated=[{"application_id": "a1"}],
                                                   partial=False))

    resp = client.post("/inbox/sync", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"scanned": 3, "classified": 2, "created": 1,
                           "updated": [{"application_id": "a1"}], "partial": False}


def test_a_revoked_grant_is_a_named_error_the_ui_can_translate(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod

    def boom(*a, **k):
        raise ConnectionError_("gone")

    monkeypatch.setattr(router_mod, "sync_user_inbox", boom)
    resp = client.post("/inbox/sync", headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "GMAIL_DISCONNECTED"}


def test_connect_passes_the_code_and_redirect_through(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    seen = {}

    def fake_connect(db, http, user_id, code, redirect_uri):
        seen.update(user_id=user_id, code=code, redirect_uri=redirect_uri)
        return {"connected": True, "email": "ada@example.com"}

    monkeypatch.setattr(router_mod, "connect_gmail", fake_connect)
    resp = client.post("/inbox/connect", headers=auth_headers,
                       json={"code": "abc", "redirect_uri": "http://localhost:3000/cb"})

    assert resp.status_code == 200
    assert resp.json() == {"connected": True, "email": "ada@example.com"}
    assert seen["code"] == "abc"
    assert seen["user_id"] == "user-1"


def test_a_refused_authorization_code_is_reported_as_such(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod

    def boom(*a, **k):
        raise ConnectionError_("no refresh token")

    monkeypatch.setattr(router_mod, "connect_gmail", boom)
    resp = client.post("/inbox/connect", headers=auth_headers,
                       json={"code": "abc", "redirect_uri": "http://x"})

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "GMAIL_DISCONNECTED"}


def test_disconnect_removes_the_connection(client, auth_headers, monkeypatch):
    override_db(InboxDB())
    import app.routers.inbox as router_mod
    called = []
    monkeypatch.setattr(router_mod, "disconnect_gmail",
                        lambda db, http, user_id: called.append(user_id))

    assert client.delete("/inbox/connect", headers=auth_headers).status_code == 200
    assert called == ["user-1"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_router.py -v`
Expected: FAIL — 404 on every route.

- [ ] **Step 3: Write the router**

Create `api/app/routers/inbox.py`:

```python
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.inbox_connect import (
    ConnectionError_, connect_gmail, connection_status, disconnect_gmail,
)
from app.services.inbox_sync import sync_user_inbox
from app.services.llm import LLMClient, get_llm
from app.services.supabase_db import SupabaseDB, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["inbox"])


def get_http() -> httpx.Client:
    return httpx.Client(timeout=30.0)


class ConnectRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/connect")
def connect(
    req: ConnectRequest,
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
):
    try:
        return connect_gmail(db, http, user_id, req.code, req.redirect_uri)
    except ConnectionError_ as exc:
        logger.warning("[inbox] connect failed for %s: %s", user_id, exc)
        raise HTTPException(status_code=409, detail={"code": "GMAIL_DISCONNECTED"})


@router.delete("/connect")
def disconnect(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
):
    disconnect_gmail(db, http, user_id)
    return {"connected": False}


@router.get("/status")
def status(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
):
    return connection_status(db, user_id)


@router.post("/sync")
def sync(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
    llm: LLMClient = Depends(get_llm),
):
    try:
        report = sync_user_inbox(db, http, llm, user_id)
    except ConnectionError_ as exc:
        # The grant is gone. Say so, so the UI can offer reconnection instead of
        # showing stale stages forever.
        logger.warning("[inbox] sync blocked for %s: %s", user_id, exc)
        raise HTTPException(status_code=409, detail={"code": "GMAIL_DISCONNECTED"})
    return {
        "scanned": report.scanned,
        "classified": report.classified,
        "created": report.created,
        "updated": report.updated,
        "partial": report.partial,
    }
```

- [ ] **Step 4: Register it**

In `api/app/main.py`, add the import next to the others and the include at the bottom:

```python
from app.routers import inbox as inbox_router
```

```python
app.include_router(inbox_router.router)
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_inbox_router.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Document the new env vars**

In `api/README.md`, extend the `.env` block:

```
    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_SERVICE_KEY=...   # service_role key; server-only, never in the web app
    EMAIL_TOKEN_KEY=...        # Fernet key encrypting stored Gmail refresh tokens
    GOOGLE_CLIENT_ID=...       # our own OAuth client, not Supabase's
    GOOGLE_CLIENT_SECRET=...
```

And add, under the endpoint list:

```markdown
## Inbox status tracking

- `POST /inbox/connect` — exchange a Google authorization code for a stored,
  encrypted refresh token. Requires `access_type=offline&prompt=consent` on the
  consent URL, or Google returns no refresh token and the call fails.
- `DELETE /inbox/connect` — revoke at Google, then delete the row.
- `GET /inbox/status` — `{connected, email, last_synced_at, status}`.
- `POST /inbox/sync` — scan new mail, update application stages, return what
  changed. Returns 409 `GMAIL_DISCONNECTED` when the grant is gone.

Generate the token key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

`gmail.readonly` is a Google restricted scope: it works for test users added in
the Google Cloud console, but publishing to general users requires OAuth
verification and an annual CASA assessment.
```

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv\Scripts\python -m pytest -q`
Expected: PASS.

```bash
git add app/routers/inbox.py app/main.py api/README.md tests/test_inbox_router.py
git commit -m "feat(api): inbox connect, status, and sync endpoints"
```

---

### Task 12: Web API client and the OAuth landing route

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/lib/errors.ts`
- Create: `web/src/app/auth/gmail/callback/route.ts`
- Create: `web/src/lib/gmailOAuth.ts`
- Test: `web/src/lib/__tests__/gmailOAuth.test.ts`

**Interfaces:**
- Consumes: `POST /inbox/*` from Task 11.
- Produces:
  ```ts
  // lib/gmailOAuth.ts
  export function gmailConsentUrl(clientId: string, redirectUri: string): string
  export const GMAIL_REDIRECT_PATH = '/auth/gmail/callback'

  // lib/api.ts
  export interface InboxStatus { connected: boolean; email: string | null; last_synced_at: string | null; status: 'active'|'revoked'|'error'|null }
  export interface SyncReport { scanned: number; classified: number; created: number; updated: {application_id: string; company: string|null; from_stage: string; to_stage: string}[]; partial: boolean }
  export function inboxStatus(): Promise<InboxStatus>
  export function inboxSync(): Promise<SyncReport>
  export function inboxConnect(code: string, redirectUri: string): Promise<{connected: boolean; email: string}>
  export function inboxDisconnect(): Promise<void>
  ```

- [ ] **Step 1: Write the failing test**

Create `web/src/lib/__tests__/gmailOAuth.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { gmailConsentUrl } from '@/lib/gmailOAuth'

describe('gmailConsentUrl', () => {
  const url = () => new URL(gmailConsentUrl('client-123', 'http://localhost:3000/auth/gmail/callback'))

  it('asks for offline access so the token survives the session', () => {
    expect(url().searchParams.get('access_type')).toBe('offline')
  })

  it('forces the consent screen so Google always returns a refresh token', () => {
    // Without this, a repeat grant omits refresh_token and the connection dies silently.
    expect(url().searchParams.get('prompt')).toBe('consent')
  })

  it('requests read-only Gmail and nothing else', () => {
    expect(url().searchParams.get('scope')).toBe('https://www.googleapis.com/auth/gmail.readonly')
  })

  it('carries the client id and redirect', () => {
    expect(url().searchParams.get('client_id')).toBe('client-123')
    expect(url().searchParams.get('redirect_uri')).toBe('http://localhost:3000/auth/gmail/callback')
    expect(url().searchParams.get('response_type')).toBe('code')
  })
})
```

- [ ] **Step 2: Run it and watch it fail**

Run: `npm test -- src/lib/__tests__/gmailOAuth.test.ts`
Expected: FAIL — cannot resolve `@/lib/gmailOAuth`.

- [ ] **Step 3: Implement the consent URL**

Create `web/src/lib/gmailOAuth.ts`:

```ts
export const GMAIL_REDIRECT_PATH = '/auth/gmail/callback'
export const GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'

export function gmailConsentUrl(clientId: string, redirectUri: string): string {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: GMAIL_SCOPE,
    access_type: 'offline',
    // Google omits refresh_token on a repeat grant unless consent is forced,
    // which would leave us with a connection that dies in an hour.
    prompt: 'consent',
    include_granted_scopes: 'true',
  })
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`
}
```

- [ ] **Step 4: Add the API calls**

Append to `web/src/lib/api.ts`:

```ts
export interface InboxStatus {
  connected: boolean
  email: string | null
  last_synced_at: string | null
  status: 'active' | 'revoked' | 'error' | null
}

export interface SyncReport {
  scanned: number
  classified: number
  created: number
  updated: { application_id: string; company: string | null; from_stage: string; to_stage: string }[]
  partial: boolean
}

export async function inboxStatus(): Promise<InboxStatus> {
  const res = await ensureOk(await fetch(apiUrl('/inbox/status'), { headers: await authHeaders() }))
  return res.json()
}

export async function inboxSync(): Promise<SyncReport> {
  const res = await ensureOk(
    await fetch(apiUrl('/inbox/sync'), { method: 'POST', headers: await authHeaders() })
  )
  return res.json()
}

export async function inboxConnect(code: string, redirectUri: string): Promise<{ connected: boolean; email: string }> {
  const res = await ensureOk(
    await fetch(apiUrl('/inbox/connect'), {
      method: 'POST',
      headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    })
  )
  return res.json()
}

export async function inboxDisconnect(): Promise<void> {
  await ensureOk(
    await fetch(apiUrl('/inbox/connect'), { method: 'DELETE', headers: await authHeaders() })
  )
}
```

- [ ] **Step 5: Map the new error code**

In `web/src/lib/errors.ts`, add the code to `KNOWN_CODES`:

```ts
  'SESSION_NOT_FOUND', 'FORBIDDEN', 'TOO_MANY_SESSIONS',
  // the Gmail grant is gone — the user revoked it, or never finished consent
  'GMAIL_DISCONNECTED', 'UNKNOWN',
```

- [ ] **Step 6: Write the callback route**

Create `web/src/app/auth/gmail/callback/route.ts`:

```ts
import { NextResponse, type NextRequest } from 'next/server'

// Google lands here with ?code=... . The code is useless without our client
// secret, which lives only in the API, so we hand it to the applications page
// and let the browser (which holds the Supabase session) complete the exchange.
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code')
  const error = request.nextUrl.searchParams.get('error')
  const target = new URL('/applications', request.nextUrl.origin)

  if (error || !code) {
    target.searchParams.set('gmail', 'denied')
  } else {
    target.searchParams.set('gmail_code', code)
  }
  return NextResponse.redirect(target)
}
```

- [ ] **Step 7: Run the tests and typecheck**

Run: `npm test && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/gmailOAuth.ts web/src/lib/api.ts web/src/lib/errors.ts web/src/app/auth/gmail/callback/route.ts web/src/lib/__tests__/gmailOAuth.test.ts
git commit -m "feat(web): Gmail consent flow and inbox API client"
```

---

### Task 13: The Başvurularım page

**Files:**
- Create: `web/src/app/(app)/applications/page.tsx`
- Create: `web/src/components/applications/StageBadge.tsx`
- Create: `web/src/components/applications/ConnectGmailCard.tsx`
- Create: `web/src/components/applications/ApplicationCard.tsx`
- Modify: `web/src/components/AppSidebar.tsx`, `web/src/lib/protected.ts`, `web/src/messages/tr.json`, `web/src/messages/en.json`
- Test: `web/src/app/(app)/applications/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: `listApplications`, `listApplicationEvents` (Task 1); `inboxStatus`, `inboxSync`, `inboxConnect`, `gmailConsentUrl` (Task 12).
- Produces: the `/applications` route.

- [ ] **Step 1: Add the translations**

In `web/src/messages/tr.json`, add a top-level `"applications"` block:

```json
  "applications": {
    "title": "Başvurularım",
    "intro": "Gmail'ini bağla, şirketlerden gelen cevapları burada topluca gör.",
    "connect": "Gmail'i bağla",
    "connectExplain": "Sadece başvuru maillerini okuruz — hiçbir mail göndermez, silmez ve kişisel yazışmalarını indirmeyiz. İstediğin an bağlantıyı kesebilirsin.",
    "connected": "Gmail'e bağlı",
    "disconnect": "Bağlantıyı kes",
    "refresh": "Yenile",
    "refreshing": "Gelen kutusu taranıyor…",
    "syncedAt": "{time} güncellendi",
    "neverSynced": "Henüz taranmadı",
    "partial": "Kısmen güncellendi — Gmail sınırına takıldık, birazdan tekrar dene.",
    "denied": "Gmail bağlantısına izin verilmedi.",
    "revoked": "Gmail bağlantın sona ermiş. Yeniden bağla.",
    "empty": "Henüz başvuru yok.",
    "why": "Neden?",
    "noEvents": "Bu başvuru için henüz bir e-posta görmedik.",
    "eventFrom": "Gönderen",
    "unknownCompany": "Şirket belirtilmemiş",
    "stage": {
      "received": "Alındı",
      "in_review": "Değerlendirmede",
      "interview": "Mülakat",
      "offer": "Teklif",
      "rejected": "Ret"
    }
  },
```

In `web/src/messages/en.json`, the same block:

```json
  "applications": {
    "title": "My applications",
    "intro": "Connect Gmail and see every company's reply in one place.",
    "connect": "Connect Gmail",
    "connectExplain": "We only read application emails — we never send or delete anything, and we don't download your personal correspondence. Disconnect whenever you like.",
    "connected": "Gmail connected",
    "disconnect": "Disconnect",
    "refresh": "Refresh",
    "refreshing": "Scanning your inbox…",
    "syncedAt": "updated {time}",
    "neverSynced": "Not scanned yet",
    "partial": "Partially updated — we hit a Gmail limit. Try again shortly.",
    "denied": "Gmail access was not granted.",
    "revoked": "Your Gmail connection has expired. Reconnect to continue.",
    "empty": "No applications yet.",
    "why": "Why?",
    "noEvents": "We haven't seen an email for this application yet.",
    "eventFrom": "From",
    "unknownCompany": "Company not stated",
    "stage": {
      "received": "Received",
      "in_review": "In review",
      "interview": "Interview",
      "offer": "Offer",
      "rejected": "Rejected"
    }
  },
```

Also add `"applications": "Başvurularım"` to the `sidebar` block in `tr.json` and `"applications": "My applications"` in `en.json`, and `"GMAIL_DISCONNECTED"` to the `errors` block in both (`"Gmail bağlantın sona ermiş. Yeniden bağla."` / `"Your Gmail connection has expired. Reconnect to continue."`).

- [ ] **Step 2: Write the failing page tests**

Create `web/src/app/(app)/applications/__tests__/page.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { renderWithIntl } from '@/test/utils'
import ApplicationsPage from '../page'

// Same shape as the dashboard test: a stable router identity, plus the search
// params the OAuth callback lands with.
const searchParams = new URLSearchParams()
vi.mock('next/navigation', () => {
  const router = { push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }
  return { useRouter: () => router, useSearchParams: () => searchParams }
})

const listApplications = vi.fn()
const listApplicationEvents = vi.fn()
vi.mock('@/lib/db', () => ({
  listApplications: (...a: unknown[]) => listApplications(...a),
  listApplicationEvents: (...a: unknown[]) => listApplicationEvents(...a),
}))

const inboxStatus = vi.fn()
const inboxSync = vi.fn()
const inboxConnect = vi.fn()
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  inboxStatus: (...a: unknown[]) => inboxStatus(...a),
  inboxSync: (...a: unknown[]) => inboxSync(...a),
  inboxConnect: (...a: unknown[]) => inboxConnect(...a),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) } }),
}))

const application = (over = {}) => ({
  id: 'a1', user_id: 'u1', url: 'https://acme.com/j', company: 'Acme',
  title: 'Backend Engineer', stage: 'rejected', stage_updated_at: '2026-07-27T10:00:00Z',
  source: 'email', status: 'external', cv_id: null, optimized_cv_id: null,
  job_text: null, cover_letter: null, qa: {}, changes: [],
  created_at: '2026-07-20T10:00:00Z', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  listApplications.mockResolvedValue([])
  listApplicationEvents.mockResolvedValue([])
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: new Date().toISOString(), status: 'active' })
  inboxSync.mockResolvedValue({ scanned: 0, classified: 0, created: 0, updated: [], partial: false })
})

it('offers to connect Gmail when no mailbox is linked', async () => {
  inboxStatus.mockResolvedValue({ connected: false, email: null, last_synced_at: null, status: null })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByRole('link', { name: "Gmail'i bağla" })).toBeInTheDocument()
  expect(screen.getByText(/kişisel yazışmalarını indirmeyiz/)).toBeInTheDocument()
})

it('shows each application with its stage', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText('Acme')).toBeInTheDocument()
  expect(screen.getByText('Backend Engineer')).toBeInTheDocument()
  expect(screen.getByText('Ret')).toBeInTheDocument()
})

it('reveals the email behind a stage when asked why', async () => {
  listApplications.mockResolvedValue([application()])
  listApplicationEvents.mockResolvedValue([{
    id: 'e1', subject: 'Update on your application', from_address: 'no-reply@greenhouse.io',
    received_at: '2026-07-27T10:00:00Z', detected_stage: 'rejected',
    evidence: 'We have decided to move forward with other candidates.',
  }])
  renderWithIntl(<ApplicationsPage />)

  await userEvent.click(await screen.findByRole('button', { name: 'Neden?' }))

  expect(await screen.findByText(/move forward with other candidates/)).toBeInTheDocument()
  expect(screen.getByText(/no-reply@greenhouse.io/)).toBeInTheDocument()
})

it('syncs on demand and reloads the list', async () => {
  listApplications.mockResolvedValue([application()])
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Acme')
  listApplications.mockClear()

  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))

  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
  await waitFor(() => expect(listApplications).toHaveBeenCalled())
})

it('does not sync on open when the last scan is recent', async () => {
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await waitFor(() => expect(inboxStatus).toHaveBeenCalled())
  expect(inboxSync).not.toHaveBeenCalled()
})

it('syncs on open when the last scan is stale', async () => {
  inboxStatus.mockResolvedValue({
    connected: true, email: 'ada@example.com', status: 'active',
    last_synced_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  })
  renderWithIntl(<ApplicationsPage />)
  await waitFor(() => expect(inboxSync).toHaveBeenCalled())
})

it('tells the user when the connection has been revoked', async () => {
  inboxStatus.mockResolvedValue({ connected: true, email: 'ada@example.com',
    last_synced_at: null, status: 'revoked' })
  renderWithIntl(<ApplicationsPage />)
  expect(await screen.findByText(/Gmail bağlantın sona ermiş/)).toBeInTheDocument()
})

it('says so when a sync was cut short', async () => {
  inboxSync.mockResolvedValue({ scanned: 5, classified: 2, created: 0, updated: [], partial: true })
  renderWithIntl(<ApplicationsPage />)
  await screen.findByText('Başvurularım')
  await userEvent.click(screen.getByRole('button', { name: 'Yenile' }))
  expect(await screen.findByText(/Kısmen güncellendi/)).toBeInTheDocument()
})
```

- [ ] **Step 3: Run them and watch them fail**

Run: `npm test -- src/app/\(app\)/applications`
Expected: FAIL — cannot resolve `../page`.

- [ ] **Step 4: Build the stage badge**

Create `web/src/components/applications/StageBadge.tsx`:

```tsx
'use client'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import type { ApplicationStage } from '@/types/db'

const TONE: Record<ApplicationStage, string> = {
  received: 'bg-muted text-muted-foreground ring-border',
  in_review: 'bg-primary/8 text-primary ring-primary/15',
  interview: 'bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400',
  offer: 'bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400',
  rejected: 'bg-destructive/8 text-destructive ring-destructive/15',
}

export function StageBadge({ stage }: { stage: ApplicationStage }) {
  const t = useTranslations('applications.stage')
  return (
    <span className={cn('shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1',
                        TONE[stage])}>
      {t(stage)}
    </span>
  )
}
```

- [ ] **Step 5: Build the connect card**

Create `web/src/components/applications/ConnectGmailCard.tsx`:

```tsx
'use client'
import { useTranslations } from 'next-intl'
import { Mail } from 'lucide-react'
import { GMAIL_REDIRECT_PATH, gmailConsentUrl } from '@/lib/gmailOAuth'

export function ConnectGmailCard() {
  const t = useTranslations('applications')
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? ''
  const redirect = typeof window === 'undefined'
    ? GMAIL_REDIRECT_PATH
    : window.location.origin + GMAIL_REDIRECT_PATH

  return (
    <section className="grain flex flex-col items-start gap-4 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-8">
      <span className="grid size-11 place-items-center rounded-full bg-primary/8 text-primary ring-1 ring-primary/12">
        <Mail aria-hidden className="size-5" />
      </span>
      <p className="max-w-prose text-[15px] leading-relaxed text-muted-foreground">
        {t('connectExplain')}
      </p>
      <a
        href={gmailConsentUrl(clientId, redirect)}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-md shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/90"
      >
        {t('connect')}
      </a>
    </section>
  )
}
```

- [ ] **Step 6: Build the application card**

Create `web/src/components/applications/ApplicationCard.tsx`:

```tsx
'use client'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import type { ApplicationEventRow, ApplicationRow } from '@/types/db'
import { StageBadge } from './StageBadge'

export function ApplicationCard({ row, loadEvents }: {
  row: ApplicationRow
  loadEvents: (id: string) => Promise<ApplicationEventRow[]>
}) {
  const t = useTranslations('applications')
  const [events, setEvents] = useState<ApplicationEventRow[] | null>(null)
  const [open, setOpen] = useState(false)

  async function toggle() {
    setOpen((was) => !was)
    if (events === null) setEvents(await loadEvents(row.id))
  }

  return (
    <li className="flex flex-col gap-3 rounded-xl px-4 py-3.5 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {row.company ?? t('unknownCompany')}
          </p>
          {row.title && (
            <p className="truncate text-xs text-muted-foreground">{row.title}</p>
          )}
        </div>
        <StageBadge stage={row.stage} />
      </div>

      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="self-start text-xs font-medium text-primary hover:underline"
      >
        {t('why')}
      </button>

      {open && (
        <div className="flex flex-col gap-2 rounded-lg bg-muted/50 px-3 py-2.5 text-xs">
          {events === null ? (
            <span className="text-muted-foreground">…</span>
          ) : events.length === 0 ? (
            <span className="text-muted-foreground">{t('noEvents')}</span>
          ) : (
            events.map((e) => (
              <div key={e.id} className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">{e.subject}</span>
                <span className="text-muted-foreground">
                  {t('eventFrom')}: {e.from_address}
                  {e.received_at && ` · ${new Date(e.received_at).toLocaleDateString()}`}
                </span>
                {e.evidence && (
                  <span className="italic text-muted-foreground">“{e.evidence}”</span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </li>
  )
}
```

- [ ] **Step 7: Build the page**

Create `web/src/app/(app)/applications/page.tsx`:

```tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { RefreshCw } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { listApplicationEvents, listApplications } from '@/lib/db'
import { inboxConnect, inboxStatus, inboxSync, type InboxStatus } from '@/lib/api'
import { GMAIL_REDIRECT_PATH } from '@/lib/gmailOAuth'
import type { ApplicationRow } from '@/types/db'
import { ApplicationCard } from '@/components/applications/ApplicationCard'
import { ConnectGmailCard } from '@/components/applications/ConnectGmailCard'

const STALE_MS = 15 * 60 * 1000

export default function ApplicationsPage() {
  const t = useTranslations('applications')
  const router = useRouter()
  const params = useSearchParams()
  const [supabase] = useState(createClient)
  const [rows, setRows] = useState<ApplicationRow[] | null>(null)
  const [status, setStatus] = useState<InboxStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const loadRows = useCallback(async () => {
    setRows(await listApplications(supabase))
  }, [supabase])

  const runSync = useCallback(async () => {
    setBusy(true)
    setNotice(null)
    try {
      const report = await inboxSync()
      if (report.partial) setNotice(t('partial'))
      setStatus(await inboxStatus())
      await loadRows()
    } catch {
      setNotice(t('revoked'))
    } finally {
      setBusy(false)
    }
  }, [loadRows, t])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      const code = params.get('gmail_code')
      if (params.get('gmail') === 'denied') setNotice(t('denied'))
      if (code) {
        // Strip the code from the URL before anything else can re-trigger it.
        router.replace('/applications')
        try {
          await inboxConnect(code, window.location.origin + GMAIL_REDIRECT_PATH)
        } catch {
          setNotice(t('denied'))
        }
      }
      const current = await inboxStatus()
      if (cancelled) return
      setStatus(current)
      await loadRows()
      const last = current.last_synced_at ? Date.parse(current.last_synced_at) : 0
      if (current.connected && current.status === 'active' && Date.now() - last > STALE_MS) {
        await runSync()
      }
    }
    boot()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadEvents = useCallback(
    (id: string) => listApplicationEvents(supabase, id), [supabase]
  )

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-5 py-12 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            {t('title')}
          </h1>
          {status?.connected && (
            <p className="mt-1 font-mono text-xs tracking-wide text-muted-foreground">
              {t('connected')} · {status.email} ·{' '}
              {status.last_synced_at
                ? t('syncedAt', { time: new Date(status.last_synced_at).toLocaleTimeString() })
                : t('neverSynced')}
            </p>
          )}
        </div>

        {status?.connected && (
          <button
            type="button"
            onClick={runSync}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-foreground ring-1 ring-border transition-colors hover:bg-accent disabled:opacity-60"
          >
            <RefreshCw aria-hidden className={`size-4 ${busy ? 'animate-spin' : ''}`} />
            {busy ? t('refreshing') : t('refresh')}
          </button>
        )}
      </div>

      {status?.status === 'revoked' && (
        <p className="rounded-lg bg-destructive/8 px-4 py-3 text-sm text-destructive">
          {t('revoked')}
        </p>
      )}
      {notice && (
        <p className="rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">{notice}</p>
      )}

      {status && !status.connected && <ConnectGmailCard />}

      {rows === null ? (
        <div className="flex flex-col gap-3" aria-hidden>
          {[0, 1, 2].map((i) => <div key={i} className="h-[76px] animate-pulse rounded-xl bg-muted/70" />)}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('empty')}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((row) => (
            <ApplicationCard key={row.id} row={row} loadEvents={loadEvents} />
          ))}
        </ul>
      )}
    </main>
  )
}
```

- [ ] **Step 8: Add the nav entry and protect the route**

In `web/src/components/AppSidebar.tsx`, import `Inbox` from `lucide-react` and add to `ITEMS` after the `optimize` entry:

```tsx
  { href: '/applications', key: 'applications', icon: Inbox, also: [] },
```

In `web/src/lib/protected.ts`, extend the prefix list:

```ts
const PROTECTED_PREFIXES = ['/dashboard', '/cv', '/score', '/ats', '/applications']
```

- [ ] **Step 9: Run the page tests**

Run: `npm test -- src/app/\(app\)/applications`
Expected: PASS (8 tests).

- [ ] **Step 10: Run everything**

Run: `npm test && npx tsc --noEmit && npm run lint`
Expected: PASS across the board, including the pre-existing sidebar and dashboard tests.

- [ ] **Step 11: Add the web env var**

In `web/.env.local` and `web/README.md`, add:

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID=...   # same OAuth client as the API's GOOGLE_CLIENT_ID
```

- [ ] **Step 12: Commit**

```bash
git add web/src/app/\(app\)/applications web/src/components/applications web/src/components/AppSidebar.tsx web/src/lib/protected.ts web/src/messages web/README.md
git commit -m "feat(web): applications page with stages and the email behind each one"
```

---

## Manual verification (after Task 13)

The test suite proves the logic; only a real mailbox proves the Google plumbing.

1. In the Google Cloud console: create an OAuth client (Web application), add `http://localhost:3000/auth/gmail/callback` as a redirect URI, enable the Gmail API, add the `gmail.readonly` scope, and add your own address as a **test user**. Copy the client id and secret into `api/.env` and `web/.env.local`.
2. Generate `EMAIL_TOKEN_KEY`, and copy `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` from the Supabase dashboard into `api/.env`.
3. Start both servers, open `/applications`, click **Gmail'i bağla**, complete consent.
4. Confirm: the header shows your address; the list fills with applications the classifier found; each row's **Neden?** shows a real email you recognise.
5. Check `api.log` for `[inbox]` warnings — a quota hit or an expired cursor should appear there and nowhere in the UI except as the partial-update notice.
6. Click **Bağlantıyı kes**, then check <https://myaccount.google.com/permissions> to confirm the grant is actually gone at Google, not just in our table.

If the classifier mislabels a real email, add it to `api/tests/fixtures/mail/corpus.json` with the stage it should have produced, watch the test fail, then fix the pattern. The corpus is where real-world wording accumulates.
