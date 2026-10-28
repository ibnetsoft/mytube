-- Service-only atomic submission. No user-controlled JWT metadata is trusted.
create table if not exists public.std_pipeline_runs (
 id uuid primary key, project_id uuid not null references public.std_projects(id),
 submission_id uuid, job_id uuid not null, manifest_hash text not null,
 manifest jsonb not null, status text not null default 'queued',
 render_queue_id uuid, warnings jsonb not null default '[]',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.std_pipeline_runs enable row level security;
revoke all on public.std_pipeline_runs from anon, authenticated;
grant all on public.std_pipeline_runs to service_role;
create index if not exists std_pipeline_runs_project on public.std_pipeline_runs(project_id, created_at desc);
create table if not exists public.std_pipeline_stages (
 run_id uuid not null references public.std_pipeline_runs(id), stage text not null,
 scene_number integer not null default 0, state text not null, attempts integer not null default 0,
 artifact jsonb, error text, updated_at timestamptz not null default now(),
 primary key(run_id,stage,scene_number)
);
alter table public.std_pipeline_stages enable row level security;
revoke all on public.std_pipeline_stages from anon, authenticated;
grant all on public.std_pipeline_stages to service_role;

create or replace function public.register_std_pipeline(p_project_id uuid, p_user_id uuid,
 p_updated_at timestamptz, p_run_id uuid, p_job_id uuid, p_manifest jsonb, p_hash text)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare p std_projects; existing std_pipeline_runs; sid uuid; stamp timestamptz := now();
begin
 select * into p from std_projects where id=p_project_id for update;
 if p.id is null or p.user_id is distinct from p_user_id then raise exception 'Project ownership mismatch'; end if;
 if p.status in ('approved','canceled') then raise exception 'Project is closed'; end if;
 if p.submitted_at is not null then
   select * into existing from std_pipeline_runs where project_id=p_project_id order by created_at desc limit 1;
   return jsonb_build_object('already_submitted',true,'run_id',existing.id,'job_id',existing.job_id);
 end if;
 if p.updated_at is distinct from p_updated_at then raise exception 'Project changed; save and submit again'; end if;
 if p_manifest->'project'->>'id' <> p_project_id::text or p_manifest->>'version' <> '2' then raise exception 'Invalid manifest'; end if;
 insert into std_project_submissions(project_id,submitted_by,status,metadata)
 values(p_project_id,p_user_id,'review_requested',jsonb_build_object('pipeline_version',2,'pipeline_run_id',p_run_id,'manifest_hash',p_hash,'postprocess_status','pending')) returning id into sid;
 insert into std_pipeline_runs(id,project_id,submission_id,job_id,manifest_hash,manifest)
 values(p_run_id,p_project_id,sid,p_job_id,p_hash,p_manifest);
 insert into std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
 values(p_job_id,p_project_id,'other','uploaded','pipeline_'||p_run_id||'.json','application/json',
 jsonb_build_object('kind','ae_mouth_job','pipeline_version',2,'pipeline_run_id',p_run_id,
 'automatic',true,'auto_pending',true,'auto_video_coordinates',false,'state','queued','phase','render',
 'fingerprint',p_manifest->'mouth'->>'fingerprint','input',p_manifest->'mouth'->'input','results',coalesce(p_manifest->'reusable_results','[]'::jsonb),
 'failure_policy',p_manifest->'failure_policy'));
 update std_projects set status='review_requested',submitted_at=stamp,updated_at=stamp,
 progress_payload=coalesce(progress_payload,'{}')||jsonb_build_object('pipeline_run_id',p_run_id,'postprocess_status','pending','ae_mouth_job_id',p_job_id)
 where id=p_project_id;
 return jsonb_build_object('run_id',p_run_id,'job_id',p_job_id,'submission_id',sid,'submitted_at',stamp);
end $$;
revoke all on function public.register_std_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.register_std_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) to service_role;

create or replace function public.record_std_pipeline_stage(p_run_id uuid,p_token text,p_number integer,
 p_state text,p_artifact jsonb,p_error text) returns boolean
language plpgsql security invoker set search_path=public as $$
declare jid uuid; current_token text;
begin
 select job_id into jid from std_pipeline_runs where id=p_run_id;
 select metadata->>'worker_token' into current_token from std_project_assets
 where id=jid and metadata->>'state'='processing' for update;
 if current_token is distinct from p_token or current_token is null then return false; end if;
 insert into std_pipeline_stages(run_id,stage,scene_number,state,attempts,artifact,error,updated_at)
 values(p_run_id,'scene_composition',p_number,p_state,case when p_state='composing' then 1 else 0 end,p_artifact,p_error,now())
 on conflict(run_id,stage,scene_number) do update set state=excluded.state,artifact=excluded.artifact,
 error=excluded.error,updated_at=excluded.updated_at,
 attempts=std_pipeline_stages.attempts+case when p_state='composing' then 1 else 0 end;
 return true;
end $$;
revoke all on function public.record_std_pipeline_stage(uuid,text,integer,text,jsonb,text) from public,anon,authenticated;
grant execute on function public.record_std_pipeline_stage(uuid,text,integer,text,jsonb,text) to service_role;
