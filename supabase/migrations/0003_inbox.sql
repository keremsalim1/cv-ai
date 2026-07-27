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
