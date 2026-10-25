create table public.std_tts_jobs (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.std_projects(id) on delete cascade,
 owner_email text not null, user_id text not null,
 fingerprint text not null, source_hash text not null, request jsonb not null, script text not null,
 status text not null default 'queued' check(status in ('queued','processing','completed','failed')),
 ready integer not null default 0, total integer not null,
 reused integer not null default 0, generated integer not null default 0,
 attempts integer not null default 0, error text, result jsonb,
 lease_token uuid, lease_until timestamptz, next_run_at timestamptz not null default now(),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.std_tts_jobs enable row level security;
revoke all on public.std_tts_jobs from anon, authenticated;
grant all on public.std_tts_jobs to service_role;
create unique index std_tts_jobs_active_project on public.std_tts_jobs(project_id)
 where status in ('queued','processing');
create index std_tts_jobs_pending on public.std_tts_jobs(next_run_at) where status in ('queued','processing');
create function public.claim_std_tts_job() returns setof public.std_tts_jobs
language sql set search_path = public as $$
 update public.std_tts_jobs set status='processing', lease_token=gen_random_uuid(),
 lease_until=now()+interval '6 minutes', updated_at=now()
 where id=(select id from public.std_tts_jobs
   where status in ('queued','processing') and next_run_at<=now()
   and (lease_until is null or lease_until<now())
   order by next_run_at,created_at for update skip locked limit 1)
 returning *;
$$;
revoke all on function public.claim_std_tts_job() from public,anon,authenticated;
grant execute on function public.claim_std_tts_job() to service_role;
