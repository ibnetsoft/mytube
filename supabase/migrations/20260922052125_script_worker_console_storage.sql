-- Independent script-worker persistence; service-role access only.
create table public.script_worker_jobs (
  id text primary key check (id ~ '^[a-f0-9]{32}$'),
  title text not null,
  mode text not null check (mode in ('new','repair','grounded','topics')),
  status text not null check (status in ('queued','running','failed','interrupted','completed','awaiting_approval','approved_pending_repair')),
  worker_id text not null,
  created_at double precision not null,
  updated_at double precision not null,
  job_record jsonb not null,
  request_data jsonb not null default '{}'::jsonb,
  source_snapshot jsonb not null default '{}'::jsonb,
  candidate jsonb not null default '{}'::jsonb,
  reference_sources jsonb not null default '[]'::jsonb
);
create index script_worker_jobs_created on public.script_worker_jobs (created_at desc);
-- A second console cannot execute the same pipeline concurrently.
create unique index script_worker_one_active on public.script_worker_jobs ((true)) where status in ('queued','running');
alter table public.script_worker_jobs enable row level security;
revoke all on public.script_worker_jobs from public, anon, authenticated;
grant select, insert, update on public.script_worker_jobs to service_role;

create view public.script_worker_history with (security_invoker = true) as
select 'dedicated'::text as origin, id, title, mode as job_type, status,
  job_record->>'stage' as stage, created_at, updated_at,
  job_record->>'source_id' as source_id, job_record->>'kind' as source_kind
from public.script_worker_jobs
union all
select 'legacy'::text, id::text,
  coalesce(nullif(payload->>'upload_title',''), nullif(payload->>'topic',''), nullif(payload->>'title',''), job_type),
  job_type, status, coalesce(message,worker_status,''),
  extract(epoch from created_at)::double precision, extract(epoch from updated_at)::double precision,
  coalesce(payload->>'topic_queue_id',payload->>'project_id'),
  case when payload->>'topic_queue_id' is not null then 'topic' else 'project' end
from public.remote_hermes_queue
where job_type in ('codex_content_generate','script_generate','script_plan_generate','publish_metadata_generate','sfx_plan_generate');
revoke all on public.script_worker_history from public, anon, authenticated;
grant select on public.script_worker_history to service_role;
