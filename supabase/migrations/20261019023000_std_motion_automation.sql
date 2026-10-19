-- Separate atomic submission keeps the existing reviewed-mouth pipeline unchanged.
create or replace function public.register_std_motion_pipeline(p_project_id uuid,p_user_id uuid,
 p_updated_at timestamptz,p_run_id uuid,p_job_id uuid,p_manifest jsonb,p_hash text)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare p std_projects; existing std_pipeline_runs; sid uuid; stamp timestamptz:=now();
begin
 select * into p from std_projects where id=p_project_id for update;
 if p.id is null or p.user_id is distinct from p_user_id then raise exception 'Project ownership mismatch'; end if;
 if p.status in ('approved','canceled') then raise exception 'Project is closed'; end if;
 if p.submitted_at is not null then
  select * into existing from std_pipeline_runs where project_id=p_project_id order by created_at desc limit 1;
  return jsonb_build_object('already_submitted',true,'run_id',existing.id,'job_id',existing.job_id);
 end if;
 if p.updated_at is distinct from p_updated_at then raise exception 'Project changed; save and submit again'; end if;
 if p_manifest->>'version' is distinct from '1' or p_manifest->'project'->>'id' is distinct from p_project_id::text
  or p_manifest->'automation'->>'fingerprint' is distinct from p_hash
  or p_hash is null or p_hash !~ '^[a-f0-9]{64}$' or jsonb_typeof(p_manifest->'automation'->'snapshot_json') is distinct from 'string' then raise exception 'Invalid frozen motion input'; end if;
 insert into std_project_submissions(project_id,submitted_by,status,metadata)
 values(p_project_id,p_user_id,'review_requested',jsonb_build_object('pipeline_version',2,'motion_automation',true,'pipeline_run_id',p_run_id,'postprocess_status','pending')) returning id into sid;
 insert into std_pipeline_runs(id,project_id,submission_id,job_id,manifest_hash,manifest)
 values(p_run_id,p_project_id,sid,p_job_id,p_hash,p_manifest);
 insert into std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
 values(p_job_id,p_project_id,'other','uploaded','motion-automation-'||p_run_id||'.json','application/json',
  jsonb_build_object('kind','motion_automation','version',1,'pipeline_run_id',p_run_id,'submission_id',sid,
  'enabled',true,'state','queued','phase','direction','input',p_manifest->'automation','fingerprint',p_hash));
 update std_projects set status='review_requested',submitted_at=stamp,updated_at=stamp,
  progress_payload=coalesce(progress_payload,'{}')||jsonb_build_object('motion_automation_job_id',p_job_id,'pipeline_run_id',p_run_id,'postprocess_status','pending') where id=p_project_id;
 return jsonb_build_object('run_id',p_run_id,'job_id',p_job_id,'submission_id',sid,'submitted_at',stamp);
end $$;
revoke all on function public.register_std_motion_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.register_std_motion_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) to service_role;

create or replace function public.patch_std_motion_job(p_job_id uuid,p_token text,p_patch jsonb)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare result jsonb;
begin
 if p_patch is null or jsonb_typeof(p_patch)<>'object' then raise exception 'Invalid motion patch'; end if;
 if p_patch ?| array['input','fingerprint','worker_token','kind','pipeline_run_id','submission_id','version'] then raise exception 'Frozen job fields cannot change'; end if;
 update std_project_assets set metadata=metadata||p_patch,updated_at=now()
 where id=p_job_id and metadata->>'kind'='motion_automation' and metadata->>'state'='processing'
 and metadata->>'worker_token'=p_token returning metadata into result;
 if result is null then raise exception 'Motion worker lease lost'; end if;
 return result;
end $$;
revoke all on function public.patch_std_motion_job(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.patch_std_motion_job(uuid,text,jsonb) to service_role;
