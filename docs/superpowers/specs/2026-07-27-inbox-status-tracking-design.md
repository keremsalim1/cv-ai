# Inbox Status Tracking — Design Spec (Faz 4)

**Date:** 2026-07-27
**Status:** Approved (design), pending written-spec review
**Depends on:** Faz 2B applications table (`supabase/migrations/0002_applications.sql`),
Faz 3 role-based form engine (merged on `feat/role-based-form-engine`)

## Problem

We know whether we *submitted* an application. We do not know what happened to it.

`applications.status` is `submitted | delivered | failed` — three values that all
describe our own delivery attempt. The column answers "did our robot manage to press
the button", which stops being interesting about ten seconds after the user presses it.
The question the user actually lives with for the next six weeks is a different one:
*is anyone reading this, and did they say no yet?*

That answer already exists, in the user's inbox, in a mail from
`no-reply@greenhouse.io`. The user reads it manually, across dozens of threads, and
holds the resulting picture in their head. This spec moves that picture into the
product.

A second gap falls out of the same work. Users apply to jobs outside KRESUME — LinkedIn
Easy Apply, a form on the company's own site, a referral. Those applications are
invisible to us today, which makes any "your applications" view a partial and therefore
untrustworthy one. Reading the inbox gives us those for free: an ATS rejection mail
proves an application existed whether or not we sent it.

## Goal

After connecting Gmail, the user opens Başvurularım and sees, per application, one of
five states — **Alındı, Değerlendirmede, Mülakat, Teklif, Ret** — each traceable to the
specific email that produced it.

Non-goals for this phase: replying to recruiters, calendar integration, interview
reminders, background scanning while the app is closed, providers other than Gmail.

## Key constraints

Two constraints shaped the design more than anything else, and both were found before
any code was written.

**1. `gmail.readonly` is a Google restricted scope.** In testing mode it works for up
to 100 explicitly-added test users with no review. Publishing the app to general users
requires OAuth verification *plus* an annual CASA (Cloud Application Security
Assessment) by a Google-designated third party — paid, and measured in weeks. This
blocks public launch, not development. The feature is buildable and demoable today; the
assessment is a product decision to schedule separately.

**2. Supabase's `provider_token` cannot carry us.** `signInWithOAuth` returns a Google
access token that lives one hour and is absent from every subsequently refreshed
session. A sync triggered on page open would find no token most of the time. We
therefore run our own Google OAuth client with `access_type=offline`, and store the
refresh token ourselves.

The second constraint has a side benefit worth stating: because Gmail connection is
decoupled from login, a user who registered with email and password can still connect
their inbox.

## Architecture

One unit manages the Gmail connection. Four more form the sync pipeline:
**fetch → classify → match → advance**, with every processed message recorded on the
way out. Each has one job and a narrow interface.

```
GmailSource ──MailMessage──> classify ──Signal──> match ──application_id──> advance
  (mailbox.py)              (inbox_classify.py)  (inbox_match.py)        (inbox_sync.py)
                                                                              │
                                                                    application_events
```

`sync_user_inbox(user_id)` in `services/inbox_sync.py` is the only orchestrator, and
the only thing the HTTP layer calls. When background scanning is added later, cron
calls the same function; nothing else moves.

### 1. Connection — `services/inbox_connect.py`

The user starts OAuth from Başvurularım. Our callback route hands the authorization
code to `POST /inbox/connect`, which exchanges it for a refresh token and stores it
encrypted (Fernet, key from `email_token_key` in settings).

```sql
create table public.email_connections (
  user_id         uuid primary key references public.profiles (id) on delete cascade,
  provider        text not null default 'gmail' check (provider in ('gmail')),
  email_address   text not null,
  refresh_token_enc text not null,
  last_history_id text,
  last_synced_at  timestamptz,
  status          text not null default 'active'
                    check (status in ('active', 'revoked', 'error')),
  created_at      timestamptz not null default now()
);
```

`refresh_token_enc` is never exposed to a browser. RLS grants the user no `select` on
this table at all; the client reads `email_connection_status`, a view over
`(user_id, email_address, last_synced_at, status)`.

Disconnecting (`DELETE /inbox/connect`) revokes the token at Google *and* deletes the
row. A local delete alone would leave a live grant the user believes they revoked.

### 2. Fetch — `services/mailbox.py`

```python
class MailSource(Protocol):
    def fetch_new(self, cursor: str | None) -> FetchResult: ...

@dataclass
class FetchResult:
    messages: list[MailMessage]
    cursor: str | None      # Gmail historyId; opaque to every caller
    partial: bool           # True when a quota limit cut the batch short
```

`GmailSource` implements it. IMAP, if it is ever wanted, is one new class behind the
same Protocol — no other module learns about it.

**First sync** uses `users.messages.list` with a Gmail-side query, so the narrowing
happens on Google's servers and non-matching mail never reaches us:

