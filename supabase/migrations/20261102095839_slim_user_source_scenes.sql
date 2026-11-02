create or replace function public.std_web_source_structure(p jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare d jsonb:=public.std_web_structure(p); rows jsonb;
begin
 if jsonb_typeof(d->'scenes')='array' then
  select coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
   'scene_number',s->'scene_number','scene_order',s->'scene_order','image_url',s->'image_url',
   'image',s->'image','video_url',s->'video_url','video',s->'video','metadata',s->'metadata')) order by n),'[]'::jsonb)
  into rows from jsonb_array_elements(d->'scenes') with ordinality t(s,n);
  d:=jsonb_set(d,'{scenes}',rows,false);
 end if;
 return d;
end $$;
create or replace function public.std_user_web_project(p_id uuid) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
declare p public.std_projects%rowtype; doc jsonb; src jsonb;
begin
 select * into p from public.std_projects where id=p_id;
 if not found then return null; end if;
 doc:=coalesce(p.project_payload,'{}'::jsonb);
 if jsonb_typeof(doc#>'{structure,scenes}')='array' then
   doc:=doc-'scenes';
 elsif jsonb_typeof(doc->'scenes')='array' then doc:=jsonb_set(doc,'{scenes}',public.std_web_scene_array(doc->'scenes'),false); end if;
 if jsonb_typeof(doc->'structure')='object' then doc:=jsonb_set(doc,'{structure}',public.std_web_structure(doc->'structure'),false); end if;
 src:=coalesce(p.source_payload,'{}'::jsonb);
 if jsonb_typeof(src->'pregenerated_structure')='object' then src:=jsonb_set(src,'{pregenerated_structure}',public.std_web_source_structure(src->'pregenerated_structure'),false); end if;
 return (to_jsonb(p)-'project_payload'-'source_payload') || jsonb_build_object('project_payload',doc,'source_payload',src);
end $$;
create or replace function public.std_user_web_topic_structure(p_id bigint) returns jsonb
language sql stable security invoker set search_path='' as $$
 select public.std_web_source_structure(pregenerated_structure) from public.topics_queue where id=p_id
$$;
revoke all on function public.std_web_source_structure(jsonb) from public,anon,authenticated;
grant execute on function public.std_web_source_structure(jsonb) to service_role;
