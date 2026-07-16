-- KRESUME.ai initial schema (MVP Phase 1)

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  language text not null default 'tr' check (language in ('tr', 'en'))
);

create table public.cvs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  file_path text not null,
  parsed_data jsonb not null,
  is_ats boolean not null default false,
  source_cv_id uuid references public.cvs (id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.job_postings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  url text,
  title text not null,
  company text,
  description text not null,
  fetch_method text not null check (fetch_method in ('url', 'manual')),
  created_at timestamptz not null default now()
);

create table public.evaluations (
  id uuid primary key default gen_random_uuid(),
  cv_id uuid not null references public.cvs (id) on delete cascade,
  job_id uuid not null references public.job_postings (id) on delete cascade,
  percent int not null check (percent between 0 and 100),
  stars int not null check (stars between 1 and 5),
  strengths jsonb not null default '[]',
  gaps jsonb not null default '[]',
  suggestions jsonb not null default '[]',
  created_at timestamptz not null default now(),
  unique (cv_id, job_id)
);

-- Row Level Security: every user sees only their own data (KVKK/GDPR baseline)
alter table public.profiles enable row level security;
alter table public.cvs enable row level security;
alter table public.job_postings enable row level security;
alter table public.evaluations enable row level security;

create policy "own profile" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

create policy "own cvs" on public.cvs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own job postings" on public.job_postings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own evaluations" on public.evaluations
  for all
  using (exists (select 1 from public.cvs c where c.id = cv_id and c.user_id = auth.uid()))
  with check (exists (select 1 from public.cvs c where c.id = cv_id and c.user_id = auth.uid()));

-- Auto-create a profile row on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data ->> 'full_name');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Private storage bucket for CV PDFs; first path folder must equal the user id
insert into storage.buckets (id, name, public) values ('cvs', 'cvs', false);

create policy "own cv files" on storage.objects
  for all
  using (bucket_id = 'cvs' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'cvs' and (storage.foldername(name))[1] = auth.uid()::text);