```
newer_than:90d AND (
  from:(greenhouse.io OR lever.co OR myworkday.com OR ashbyhq.com OR
        successfactors.com OR icims.com OR smartrecruiters.com OR
        workable.com OR recruitee.com OR teamtailor.com)
  OR subject:(application OR başvuru OR interview OR mülakat OR pozisyon OR position)
)
```

**Subsequent syncs** use `users.history.list` with the stored `last_history_id` and
apply the same predicate locally to the returned ids. A `404` from the history endpoint
means the cursor aged out (Gmail keeps roughly a week); we fall back to the dated query
scan.

**Bodies are fetched lazily.** Messages arrive as `format=metadata` — headers and
snippet only. We request `format=full` solely for messages that pass the sender/subject
prefilter. The user's unrelated mail is never downloaded, let alone classified.

### 3. Classify — `services/inbox_classify.py`

```python
@dataclass
class Signal:
    stage: Stage | None      # None = could not tell; never a guess
    company: str | None
    title: str | None
    confidence: float
    evidence: str            # the sentence that decided it, shown to the user
    job_related: bool
```

**Rules first.** ATS templates are near-identical across employers, so most mail is
classifiable for free. Patterns are ordered by reliability and matched against subject
plus the first ~2000 characters of the body, in Turkish and English:

| Stage | Signals |
|---|---|
| `rejected` | "move forward with other candidates", "not to proceed", "olumsuz sonuçlan", "başka adaylarla devam" |
| `offer` | "pleased to offer", "iş teklifi", "teklifimizi" |
| `interview` | "schedule a call", "book a time", "mülakat daveti", `text/calendar` attachment |
| `received` | "we have received your application", "başvurunuz alınmıştır", auto-reply headers |
| `in_review` | "shortlisted", "next stage", "değerlendirmeye alındı", "bir sonraki aşama" |

**LLM second, and only when needed.** If no rule fires, or two rules of different
stages fire, the message goes to Gemini (`MODEL_FAST`) with a strict JSON schema via
the existing `LLMClient.chat_json`. This keeps quota consumption proportional to
genuine ambiguity rather than to inbox size.

**Silence is a valid output.** If neither layer is confident, `stage` is `None`, the
event is still recorded, and the application's stage does not move. A wrong "Ret" badge
costs the user more than a missing one.

`job_related=False` discards job-board newsletters and marketing mail that survived the
query.

### 4. Match — `services/inbox_match.py`

Four steps, first hit wins:

1. **Thread.** The `thread_id` already appears in `application_events` → same application.
2. **Domain.** The sender's registrable domain equals the registrable domain of
   `applications.url`.
3. **Company name.** `Signal.company`, normalized, equals a stored company. Normalize =
   casefold, strip diacritics, drop legal suffixes (`A.Ş.`, `Ltd. Şti.`, `Inc.`,
   `GmbH`, `B.V.`, `LLC`).
4. **Nothing matched** → insert a new `applications` row with `source='email'`,
   `status='external'`, company and title from the signal.

Step 4 is what makes the list complete rather than merely accurate: applications the
user made outside KRESUME appear the moment a company replies to them.

### 5. Advance — the stage machine

```
received (1) → in_review (2) → interview (3) → offer (4)
                    rejected — reachable from any stage, terminal
```

**Stages only move forward.** A delayed "we received your application" auto-reply
arriving after an interview invitation must not rewind the badge; mail order is not
event order.

**Rejection is terminal.** Nothing after it changes the stage. If a later mail
disagrees, the event is still recorded and visible under "Neden?", so a genuine
reversal is legible to the user even though the badge does not flip on its own.

Every processed message writes a row, whether or not the stage moved:

```sql
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
  detected_stage text,               -- null when the classifier was unsure
  confidence     real,
  evidence       text,
  created_at     timestamptz not null default now(),
  unique (user_id, message_id)
);
```

The unique constraint makes reprocessing idempotent — the same message seen twice
cannot advance a stage twice.

This table is the feature's trust mechanism. A status the user cannot interrogate is a
status they will not believe the first time it is wrong, and it will sometimes be
wrong.

### 6. Schema changes — `supabase/migrations/0003_inbox.sql`

Beyond the two new tables:

```sql
alter table public.applications
  add column company text,
  add column title text,
  add column stage text not null default 'received'
    check (stage in ('received','in_review','interview','offer','rejected')),
  add column stage_updated_at timestamptz,
  add column source text not null default 'assisted'
    check (source in ('assisted','email'));

alter table public.applications drop constraint applications_status_check;
alter table public.applications add constraint applications_status_check
  check (status in ('submitted','delivered','failed','external'));
```

