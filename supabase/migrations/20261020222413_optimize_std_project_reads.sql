-- Materialize the payload once. Repeated JSON operators on TOASTed source
-- documents used to decompress the same multi-megabyte value for every field.
create or replace function public.std_compact_project_payload(p jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare
 doc jsonb := p || '{}'::jsonb;
 summary jsonb;
 subtitles jsonb;
begin
 select coalesce(jsonb_object_agg(key,value),'{}'::jsonb) into summary
 from jsonb_each(case when jsonb_typeof(doc)='object' then doc else '{}'::jsonb end)
 where key=any(array['topic_queue_id','main_character','supporting_characters',
 'required_video_scene_count','video_scene_count','video_scenes','script',
 'pregenerated_script','audio_url','tts_url','thumbnail_url']);
 if jsonb_typeof(doc->'subtitles')='array' then
  select coalesce(jsonb_agg(jsonb_build_object('scene_number',s->'scene_number',
   'text',s->'text','dialogue_override',s->'dialogue_override',
   'dialogue_kind',s->'dialogue_kind','dialogue_speaker',s->'dialogue_speaker',
   'editor_speaker',s->'editor_speaker','speaker',s->'speaker') order by n),'[]'::jsonb)
  into subtitles from jsonb_array_elements(doc->'subtitles') with ordinality a(s,n);
 end if;
 return summary || jsonb_build_object(
 'structure',public.std_compact_structure(doc->'structure'),
 'pregenerated_structure',public.std_compact_structure(doc->'pregenerated_structure'),
 'scenes',public.std_compact_structure(doc)->'scenes',
 'render_settings',jsonb_build_object('comic',doc#>'{render_settings,comic}'),
 'subtitles',subtitles);
end $$;

-- Loop over the small set of requested rows and keep JSON inputs in local
-- variables. Never convert the complete project row to JSON merely to delete
-- its large payload fields afterwards. Keep receipt/cast identity unchanged.
create or replace function public.std_project_status_context(p_project_ids uuid[]) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
declare
 row_data record;
 payload jsonb;
 source_doc jsonb;
 progress_doc jsonb;
 generated jsonb;
 cast_doc jsonb;
 result jsonb := '[]'::jsonb;
begin
 for row_data in
  select p.id,p.topic_queue_id,p.user_id,p.employee_email,p.title,p.category_id,
   p.language,p.status,p.assigned_duration_minutes,p.estimated_payout,
   p.script_style,p.image_style,p.drive_folder_id,p.submitted_at,p.reviewed_at,
   p.reviewed_by,p.created_at,p.updated_at,p.project_payload,p.source_payload,p.progress_payload
  from public.std_projects p where p.id=any(p_project_ids)
 loop
  payload := row_data.project_payload || '{}'::jsonb;
  source_doc := row_data.source_payload || '{}'::jsonb;
  progress_doc := row_data.progress_payload || '{}'::jsonb;
  generated := null;
  select t.pregenerated_structure into generated from public.topics_queue t
   where t.id=coalesce(row_data.topic_queue_id::text,source_doc->>'topic_queue_id',payload->>'topic_queue_id')::bigint;
  generated := coalesce(nullif(generated,'null'::jsonb),payload->'structure',source_doc->'pregenerated_structure');
  cast_doc := jsonb_build_object(
   'main',coalesce(nullif(payload#>'{structure,main_character}','null'::jsonb),nullif(payload->'main_character','null'::jsonb),'{}'::jsonb),
   'supporting',coalesce(nullif(payload#>'{structure,supporting_characters}','null'::jsonb),nullif(payload->'supporting_characters','null'::jsonb),'[]'::jsonb),
   'scene_cast',coalesce(nullif(payload#>'{structure,scene_cast}','null'::jsonb),'[]'::jsonb));
  result := result || jsonb_build_array(jsonb_build_object(
   'id',row_data.id,'topic_queue_id',row_data.topic_queue_id,'user_id',row_data.user_id,
   'employee_email',row_data.employee_email,'title',row_data.title,'category_id',row_data.category_id,
   'language',row_data.language,'status',row_data.status,'assigned_duration_minutes',row_data.assigned_duration_minutes,
   'estimated_payout',row_data.estimated_payout,'script_style',row_data.script_style,'image_style',row_data.image_style,
   'drive_folder_id',row_data.drive_folder_id,'submitted_at',row_data.submitted_at,'reviewed_at',row_data.reviewed_at,
   'reviewed_by',row_data.reviewed_by,'created_at',row_data.created_at,'updated_at',row_data.updated_at,
   'project_payload',public.std_compact_project_payload(payload),
   'source_payload',public.std_compact_project_payload(source_doc),
   'progress_payload',jsonb_build_object(
    'tts_completed',progress_doc->'tts_completed','subtitle_tts_completed',progress_doc->'subtitle_tts_completed',
    'script_changed_requires_audio_regeneration',progress_doc->'script_changed_requires_audio_regeneration',
    'thumbnail_completed',progress_doc->'thumbnail_completed','thumbnail_url',progress_doc->'thumbnail_url',
    'required_video_scene_count',progress_doc->'required_video_scene_count',
    'video_scene_count',progress_doc->'video_scene_count','video_scenes',progress_doc->'video_scenes'),
   'generated_structure',public.std_compact_generated_structure(generated,cast_doc)));
 end loop;
 return result;
end $$;
revoke all on function public.std_compact_project_payload(jsonb),public.std_project_status_context(uuid[]) from public,anon,authenticated;
grant execute on function public.std_compact_project_payload(jsonb),public.std_project_status_context(uuid[]) to service_role;
