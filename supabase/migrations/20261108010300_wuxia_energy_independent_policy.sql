-- Energy preparation remains active when mouth animation is disabled.
create or replace function public.wuxia_preparation_enabled(policy jsonb)
returns boolean language sql immutable security invoker set search_path=public as $$
 select (coalesce(policy->>'auto_prepare','false')='true' and coalesce(policy->>'enabled','true')<>'false')
 or (coalesce(policy#>>'{energy_auto,auto_prepare}','false')='true' and coalesce(policy#>>'{energy_auto,enabled}','false')='true')
$$;
revoke all on function public.wuxia_preparation_enabled(jsonb) from public,anon,authenticated;
grant execute on function public.wuxia_preparation_enabled(jsonb) to service_role;

create or replace function public.request_std_wuxia_mouth(p_project_id uuid,p_task text)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare p public.std_projects; a public.std_project_assets; inp jsonb; fp text; job uuid;
begin
 if p_task not in ('art','timing') then raise exception 'Invalid mouth task';end if;
 select * into p from public.std_projects where id=p_project_id for update;
 if p.id is null or p.submitted_at is not null or p.status in ('approved','canceled','cancelled','completed','paid') then return jsonb_build_object('state','closed');end if;
 if not public.wuxia_preparation_enabled(p.project_payload#>'{structure,wuxia_mouth_policy}')
 or p.project_payload#>>'{structure,wuxia_ae_package,contract}' is distinct from 'wuxia_still_ae_episode/v1' then return jsonb_build_object('state','disabled');end if;
 if p_task='timing' then
  select * into a from public.std_project_assets where project_id=p.id and id::text=p.project_payload->>'subtitle_source_audio_id'
   and asset_type='audio' and status in ('uploaded','assigned');
  if a.id is null or a.metadata->>'sha256' is null or jsonb_typeof(a.metadata->'subtitle_timeline') is distinct from 'array' then return jsonb_build_object('state','waiting_audio');end if;
 end if;
 inp:=public.wuxia_mouth_input(p.project_payload,p_task,case when a.id is not null then jsonb_build_object('id',a.id,'metadata',a.metadata,'file_name',a.file_name) else null end);
 fp:=encode(sha256(convert_to(inp::text,'UTF8')),'hex');
 select id into job from public.std_project_assets where project_id=p.id and metadata->>'kind'='wuxia_mouth_preparation' and metadata->>'fingerprint'=fp;
 if job is not null then
  update public.std_project_assets set metadata=metadata||jsonb_build_object('state','queued','worker_token',null,'retry_after',null),updated_at=now()
   where id=job and metadata->>'state' in ('canceled','superseded');
  return jsonb_build_object('job_id',job,'state','existing');end if;
 job:=gen_random_uuid();
 insert into public.std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
 values(job,p.id,'other','uploaded','wuxia-mouth-'||p_task||'.json','application/json',jsonb_build_object(
 'kind','wuxia_mouth_preparation','workflow_stage','preparation','state','queued','phase',p_task,'fingerprint',fp,'input',inp,'attempts',0));
 return jsonb_build_object('job_id',job,'state','queued');
end $$;

create or replace function public.claim_std_wuxia_mouth(p_token uuid)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare j public.std_project_assets; p public.std_projects;
begin
 for j in select a.* from public.std_project_assets a join public.std_projects project_row on project_row.id=a.project_id
 where a.metadata->>'kind'='wuxia_mouth_preparation' and project_row.submitted_at is null and project_row.status not in ('approved','canceled','cancelled','completed','paid')
 and ((a.metadata->>'state'='queued' and coalesce((a.metadata->>'retry_after')::timestamptz,'-infinity'::timestamptz)<=now())
 or (a.metadata->>'state'='processing' and a.updated_at<now()-interval '3 minutes'))
 order by a.created_at limit 100 for update of a skip locked loop
  if not pg_try_advisory_xact_lock(hashtextextended(j.project_id::text,71)) then continue;end if;
  if exists(select 1 from public.std_project_assets a where a.project_id=j.project_id and a.id<>j.id
   and a.metadata->>'kind'='wuxia_mouth_preparation' and a.metadata->>'state'='processing' and a.updated_at>=now()-interval '3 minutes') then continue;end if;
  select * into p from public.std_projects where id=j.project_id;
  if not public.wuxia_preparation_enabled(p.project_payload#>'{structure,wuxia_mouth_policy}') then
   update public.std_project_assets set metadata=metadata||'{"state":"canceled"}'::jsonb,updated_at=now() where id=j.id;continue;
  end if;
  update public.std_project_assets set metadata=metadata||jsonb_build_object('state','processing','worker_token',p_token,'error',null,'heartbeat_at',now()),updated_at=now() where id=j.id returning * into j;
  return to_jsonb(j);
 end loop;
 return null;
end $$;


create or replace function public.finish_std_wuxia_mouth(p_job_id uuid,p_token uuid,p_result jsonb)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare j public.std_project_assets; p public.std_projects; a public.std_project_assets; current_input jsonb; task text; pkg jsonb;
begin
 -- Same project -> asset lock order as enqueue/trigger; never invert it.
 select * into j from public.std_project_assets where id=p_job_id;
 if j.id is null then raise exception 'Mouth job missing';end if;
 select * into p from public.std_projects where id=j.project_id for update;
 select * into j from public.std_project_assets where id=p_job_id for update;
 if j.metadata->>'worker_token' is distinct from p_token::text or j.metadata->>'state'<>'processing' then raise exception 'Mouth worker lease lost';end if;
 task:=j.metadata->'input'->>'task';
 if p.submitted_at is not null or p.status in ('approved','canceled','cancelled','completed','paid') or not public.wuxia_preparation_enabled(p.project_payload#>'{structure,wuxia_mouth_policy}') then
  update public.std_project_assets set metadata=metadata||'{"state":"canceled"}'::jsonb,updated_at=now() where id=j.id;return jsonb_build_object('applied',false,'reason','closed');end if;
 if task='timing' then select * into a from public.std_project_assets where project_id=p.id and id::text=p.project_payload->>'subtitle_source_audio_id' and asset_type='audio' and status in ('uploaded','assigned');end if;
 current_input:=public.wuxia_mouth_input(p.project_payload,task,case when a.id is not null then jsonb_build_object('id',a.id,'metadata',a.metadata,'file_name',a.file_name) else null end);
 if current_input is distinct from j.metadata->'input' then
  update public.std_project_assets set metadata=metadata||'{"state":"superseded"}'::jsonb,updated_at=now() where id=j.id;
  perform public.request_std_wuxia_mouth(p.id,task);return jsonb_build_object('applied',false,'reason','source_changed');end if;
 pkg:=public.apply_wuxia_mouth_result(p.project_payload#>'{structure,wuxia_ae_package}',p_result,task='timing');
 update public.std_projects set project_payload=jsonb_set(project_payload,'{structure,wuxia_ae_package}',pkg),updated_at=now() where id=p.id;
 update public.std_project_assets set metadata=metadata||jsonb_build_object('state',case when p_result->'report'->>'state'='not_required' then 'not_required' else 'ready' end,'result',p_result,'error',null,'worker_token',null,'completed_at',now()),updated_at=now() where id=j.id;
 if task='art' then perform public.request_std_wuxia_mouth(p.id,'timing');end if;
 return jsonb_build_object('applied',true,'state',p_result->'report'->>'state');
end $$;

create or replace function public.queue_std_wuxia_mouth_after_save()
returns trigger language plpgsql security invoker set search_path=public as $$
begin
 if not public.wuxia_preparation_enabled(new.project_payload#>'{structure,wuxia_mouth_policy}') then return new;end if;
 if tg_op='INSERT' then
  perform public.request_std_wuxia_mouth(new.id,'art');perform public.request_std_wuxia_mouth(new.id,'timing');
 else
  if public.wuxia_mouth_source(old.project_payload->'structure') is distinct from public.wuxia_mouth_source(new.project_payload->'structure') then perform public.request_std_wuxia_mouth(new.id,'art');end if;
  if old.project_payload->'subtitles' is distinct from new.project_payload->'subtitles'
   or public.wuxia_mouth_source(old.project_payload->'structure') is distinct from public.wuxia_mouth_source(new.project_payload->'structure')
   or old.project_payload->>'subtitle_source_audio_id' is distinct from new.project_payload->>'subtitle_source_audio_id'
   or old.project_payload#>'{structure,wuxia_ae_package,mouth_preparation}' is distinct from new.project_payload#>'{structure,wuxia_ae_package,mouth_preparation}' then
   perform public.request_std_wuxia_mouth(new.id,'timing');end if;
 end if;
 return new;
end $$;

create or replace function public.publish_wuxia_topic_mouth_art(p_topic_id bigint,p_expected_package jsonb,p_result jsonb,p_expected_owner_email text default null)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare t public.topics_queue; current_source jsonb; expected_source jsonb; pkg jsonb;
begin
 select * into t from public.topics_queue where id=p_topic_id for update;
 if t.id is null or t.status<>'pending' or t.assigned_at is not null
  or not public.wuxia_preparation_enabled(t.pregenerated_structure->'wuxia_mouth_policy')
 then return jsonb_build_object('applied',false,'reason','disabled'); end if;
 if coalesce(nullif(t.assigned_employee_email,''),'') is distinct from coalesce(nullif(p_expected_owner_email,''),'')
 then return jsonb_build_object('applied',false,'reason','owner_changed'); end if;
 current_source:=public.wuxia_mouth_source(t.pregenerated_structure)->'package';
 expected_source:=public.wuxia_mouth_source(jsonb_build_object('wuxia_ae_package',p_expected_package))->'package';
 if current_source is distinct from expected_source then return jsonb_build_object('applied',false,'reason','source_changed'); end if;
 pkg:=public.apply_wuxia_mouth_result(t.pregenerated_structure->'wuxia_ae_package',p_result,false);
 update public.topics_queue set pregenerated_structure=jsonb_set(pregenerated_structure,'{wuxia_ae_package}',pkg) where id=t.id;
 return jsonb_build_object('applied',true,'state',p_result->'report'->>'state');
end $$;
revoke all on function public.publish_wuxia_topic_mouth_art(bigint,jsonb,jsonb,text) from public,anon,authenticated;
grant execute on function public.publish_wuxia_topic_mouth_art(bigint,jsonb,jsonb,text) to service_role;