`status` and `stage` stay separate on purpose. `status` answers "could we deliver it",
`stage` answers "what did the company say". Collapsing them would make an email-sourced
application need a delivery status it never had, and a failed submission need a company
response that will never come.

Both new tables carry the codebase's existing RLS pattern: `auth.uid() = user_id` for
`application_events`, and no direct client access at all for `email_connections`.

### 7. HTTP surface — `routers/inbox.py`

| Endpoint | Purpose |
|---|---|
| `POST /inbox/connect` | Exchange OAuth code, store connection |
| `DELETE /inbox/connect` | Revoke at Google, delete row |
| `GET /inbox/status` | `{connected, email, last_synced_at, status}` |
| `POST /inbox/sync` | Run `sync_user_inbox`, return what changed |

`POST /inbox/sync` returns `{scanned, classified, created, updated: [{application_id, company, from_stage, to_stage}], partial}` — enough for the UI to say what happened rather than just re-rendering.

### 8. Interface — `/applications`

A new page, Başvurularım. Rows carry company, title, stage badge, and last update.
Expanding a row shows the deciding email: sender, subject, date, and the evidence
sentence, under **"Neden?"**.

The header shows connection state — *"Gmail'e bağlı · 3 dk önce güncellendi"* — with a
**Yenile** button. Opening the page triggers a sync when `last_synced_at` is older than
15 minutes; otherwise it renders what is stored. When no inbox is connected, the page
still lists KRESUME applications and offers the connect card above them, describing
exactly what we read and what we never touch.

Strings go in `messages/tr.json` and `messages/en.json`, following the existing
`next-intl` layout.

### 9. Failure modes

Each of these is surfaced, not swallowed. The existing assisted-apply work established
that telling the user what actually happened beats a generic failure, and the same
applies here.

| Failure | Behavior |
|---|---|
| Refresh token revoked by user at Google | `status='revoked'`; UI: "Gmail bağlantın sona ermiş, yeniden bağla" |
| Gmail quota / 429 | Keep `last_history_id`, return `partial=true`; UI: "kısmen güncellendi" |
| `historyId` expired (404) | Fall back to the dated query scan; user sees nothing unusual |
| Gemini unavailable or `daily_ai_limit` reached | Rules still run; ambiguous mail is left unclassified and retried next sync |
| Classifier unsure | Event recorded, stage unchanged |

No path invents a stage.

## Testing

The rule layer is pure and therefore fully testable offline, which is most of the risk
surface.

- **Fixture corpus** — realistic ATS mails across `{TR, EN} × {greenhouse, lever,
  workday, ashby} × 5 stages`, plus negatives that must be ignored: a job-board
  newsletter, a recruiter cold-outreach mail (not an application response), and a
  personal email.
- **Rules** — unit tests over the corpus, no network, asserting both correct stages and
  correct abstention.
- **`GmailSource`** — fake transport; covers first sync, incremental sync, expired
  cursor fallback, and quota truncation.
- **Match** — each of the four steps, including the normalization cases (`Acme A.Ş.` vs
  `ACME Inc.`).
- **Stage machine** — forward-only, rejection-terminal, idempotent reprocessing.
- **Web** — page tests with a mocked Supabase client, matching the existing
  `__tests__` convention.

## Risks

**Classification is a judgment call and will sometimes be wrong.** The mitigation is
not better patterns; it is the visible evidence trail plus abstention when unsure.
Users forgive a missing status faster than a fabricated one.

**The rules are a maintenance surface.** Every ATS rewrites its templates eventually,
and Turkish HR prose varies more than English boilerplate. The LLM fallback absorbs
drift, but a rule that silently stops matching degrades into "the LLM does everything",
which the quota cannot fund. Rule-hit rate is worth measuring once real mail flows.

**CASA is a real cost.** Building this does not unblock shipping it publicly. Worth
knowing before, not after.

## Decisions

1. **Gmail API over IMAP or a forwarding address.** One-click connection, revocable,
   no password handling. `MailSource` keeps IMAP available later without a rewrite.
2. **Query-narrowed scanning over full-inbox scanning.** Personal mail is never
   fetched; the query still catches applications made outside KRESUME.
3. **Rules first, LLM on ambiguity.** Full-LLM classification cannot fit the 20/day
   quota; rules-only cannot read Turkish HR prose. The hybrid is also the only option
   that degrades gracefully when Gemini is down.
4. **Five stages.** Separating "Alındı" from "Değerlendirmede" distinguishes an
   automated acknowledgment from human contact — the difference the user cares about
   while waiting. "Mülakat" is separate because it is the one stage demanding action.
5. **Email-discovered applications create rows.** A list missing the user's LinkedIn
   applications is one they cannot trust as a complete picture.
6. **Stages move forward only; rejection is terminal.** Mail arrival order is not event
   order.
7. **On-demand sync, cron-shaped.** No scheduler infrastructure now, no rewrite later.
