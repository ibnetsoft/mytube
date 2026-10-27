-- Submitted video postwork cannot bypass actual scene and final-output review.
create or replace function public.assert_std_submitted_video_postwork_review(p_snapshot jsonb, p_results jsonb, p_review jsonb)
returns void language plpgsql set search_path=public as $guard$
declare
 s jsonb; r jsonb; proof jsonb; b jsonb; f jsonb; check_id text;
 needed text[]; target_count integer:=0; voice_hash text;
begin
 if p_snapshot->>'submitted_video_postwork' is distinct from 'submitted_video_postwork/v1' then return; end if;
 voice_hash:=p_review->>'final_voice_sha256';
 if p_review->>'submitted_video_postwork_contract' is distinct from 'submitted_video_postwork/v1'
  or p_review->'passed' is distinct from 'true'::jsonb or p_review->'skipped'='true'::jsonb
  or p_review->>'reviewer' is distinct from 'local_codex_cli'
  or coalesce(voice_hash,'') !~ '^[a-f0-9]{64}$' then raise exception 'Submitted video postwork requires actual reviewed output'; end if;
 if jsonb_typeof(p_snapshot->'scenes') is distinct from 'array'
  or jsonb_typeof(p_results) is distinct from 'array'
  or jsonb_typeof(p_review->'scenes') is distinct from 'array'
  or jsonb_array_length(p_review->'scenes') is distinct from jsonb_array_length(p_snapshot->'scenes') then
  raise exception 'Submitted video postwork review scenes incomplete';
 end if;
 for s in select value from jsonb_array_elements(p_snapshot->'scenes') loop
  select value into r from jsonb_array_elements(p_results) where value->>'number'=s->>'number';
  if r is null or r->'review'->'passed' is distinct from 'true'::jsonb
   or r->'review'->'skipped'='true'::jsonb or r->'review'->>'render_sha256' is distinct from r->>'sha256'
   or coalesce(r->>'sha256','') !~ '^[a-f0-9]{64}$'
   or r->'review'->>'final_voice_sha256' is distinct from voice_hash then
   raise exception 'Submitted video postwork scene review missing or stale';
  end if;
  if s->'postwork'->>'contract'='submitted_video_postwork/v1' or s->'still_mouth'->>'contract'='prepared_still_mouth/v1' then
   needed:=array['postwork_narrative_fit','source_playback_preserved','transition_plan'];
   if coalesce(s->'postwork'->'mouth_required',s->'still_mouth'->'mouth_required')='true'::jsonb then
    needed:=needed||array['dialogue_mouth_timing','tracked_mouth_alignment'];
   end if;
   if jsonb_typeof(r->'review'->'batches') is distinct from 'array' or jsonb_array_length(r->'review'->'batches')=0 then
    raise exception 'Submitted video postwork actual frame review receipt required';
   end if;
   for b in select value from jsonb_array_elements(r->'review'->'batches') loop
    if b->'passed' is distinct from 'true'::jsonb or b->'critical_issues' is distinct from '[]'::jsonb or jsonb_typeof(b->'checks') is distinct from 'array' then
     raise exception 'Submitted video postwork frame review failed';
    end if;
    foreach check_id in array needed loop
     if (select count(*) from jsonb_array_elements(b->'checks') c where c->>'id'=check_id)=1
      and exists(select 1 from jsonb_array_elements(b->'checks') c where c->>'id'=check_id and c->'passed'='true'::jsonb and nullif(btrim(c->>'evidence'),'') is not null) then
      null;
     else raise exception 'Submitted video postwork required check missing: %',check_id;
     end if;
    end loop;
   end loop;
  end if;
  if s->'postwork'->>'contract'='submitted_video_postwork/v1' then
   target_count:=target_count+1; proof:=r->'submitted_video_postwork';
   if (s->>'number')::integer not between 1 and 18 or s->>'source_kind' is distinct from 'video'
    or proof->>'contract' is distinct from 'submitted_video_postwork/v1'
    or proof->>'final_voice_sha256' is distinct from voice_hash
    or coalesce(proof->>'source_sha256','') !~ '^[a-f0-9]{64}$'
    or proof->'playback_rate' is distinct from '1'::jsonb
    or proof->'mouth_required' is distinct from s->'postwork'->'mouth_required' then
    raise exception 'Submitted video postwork source/voice evidence invalid';
   end if;
   if s->'postwork'->'mouth_required'='true'::jsonb and proof->'mouth_applied' is distinct from 'true'::jsonb then
    if jsonb_typeof(s->'postwork'->'dialogue') is distinct from 'array'
     or jsonb_array_length(s->'postwork'->'dialogue')=0
     or jsonb_typeof(proof->'offscreen_speakers') is distinct from 'array'
     or exists(select 1 from jsonb_array_elements(s->'postwork'->'dialogue') d where nullif(d->>'speaker','') is null or not (coalesce(proof->'offscreen_speakers','[]'::jsonb) @> jsonb_build_array(d->>'speaker'))) then
     raise exception 'Required mouth postwork cannot silently fall back to original video';
    end if;
   end if;
  end if;
 end loop;
 if target_count=0 then raise exception 'Submitted video postwork has no target scenes'; end if;
 for f in select value from jsonb_array_elements(p_review->'scenes') loop
  if f->'passed' is distinct from 'true'::jsonb or f->'critical_issues' is distinct from '[]'::jsonb or jsonb_typeof(f->'checks') is distinct from 'array' then
   raise exception 'Final submitted video postwork review failed';
  end if;
  foreach check_id in array array['captions','scene_boundary','visual_quality','postwork_continuity','voice_clock_preserved'] loop
   if (select count(*) from jsonb_array_elements(f->'checks') c where c->>'id'=check_id)=1
    and exists(select 1 from jsonb_array_elements(f->'checks') c where c->>'id'=check_id and c->'passed'='true'::jsonb and nullif(btrim(c->>'evidence'),'') is not null) then
    null;
   else raise exception 'Final submitted video postwork required check missing: %',check_id;
   end if;
  end loop;
 end loop;
end $guard$;
revoke all on function public.assert_std_submitted_video_postwork_review(jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.assert_std_submitted_video_postwork_review(jsonb,jsonb,jsonb) to service_role;

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
 if frozen->>'submitted_video_postwork'='submitted_video_postwork/v1' then
  if job.metadata->>'kind' is distinct from 'motion_automation' then raise exception 'Submitted video postwork requires Adobe AE worker'; end if;
  skip_review:=false;
  perform public.assert_std_submitted_video_postwork_review(frozen,job.metadata->'results',p_review);
 end if;
 if job.metadata->>'kind'='horizontal_webtoon_automation' and (frozen->'renderer'->>'engine' is distinct from 'ae_horizontal_webtoon' or p_review->'renderer' is distinct from frozen->'renderer' or (not coalesce(skip_review,false) and (p_review->'passed' is distinct from 'true'::jsonb or p_review->>'reviewer' is distinct from 'local_codex_cli'))) then raise exception 'Horizontal webtoon AE review evidence required'; end if;
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

