-- A distinct committed queue kind prevents old workers from rendering horizontal webtoon jobs in Adobe.
create or replace function public.register_std_horizontal_webtoon_pipeline(p_project_id uuid,p_user_id uuid,
 p_updated_at timestamptz,p_run_id uuid,p_job_id uuid,p_manifest jsonb,p_hash text)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare frozen jsonb; result jsonb; kind text;
begin
 frozen:=(p_manifest->'automation'->>'snapshot_json')::jsonb;
 if frozen->'motion'->>'edit_mode' is distinct from 'horizontal_webtoon'
  or frozen->'renderer'->>'engine' is distinct from 'ae_horizontal_webtoon'
  or frozen->'motion'->>'aspect' is distinct from '16:9'
  or frozen->'renderer'->>'version' is distinct from '1'
  or frozen->'motion'->'automation'->>'mode' is distinct from 'ae_only' then raise exception 'Invalid horizontal webtoon submission'; end if;
 result:=register_std_motion_pipeline(p_project_id,p_user_id,p_updated_at,p_run_id,p_job_id,p_manifest,p_hash);
 if coalesce((result->>'already_submitted')::boolean,false) then
  select metadata->>'kind' into kind from std_project_assets where id=(result->>'job_id')::uuid;
  if kind is distinct from 'horizontal_webtoon_automation' then raise exception 'Project already submitted to another renderer'; end if;
  return result;
 end if;
 update std_project_assets set metadata=metadata||jsonb_build_object('kind','horizontal_webtoon_automation') where id=p_job_id;
 return result;
end $$;
revoke all on function public.register_std_horizontal_webtoon_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.register_std_horizontal_webtoon_pipeline(uuid,uuid,timestamptz,uuid,uuid,jsonb,text) to service_role;

