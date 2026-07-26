-- KRESUME.ai Faz 2B: application history

create table public.applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  cv_id uuid references public.cvs (id) on delete set null,
  optimized_cv_id uuid references public.cvs (id) on delete set null,
  url text not null,
  job_text text,
  cover_letter text,
  qa jsonb not null default '{}',
  changes jsonb not null default '[]',
  status text not null check (status in ('submitted', 'delivered', 'failed')),
  created_at timestamptz not null default now()
);

alter table public.applications enable row level security;

create policy "own applications" on public.applications
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
