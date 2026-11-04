-- The project list only needs output readiness, not prompts, cast geometry or
-- subtitle text. Keep this separate from the full admin/editor status RPC.
create or replace function public.std_list_compact_structure(p jsonb) returns jsonb
language sql immutable security invoker set search_path='' as $$
 select case when p is null or p='null'::jsonb then null else
  jsonb_build_object(
   'required_video_scene_count',p->'required_video_scene_count',
   'video_scene_count',p->'video_scene_count', 'video_scenes',p->'video_scenes',
   'motion_graphic_video_scenes',p->'motion_graphic_video_scenes', 'comic_plan',p->'comic_plan',
   'scenes', case when p ? 'scenes' then
    (select coalesce(jsonb_agg(jsonb_build_object(
      'scene_number',s->'scene_number','scene_order',s->'scene_order',
      'scene_text',left(s->>'scene_text',1),'narration',left(s->>'narration',1),
      'image_url',s->'image_url','video_url',s->'video_url',
      'video_prompt_required',s->'video_prompt_required','video_generation_mode',s->'video_generation_mode') order by n),'[]'::jsonb)
     from jsonb_array_elements(case when jsonb_typeof(p->'scenes')='array' then p->'scenes' else '[]'::jsonb end) with ordinality a(s,n))
    else null end)
 end
$$;

create or replace function public.std_list_compact_payload(p jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare doc jsonb := coalesce(p,'{}'::jsonb) || '{}'::jsonb;
begin
 return jsonb_build_object(
  'required_video_scene_count',doc->'required_video_scene_count',
  'video_scene_count',doc->'video_scene_count','video_scenes',doc->'video_scenes',
  'script',left(doc->>'script',1),'pregenerated_script',left(doc->>'pregenerated_script',1),
  'audio_url',doc->'audio_url','tts_url',doc->'tts_url','thumbnail_url',doc->'thumbnail_url',
  'structure',public.std_list_compact_structure(doc->'structure'),
  'pregenerated_structure',public.std_list_compact_structure(doc->'pregenerated_structure'),
  'scenes',public.std_list_compact_structure(doc)->'scenes',
  'render_settings',jsonb_build_object('comic',doc#>'{render_settings,comic}'));
end $$;

create or replace function public.std_project_list_context(p_project_ids uuid[]) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
declare
 r record; payload jsonb; source_doc jsonb; progress_doc jsonb; result jsonb := '[]'::jsonb;
begin
 for r in select p.id,p.topic_queue_id,p.title,p.project_payload,p.source_payload,p.progress_payload
  from public.std_projects p where p.id=any(p_project_ids)
 loop
  payload := coalesce(r.project_payload,'{}'::jsonb) || '{}'::jsonb;
  source_doc := coalesce(r.source_payload,'{}'::jsonb) || '{}'::jsonb;
  progress_doc := coalesce(r.progress_payload,'{}'::jsonb) || '{}'::jsonb;
  -- Preserve the established full validation path for nonverbal projects.
  if payload->>'production_mode'='nonverbal_preschool' or payload#>>'{structure,production_mode}'='nonverbal_preschool' then
   result := result || public.std_project_status_context(array[r.id]);
   continue;
  end if;
  result := result || jsonb_build_array(jsonb_build_object(
   'id',r.id,'topic_queue_id',r.topic_queue_id,'title',r.title,
   'project_payload',public.std_list_compact_payload(payload),
   'source_payload',public.std_list_compact_payload(source_doc),
   'progress_payload',jsonb_build_object(
    'tts_completed',progress_doc->'tts_completed','subtitle_tts_completed',progress_doc->'subtitle_tts_completed',
    'script_changed_requires_audio_regeneration',progress_doc->'script_changed_requires_audio_regeneration',
    'thumbnail_completed',progress_doc->'thumbnail_completed','thumbnail_url',progress_doc->'thumbnail_url',
    'required_video_scene_count',progress_doc->'required_video_scene_count',
    'video_scene_count',progress_doc->'video_scene_count','video_scenes',progress_doc->'video_scenes')));
 end loop;
 return result;
end $$;

revoke all on function public.std_list_compact_structure(jsonb), public.std_list_compact_payload(jsonb), public.std_project_list_context(uuid[]) from public, anon, authenticated;
grant execute on function public.std_list_compact_structure(jsonb), public.std_list_compact_payload(jsonb), public.std_project_list_context(uuid[]) to service_role;
