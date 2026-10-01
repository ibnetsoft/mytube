create table public.std_subtitle_translation_jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.std_projects(id) on delete cascade,
  target_language text not null check (target_language in ('ko','en','vi','th')),
  request_hash text not null,
  source_blocks jsonb not null,
  status text not null default 'queued' check (status in ('queued','running','completed','failed')),
  result_blocks jsonb,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique(project_id,target_language,request_hash)
);
alter table public.std_subtitle_translation_jobs enable row level security;
revoke all on public.std_subtitle_translation_jobs from anon, authenticated;
grant all on public.std_subtitle_translation_jobs to service_role;
create index std_subtitle_translation_pending on public.std_subtitle_translation_jobs(created_at) where status = 'queued';

create function public.claim_std_subtitle_translation()
returns setof public.std_subtitle_translation_jobs language plpgsql security invoker set search_path = public as $$
begin
  -- A crashed CLI call is reported as failed rather than silently replayed.
  update std_subtitle_translation_jobs set status='failed', error='로컬 번역 실행 시간이 초과되었습니다. 다시 시도해 주세요.'
  where status='running' and started_at < now() - interval '30 minutes';
  return query update std_subtitle_translation_jobs set status='running', started_at=now(), error=null
  where id = (select id from std_subtitle_translation_jobs where status='queued'
              order by created_at for update skip locked limit 1)
  returning *;
end $$;

create function public.complete_std_subtitle_translation(job_id uuid, translated_blocks jsonb)
returns void language plpgsql security invoker set search_path = public as $$
declare j std_subtitle_translation_jobs; payload jsonb; saved jsonb; merged jsonb;
begin
  select * into j from std_subtitle_translation_jobs where id=job_id and status='running' for update;
  if not found then raise exception 'Translation job is not running'; end if;
  if jsonb_array_length(translated_blocks) <> jsonb_array_length(j.source_blocks)
     or exists(select 1 from jsonb_array_elements(j.source_blocks) s where not exists(
         select 1 from jsonb_array_elements(translated_blocks) t where t->'index'=s->'index'
         and t->>'source_text'=s->>'source_text' and length(trim(t->>'translated_text')) > 0))
  then raise exception 'Translation result does not match source'; end if;
  select coalesce(project_payload,'{}') into payload from std_projects where id=j.project_id for update;
  saved := coalesce(payload->'subtitle_translations'->j.target_language->'blocks','[]');
  select coalesce(jsonb_agg(b),'[]') into merged from (
    select b from jsonb_array_elements(saved) b where not exists(
      select 1 from jsonb_array_elements(translated_blocks) t where t->'index'=b->'index')
    union all select b from jsonb_array_elements(translated_blocks) b
  ) rows;
  payload := jsonb_set(payload,'{subtitle_translations}',
    coalesce(payload->'subtitle_translations','{}') || jsonb_build_object(j.target_language,
      jsonb_build_object('version',1,'updated_at',now(),'blocks',merged,'provider','local-codex')));
  update std_projects set project_payload=payload where id=j.project_id;
  update std_subtitle_translation_jobs set status='completed', result_blocks=translated_blocks, completed_at=now() where id=j.id;
end $$;
revoke all on function public.claim_std_subtitle_translation() from public, anon, authenticated;
revoke all on function public.complete_std_subtitle_translation(uuid,jsonb) from public, anon, authenticated;
grant execute on function public.claim_std_subtitle_translation() to service_role;
grant execute on function public.complete_std_subtitle_translation(uuid,jsonb) to service_role;
