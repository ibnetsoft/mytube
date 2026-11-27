-- Incremental script-worker handoff. All changes are atomic and restricted to service_role.
create table if not exists public.script_worker_web_links (
 job_id text primary key references public.script_worker_jobs(id),
 topic_id bigint not null unique references public.topics_queue(id),
 project_id uuid not null unique references public.std_projects(id),
 created_at timestamptz not null default now()
);
alter table public.script_worker_web_links enable row level security;
revoke all on public.script_worker_web_links from public,anon,authenticated;
grant select,insert,update on public.script_worker_web_links to service_role;
create or replace function public.std_script_worker_deliver(p_job_id text, p_revision bigint, p_updates jsonb, p_fields jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare j public.script_worker_jobs%rowtype; p public.std_projects%rowtype; t public.topics_queue%rowtype;
 owner_id uuid; c jsonb; w jsonb; req jsonb; scene jsonb; u jsonb; f record; old jsonb; state jsonb; prior jsonb;
 script text; base_structure jsonb; v_topic_id integer; v_project_id uuid; count_scenes int; n int; current_prompt text; prev_prompt text;
begin
 select * into j from public.script_worker_jobs where id=p_job_id for update;
 if not found or j.revision<>p_revision or j.mode<>'new' or j.status in ('canceled','cancelled','running','queued') then raise exception '작업이 변경되었거나 실행 중입니다'; end if;
 c:=j.candidate; w:=c->'manual_workflow'; req:=j.request_data; script:=c->>'script';
 if coalesce(w#>>'{stages,0,status}','') not in ('review','approved') or nullif(btrim(script),'') is null or jsonb_typeof(c#>'{structure,scenes}')<>'array' then raise exception '등록할 대본이 필요합니다'; end if;
 base_structure:=(c->'structure') - 'manual_image_prompts' - 'manual_video_directions' - 'manual_ae_directions' - 'sfx_generation_plan' - 'cut_transition_plan' - 'scene_image_prompt_drafts';
 if jsonb_typeof(p_updates)<>'array' or jsonb_typeof(p_fields)<>'object' then raise exception '등록 입력 오류'; end if;
 if jsonb_array_length(p_updates)<>(select count(distinct x->>'scene_id') from jsonb_array_elements(p_updates) x) then raise exception '중복 씬 등록 입력 오류'; end if;
 select id into owner_id from auth.users where lower(email)='supapitmusic@gmail.com';
 if owner_id is null then raise exception '대상 계정을 찾을 수 없습니다'; end if;
 -- Source marker is authoritative; the locked job serializes retries.
 select topic_id,project_id into v_topic_id,v_project_id from public.script_worker_web_links where job_id=p_job_id;
 if v_topic_id is null and w ? 'topic_registration' then raise exception '기존 등록 프로젝트와의 연결을 먼저 확인하세요'; end if;
 if v_topic_id is null then
  count_scenes:=jsonb_array_length(c#>'{structure,scenes}');
  if count_scenes<1 or count_scenes>1000 then raise exception '씬 수 오류'; end if;
  insert into public.topics_queue(topic,generated_title,category_id,language,status,assigned_at,assigned_employee_email,
    assigned_script_style,assigned_image_style,assigned_duration_minutes,recommended_duration_minutes,total_scenes,image_scenes,video_scenes,
    pregenerated_script,pregenerated_script_status,pregenerated_structure,pregenerated_structure_status,progress_payload)
  values(j.title,j.title,nullif(req->>'category_id','')::int,coalesce(nullif(req->>'language',''),'ko'),'assigned',clock_timestamp(),'supapitmusic@gmail.com',
    req->>'script_style',req->>'image_style',nullif(req->>'duration_minutes','')::int,nullif(req->>'duration_minutes','')::int,count_scenes,count_scenes,0,
    script,'ready',base_structure,'ready',jsonb_build_object('source_script_job_id',p_job_id)) returning id into v_topic_id;
  insert into public.std_projects(topic_queue_id,user_id,employee_email,title,category_id,language,status,assigned_duration_minutes,script_style,image_style,source_payload,project_payload,progress_payload)
  values(v_topic_id,owner_id,'supapitmusic@gmail.com',j.title,nullif(req->>'category_id','')::bigint,coalesce(nullif(req->>'language',''),'ko'),'claimed',nullif(req->>'duration_minutes','')::int,req->>'script_style',req->>'image_style',
    jsonb_build_object('id',v_topic_id,'pregenerated_script',script,'pregenerated_structure',base_structure),
    jsonb_build_object('script',script,'original_worker_script',script,'structure',base_structure,'source_script_job_id',p_job_id,'render_settings','{}'::jsonb),
    jsonb_build_object('scene_count',count_scenes,'script_worker_delivery',jsonb_build_object('job_id',p_job_id,'prompts','{}'::jsonb,'fields','{}'::jsonb))) returning id into v_project_id;
  insert into public.script_worker_web_links(job_id,topic_id,project_id) values(p_job_id,v_topic_id,v_project_id);
  for scene in select value from jsonb_array_elements(c#>'{structure,scenes}') loop
    insert into public.std_project_scenes(project_id,scene_number,scene_title,scene_text,image_prompt,video_prompt,metadata)
    values(v_project_id,(scene->>'scene_number')::int,scene->>'title',coalesce(scene->>'scene_text',''),'','',scene);
  end loop;
 end if;
 select * into t from public.topics_queue where id=v_topic_id for update;
 select count(*) into n from public.std_projects where topic_queue_id=v_topic_id;
 if n<>1 then raise exception '연결된 프로젝트가 없거나 중복되었습니다'; end if;
 select * into p from public.std_projects where topic_queue_id=v_topic_id for update;
 if not found or p.id is distinct from v_project_id or p.user_id is distinct from owner_id or lower(p.employee_email)<>'supapitmusic@gmail.com' then raise exception '대상 프로젝트 소유권을 확인하세요'; end if;
 if p.status not in ('claimed','in_progress') or p.submitted_at is not null then raise exception '제출되었거나 편집할 수 없는 프로젝트입니다'; end if;
 if p.project_payload->>'original_worker_script' is distinct from script or p.project_payload->>'script' is distinct from script then raise exception '대본이 유저웹에서 변경되었거나 작업 대본과 다릅니다'; end if;
 state:=coalesce(p.progress_payload->'script_worker_delivery','{}'::jsonb);
 if state->>'job_id' is distinct from p_job_id then raise exception '프로젝트 작업 연결이 다릅니다'; end if;
 prior:=coalesce(state->'prompts','{}'::jsonb);
 perform 1 from public.std_project_scenes where project_id=p.id order by id for update;
 for u in select value from jsonb_array_elements(p_updates) loop
   select count(*),min(image_prompt) into n,current_prompt from public.std_project_scenes where project_id=p.id and metadata->>'scene_id'=u->>'scene_id';
   if n<>1 then raise exception '씬 연결이 없거나 중복되었습니다: %',u->>'scene_id'; end if;
   if u->>'cut_id' is not null and exists(select 1 from public.std_project_scenes s where s.project_id=p.id and s.metadata->>'scene_id'=u->>'scene_id' and nullif(s.metadata->>'cut_id','') is not null and s.metadata->>'cut_id'<>u->>'cut_id') then raise exception '유저웹 컷 연결이 다릅니다: %',u->>'scene_id'; end if;
   prev_prompt:=prior->>(u->>'scene_id');
   if coalesce(current_prompt,'')<>coalesce(u->>'image_prompt','') and coalesce(current_prompt,'')<>coalesce(prev_prompt,'') then raise exception '유저웹 이미지 프롬프트가 변경되었습니다: %',u->>'scene_id'; end if;
 end loop;
 for f in select key,value from jsonb_each(p_fields) loop
   if f.key not in ('manual_image_prompts','manual_video_directions','manual_ae_directions','sfx_generation_plan','cut_transition_plan') then raise exception '지원하지 않는 항목'; end if;
   old:=p.project_payload#>array['structure',f.key];
   if old is distinct from f.value and old is distinct from state#>array['fields',f.key] and old is not null then raise exception '유저웹 항목이 변경되었습니다: %',f.key; end if;
 end loop;
 for u in select value from jsonb_array_elements(p_updates) loop
   update public.std_project_scenes set image_prompt=u->>'image_prompt',metadata=metadata || case when u->>'cut_id' is not null then jsonb_build_object('cut_id',u->>'cut_id') else '{}'::jsonb end,updated_at=clock_timestamp() where project_id=p.id and metadata->>'scene_id'=u->>'scene_id';
   prior:=jsonb_set(prior,array[u->>'scene_id'],to_jsonb(u->>'image_prompt'),true);
 end loop;
 for f in select key,value from jsonb_each(p_fields) loop
   p.project_payload:=jsonb_set(p.project_payload,array['structure',f.key],f.value,true);
 end loop;
 state:=state || jsonb_build_object('prompts',prior,'fields',coalesce(state->'fields','{}'::jsonb)||p_fields,'job_revision',p_revision,'delivered_at',clock_timestamp());
 update public.std_projects set project_payload=p.project_payload,progress_payload=jsonb_set(progress_payload,'{script_worker_delivery}',state,true),updated_at=clock_timestamp() where id=p.id;
 return jsonb_build_object('topic_id',v_topic_id,'project_id',p.id,'scene_count',(select count(*) from public.std_project_scenes where project_id=p.id),'prompt_count',jsonb_array_length(p_updates),'fields',p_fields,'job_revision',p_revision);
end $$;
revoke all on function public.std_script_worker_deliver(text,bigint,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.std_script_worker_deliver(text,bigint,jsonb,jsonb) to service_role;