CREATE OR REPLACE FUNCTION public.patch_std_motion_job(p_job_id uuid, p_token text, p_patch jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
declare result jsonb;
begin
 if p_patch is null or jsonb_typeof(p_patch)<>'object' then raise exception 'Invalid motion patch'; end if;
 if p_patch ?| array['input','fingerprint','worker_token','kind','pipeline_run_id','submission_id','version'] then raise exception 'Frozen job fields cannot change'; end if;
 update std_project_assets set metadata=metadata||p_patch,updated_at=now()
 where id=p_job_id and metadata->>'kind' in ('motion_automation','effectcraft_automation','filmcraft_automation','horizontal_webtoon_automation') and metadata->>'state'='processing'
 and metadata->>'worker_token'=p_token returning metadata into result;
 if result is null then raise exception 'Motion worker lease lost'; end if;
 return result;
end $function$
;

CREATE OR REPLACE FUNCTION public.complete_std_motion_job(p_job_id uuid, p_token text, p_asset_id uuid, p_final jsonb, p_review jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
declare job std_project_assets; p std_projects; frozen jsonb; version_number integer; stamp timestamptz:=now(); hash text; skip_review boolean;
begin
 select * into job from std_project_assets where id=p_job_id;
 select * into p from std_projects where id=job.project_id for update;
 select * into job from std_project_assets where id=p_job_id for update;
 if p.id is null or p.status in ('approved','canceled') then raise exception 'Project closed'; end if;
 if coalesce(job.metadata->>'kind','') not in ('motion_automation','effectcraft_automation','filmcraft_automation','horizontal_webtoon_automation') or job.metadata->>'worker_token' is distinct from p_token then raise exception 'Motion worker lease lost'; end if;
 if job.metadata->>'state'='complete' and job.metadata->'final'->>'sha256'=p_final->>'sha256' then return job.metadata; end if;
 if job.metadata->>'state' is distinct from 'processing' then raise exception 'Motion worker lease lost'; end if;
 frozen:=(job.metadata->'input'->>'snapshot_json')::jsonb;
 if job.metadata->>'kind'='effectcraft_automation' and (frozen->'renderer'->>'engine' is distinct from 'effectcraft'
   or p_review->'renderer' is distinct from frozen->'renderer') then raise exception 'EffectCraft renderer evidence required'; end if;
 if job.metadata->>'kind'='filmcraft_automation' and (frozen->'renderer'->>'engine' is distinct from 'filmcraft'
   or p_review->'renderer' is distinct from frozen->'renderer') then raise exception 'FilmCraft renderer evidence required'; end if;
 skip_review := (job.metadata->>'review_policy'='skip_user_requested/v1' and nullif(job.metadata->>'review_policy_authorization','') is not null) or (frozen->'execution_policy'->>'review_policy'='skip_user_requested/v1' and frozen->'execution_policy'->>'authorization'='default_submission_existing_assets_without_review');
 if job.metadata->>'kind'='horizontal_webtoon_automation' and (frozen->'renderer'->>'engine' is distinct from 'ae_horizontal_webtoon' or p_review->'renderer' is distinct from frozen->'renderer' or p_review->'passed' is distinct from 'true'::jsonb or p_review->>'reviewer' is distinct from 'local_codex_cli') then raise exception 'Horizontal webtoon AE review evidence required'; end if;
 hash:=p_final->>'sha256';
 if hash is null or hash !~ '^[a-f0-9]{64}$' or p_final->>'gcs_bucket' is null
  or p_final->>'gcs_path' is distinct from 'std-motion/'||p_job_id||'/final/'||hash||'.mp4'
  or p_review->>'render_sha256' is distinct from hash then raise exception 'Final output evidence required'; end if;
 if skip_review then
  if p_review->'skipped' is distinct from 'true'::jsonb or p_review->>'status' is distinct from 'not_reviewed_user_requested' or p_review->>'method' is distinct from 'user_requested_review_bypass' or p_review->>'final_voice_sha256' !~ '^[a-f0-9]{64}$' then raise exception 'Explicit review skip receipt required'; end if;
 else
  if p_review->'passed' is distinct from 'true'::jsonb or p_review->>'reviewer' is distinct from 'local_codex_cli' or jsonb_array_length(p_review->'scenes') is distinct from jsonb_array_length(frozen->'scenes') then raise exception 'Reviewed output evidence required'; end if;
 end if;
 select coalesce(max((metadata->>'render_version')::integer),0)+1 into version_number from remote_render_queue where metadata->>'std_web_project_id'=p.id::text;
 insert into std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
 values(p_asset_id,p.id,'video','uploaded','motion-final.mp4','video/mp4',p_final||jsonb_build_object('kind','motion_final','job_id',p_job_id,'review',p_review));
 insert into remote_render_queue(id,project_id,project_name,email,status,progress,message,completed_at,render_mode,result_file_id,result_file_name,metadata)
 values(p_job_id,1900000000,p.title,p.employee_email,'completed',100,case when skip_review then 'Render complete; output review skipped at user request' else 'Codex actual-output review complete; administrator review pending' end,stamp,'gcs_api',
  'gs://'||(p_final->>'gcs_bucket')||'/'||(p_final->>'gcs_path'),'motion-final.mp4',
  p_final||jsonb_build_object('std_web_project_id',p.id,'topic_queue_id',p.topic_queue_id,'render_version',version_number,
    'motion_automation_job_id',p_job_id,'admin_publish_status','pending_review','admin_action_required','review_and_upload','output_review',p_review));
 update std_project_assets set metadata=metadata||jsonb_build_object('state','complete','phase','complete','progress',case when skip_review then '렌더 완료 · 사용자 요청으로 검수 생략' else 'Codex 출력 검수 완료 · 관리자 게시 대기' end,
  'review',p_review,'final',p_final||jsonb_build_object('asset_id',p_asset_id,'render_queue_id',p_job_id)),updated_at=stamp where id=p_job_id;
 update std_pipeline_runs set status='complete',render_queue_id=p_job_id,updated_at=stamp where id=(job.metadata->>'pipeline_run_id')::uuid;
 update std_project_submissions set metadata=metadata||jsonb_build_object('postprocess_status','complete','remote_render_queue_id',p_job_id)
 where id=(job.metadata->>'submission_id')::uuid;
 update std_projects set progress_payload=progress_payload||jsonb_build_object('postprocess_status','complete','remote_render_queue_id',p_job_id,
  'latest_render_version',version_number,'admin_publish_status','pending_review'),updated_at=stamp where id=p.id;
 select metadata into p_final from std_project_assets where id=p_job_id;
 return p_final;
end $function$
;
