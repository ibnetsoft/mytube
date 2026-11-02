create or replace function public.std_web_scene_array(p jsonb) returns jsonb
language sql immutable security invoker set search_path='' as $$
 select case when jsonb_typeof(p)='array' then coalesce((select jsonb_agg(
   s - array['scene_direction_plan','ae_directorial_plan','ae_motion_plan','ae_effect_plan',
     'psd_layer_plan','local_layer_plan','image_generation_policy','video_keyframe_plan','shot_design','joint_motion_plan'] order by n)
   from jsonb_array_elements(p) with ordinality x(s,n)),'[]'::jsonb) else p end
$$;
create or replace function public.std_web_structure(p jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare d jsonb:=p;
begin
 if jsonb_typeof(d) is distinct from 'object' then return d; end if;
 d:=d - array['scene_direction_plans','ae_motion_plans','ae_effect_plans','psd_layer_prompts','image_generation_policy'];
 if jsonb_typeof(d->'scenes')='array' then d:=jsonb_set(d,'{scenes}',public.std_web_scene_array(d->'scenes'),false); end if;
 return d;
end $$;
create or replace function public.std_user_web_project(p_id uuid) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
declare p public.std_projects%rowtype; doc jsonb; src jsonb;
begin
 select * into p from public.std_projects where id=p_id;
 if not found then return null; end if;
 doc:=coalesce(p.project_payload,'{}'::jsonb);
 if jsonb_typeof(doc->'structure')='object' then doc:=jsonb_set(doc,'{structure}',public.std_web_structure(doc->'structure'),false); end if;
 if jsonb_typeof(doc->'scenes')='array' then doc:=jsonb_set(doc,'{scenes}',public.std_web_scene_array(doc->'scenes'),false); end if;
 src:=coalesce(p.source_payload,'{}'::jsonb);
 if jsonb_typeof(src->'pregenerated_structure')='object' then src:=jsonb_set(src,'{pregenerated_structure}',public.std_web_structure(src->'pregenerated_structure'),false); end if;
 return (to_jsonb(p)-'project_payload'-'source_payload') || jsonb_build_object('project_payload',doc,'source_payload',src);
end $$;
create or replace function public.std_user_web_topic_structure(p_id bigint) returns jsonb
language sql stable security invoker set search_path='' as $$
 select public.std_web_structure(pregenerated_structure) from public.topics_queue where id=p_id
$$;
revoke all on function public.std_web_scene_array(jsonb),public.std_web_structure(jsonb),public.std_user_web_project(uuid),public.std_user_web_topic_structure(bigint) from public,anon,authenticated;
grant execute on function public.std_web_scene_array(jsonb),public.std_web_structure(jsonb),public.std_user_web_project(uuid),public.std_user_web_topic_structure(bigint) to service_role;
