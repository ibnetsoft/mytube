-- Re-render submissions must use the selected renderer and freeze a fresh snapshot.
create or replace function public.register_std_motion_resubmission(
 p_project_id uuid,p_user_id uuid,p_updated_at timestamptz,p_run_id uuid,p_job_id uuid,
 p_manifest jsonb,p_hash text,p_engine text
) returns jsonb language plpgsql set search_path=public as $$
declare p std_projects; existing std_project_assets;
begin
 select * into p from std_projects where id=p_project_id for update;
 if p.id is null or p.user_id is distinct from p_user_id then raise exception 'Project ownership mismatch'; end if;
 if p.status in ('approved','canceled') then raise exception 'Project is closed'; end if;
 if p_engine not in ('effectcraft','ae') or p_engine is null then raise exception 'Invalid renderer'; end if;
 select * into existing from std_project_assets where project_id=p_project_id
  and metadata->>'kind' in ('effectcraft_automation','motion_automation','filmcraft_automation')
  and metadata->>'state' in ('queued','processing') order by created_at desc limit 1;
 if existing.id is not null then
  if existing.metadata->>'fingerprint'=p_hash and existing.metadata->>'kind'=
   (case when p_engine='effectcraft' then 'effectcraft_automation' else 'motion_automation' end) then
   return jsonb_build_object('already_submitted',true,'job_id',existing.id,
    'run_id',existing.metadata->>'pipeline_run_id','submitted_at',p.submitted_at);
  end if;
  raise exception 'An automation job is already active';
 end if;
 if exists(select 1 from remote_render_queue where metadata->>'std_web_project_id'=p_project_id::text
  and status in ('pending','rendering')) then raise exception 'A render is already active'; end if;
 if p.updated_at is distinct from p_updated_at then raise exception 'Project changed; save and submit again'; end if;
 -- The lock and transaction prevent a partially reopened project or duplicate jobs.
 update std_projects set submitted_at=null where id=p_project_id;
 if p_engine='effectcraft' then
  return register_std_effectcraft_pipeline(p_project_id,p_user_id,p_updated_at,p_run_id,p_job_id,p_manifest,p_hash);
 end if;
 return register_std_motion_pipeline(p_project_id,p_user_id,p_updated_at,p_run_id,p_job_id,p_manifest,p_hash);
end $$;
revoke all on function public.register_std_motion_resubmission(uuid,uuid,timestamptz,uuid,uuid,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.register_std_motion_resubmission(uuid,uuid,timestamptz,uuid,uuid,jsonb,text,text) to service_role;
