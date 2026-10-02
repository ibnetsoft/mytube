-- Local script worker only. Supabase is the authoritative improvement history.
create table public.script_guideline_versions (
  id uuid primary key default gen_random_uuid(),
  version bigint generated always as identity unique,
  title text not null check (length(title) between 1 and 200),
  issue text not null check (length(issue) between 1 and 4000),
  instruction text not null check (length(instruction) between 1 and 4000),
  category text not null default '',
  language text not null default '' check (language in ('','ko','ja','en','es','vi','th')),
  source_job_id text references public.script_worker_jobs(id),
  status text not null default 'pending' check (status in ('pending','approved','rejected','retired')),
  review_note text not null default '',
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  notion_page_id text,
  notion_synced_at timestamptz
);
create index script_guideline_scope on public.script_guideline_versions(status,category,language);
create table public.script_guideline_outcomes (
  job_id text primary key references public.script_worker_jobs(id),
  title text not null,
  category text not null default '',
  language text not null default '',
  status text not null,
  applied_versions jsonb not null default '[]',
  evaluation jsonb not null default '{}',
  updated_at timestamptz not null default now()
);
alter table public.script_guideline_versions enable row level security;
alter table public.script_guideline_outcomes enable row level security;
revoke all on public.script_guideline_versions, public.script_guideline_outcomes from public,anon,authenticated;
grant select,insert,update on public.script_guideline_versions, public.script_guideline_outcomes to service_role;
grant usage,select on sequence public.script_guideline_versions_version_seq to service_role;
create function public.guard_script_guideline_version() returns trigger language plpgsql set search_path = '' as $$
begin
  if (new.title,new.issue,new.instruction,new.category,new.language,new.source_job_id,new.version,new.created_at)
     is distinct from (old.title,old.issue,old.instruction,old.category,old.language,old.source_job_id,old.version,old.created_at) then
    raise exception 'Create a new guideline version instead of editing history';
  end if;
  if new.status is distinct from old.status and not
    ((old.status='pending' and new.status in ('approved','rejected')) or
     (old.status='approved' and new.status='retired')) then
    raise exception 'Invalid guideline review transition';
  end if;
  return new;
end $$;
create trigger guard_script_guideline_version before update on public.script_guideline_versions
for each row execute function public.guard_script_guideline_version();
