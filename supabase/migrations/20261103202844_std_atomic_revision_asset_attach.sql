-- Bind a previously registered upload and scene readiness in one transaction.
-- This privileged function is intentionally restricted to the server role.
create or replace function public.std_attach_revision_asset(
 p_project_id uuid, p_owner text, p_expected_updated_at timestamptz,
 p_expected_status text, p_asset_id uuid, p_scene_number integer, p_payload jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare p public.std_projects%rowtype; a public.std_project_assets%rowtype; s public.std_project_scenes%rowtype; job public.script_worker_jobs%rowtype;
 current_hash text; needs_video boolean; ready boolean; count_ready integer; result_payload jsonb; scene_array jsonb; i integer; key text;
begin
 select * into p from public.std_projects where id=p_project_id for update;
 if not found or lower(p.employee_email) is distinct from lower(p_owner) then raise exception 'Project ownership mismatch'; end if;
 if p.status in ('approved','canceled','cancelled','completed','paid')
 then raise exception 'Project status changed'; end if;
 if p.project_payload->'strict_content_identity' is distinct from 'true'::jsonb then raise exception 'Not a revisioned project'; end if;
 select * into job from public.script_worker_jobs where id=p.project_payload->>'source_script_job_id' for share;
 if not found or job.status in ('canceled','cancelled') or job.job_record->>'status' in ('canceled','cancelled')
    or job.job_record->>'topic_queue_id' is distinct from p.topic_queue_id::text
 then raise exception 'Source job canceled or invalid'; end if;
 current_hash:=p.project_payload#>>'{content_identity,script_sha256}';
 if current_hash is null or current_hash !~ '^[0-9a-f]{64}$' then raise exception 'Missing content identity'; end if;
 select * into a from public.std_project_assets where id=p_asset_id and project_id=p.id for update;
 if not found or a.scene_number is distinct from p_scene_number or a.asset_type not in ('image','video')
    or a.status not in ('uploaded','assigned') or a.metadata#>>'{content_identity,script_sha256}' is distinct from current_hash
    or a.metadata#>>'{content_identity,project_id}' is distinct from p.id::text
    or a.metadata#>>'{content_identity,topic_queue_id}' is distinct from p.topic_queue_id::text
 then raise exception 'Asset does not match revision'; end if;
 select * into s from public.std_project_scenes where project_id=p.id and scene_number=p_scene_number for update;
 if not found or (a.scene_id is not null and a.scene_id is distinct from s.id) then raise exception 'Scene does not match asset'; end if;
 if p.updated_at is distinct from p_expected_updated_at then
   if p.progress_payload->>'last_atomic_upload_asset_id'=p_asset_id::text
      and exists(select 1 from jsonb_array_elements(coalesce(p.project_payload#>'{structure,scenes}','[]'::jsonb)) e
        where (e->>'scene_number')::integer=p_scene_number
          and e#>>array['metadata',a.asset_type||'_asset_id']=p_asset_id::text) then
     return jsonb_build_object('success',true,'already_attached',true,'updated_at',p.updated_at);
   end if;
   raise exception 'Project changed';
 end if;
 if p.status is distinct from p_expected_status then raise exception 'Project status changed'; end if;
 if jsonb_typeof(p_payload) is distinct from 'object' or p_payload->>'script' is distinct from p.project_payload->>'script'
    or p_payload#>>'{content_identity,script_sha256}' is distinct from current_hash
    or p_payload->'strict_content_identity' is distinct from 'true'::jsonb
 then raise exception 'Invalid upload payload'; end if;
 needs_video:=p_scene_number <= coalesce((p.project_payload#>>'{structure,required_video_scene_count}')::int,18)
   or coalesce(p.project_payload#>'{structure,motion_graphic_video_scenes}','[]'::jsonb) @> jsonb_build_array(p_scene_number);
 if a.asset_type='video' and not needs_video then raise exception 'Video not selected'; end if;
 select exists(select 1 from public.std_project_assets x where x.project_id=p.id and x.scene_number=p_scene_number
   and x.status in ('uploaded','assigned') and x.metadata#>>'{content_identity,script_sha256}'=current_hash
   and x.asset_type=case when needs_video then 'video' else 'image' end) into ready;
 update public.std_project_scenes set asset_status=case when ready then 'ready' else 'missing' end,updated_at=clock_timestamp() where id=s.id;
 result_payload:=p_payload;
 foreach key in array array['scenes','structure'] loop
   scene_array:=case when key='scenes' then result_payload->'scenes' else result_payload#>'{structure,scenes}' end;
   if jsonb_typeof(scene_array)='array' then
     select (ord-1)::integer into i from jsonb_array_elements(scene_array) with ordinality e(v,ord)
       where (v->>'scene_number')::integer=p_scene_number limit 1;
     if i is not null then
       if key='scenes' then result_payload:=jsonb_set(result_payload,array['scenes',i::text,'asset_status'],to_jsonb(case when ready then 'ready'::text else 'missing'::text end),true);
       else result_payload:=jsonb_set(result_payload,array['structure','scenes',i::text,'asset_status'],to_jsonb(case when ready then 'ready'::text else 'missing'::text end),true); end if;
     end if;
   end if;
 end loop;
 select count(*) into count_ready from public.std_project_scenes where project_id=p.id and asset_status='ready';
 update public.std_projects set project_payload=result_payload,
   progress_payload=coalesce(p.progress_payload,'{}'::jsonb)||jsonb_build_object('ready_scene_count',count_ready,
       'last_asset_uploaded_at',clock_timestamp(),'last_atomic_upload_asset_id',p_asset_id),
   status=case when p.status='claimed' then 'in_progress' else p.status end,updated_at=clock_timestamp()
 where id=p.id returning updated_at into p.updated_at;
 return jsonb_build_object('success',true,'already_attached',false,'updated_at',p.updated_at,'asset_status',case when ready then 'ready' else 'missing' end);
end $$;
revoke all on function public.std_attach_revision_asset(uuid,text,timestamptz,text,uuid,integer,jsonb) from public,anon,authenticated;
grant execute on function public.std_attach_revision_asset(uuid,text,timestamptz,text,uuid,integer,jsonb) to service_role;
