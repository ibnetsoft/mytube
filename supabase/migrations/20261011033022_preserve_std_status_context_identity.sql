-- Preserve null fields inside cast/receipts: their JSON identity binds approvals.
create or replace function public.std_compact_structure(p jsonb) returns jsonb
language sql immutable security invoker set search_path = '' as $$
 select case when p is null or p='null'::jsonb then null else (
 jsonb_build_object('main_character', p->'main_character', 'supporting_characters', p->'supporting_characters', 'scene_cast', p->'scene_cast', 'required_video_scene_count', p->'required_video_scene_count', 'video_scene_count', p->'video_scene_count', 'video_scenes', p->'video_scenes', 'comic_plan', p->'comic_plan') || jsonb_build_object('scenes', case when p ? 'scenes' then (select coalesce(jsonb_agg((jsonb_build_object('scene_number', s->'scene_number', 'scene_order', s->'scene_order', 'scene_text', s->'scene_text', 'narration', s->'narration', 'image_url', s->'image_url', 'video_url', s->'video_url', 'video_prompt_required', s->'video_prompt_required', 'video_generation_mode', s->'video_generation_mode') || jsonb_build_object('metadata', jsonb_build_object('cowork_image_asset', jsonb_build_object('speaker_geometry', s#>'{metadata,cowork_image_asset,speaker_geometry}')))) order by n), '[]'::jsonb)
from jsonb_array_elements(case when jsonb_typeof(p->'scenes')='array' then p->'scenes' else '[]'::jsonb end) with ordinality a(s,n)) else null end)) end
$$;
create or replace function public.std_compact_project_payload(p jsonb) returns jsonb
language sql immutable security invoker set search_path = '' as $$
 select (jsonb_build_object('topic_queue_id', p->'topic_queue_id', 'main_character', p->'main_character', 'supporting_characters', p->'supporting_characters', 'required_video_scene_count', p->'required_video_scene_count', 'video_scene_count', p->'video_scene_count', 'video_scenes', p->'video_scenes', 'script', p->'script', 'pregenerated_script', p->'pregenerated_script', 'audio_url', p->'audio_url', 'tts_url', p->'tts_url', 'thumbnail_url', p->'thumbnail_url') || jsonb_build_object(
 'structure',public.std_compact_structure(p->'structure'),
 'pregenerated_structure',public.std_compact_structure(p->'pregenerated_structure'),
 'scenes',public.std_compact_structure(p)->'scenes',
 'render_settings',jsonb_build_object('comic',p#>'{render_settings,comic}'),
 'subtitles',case when jsonb_typeof(p->'subtitles')='array' then (
 select coalesce(jsonb_agg((jsonb_build_object('scene_number', s->'scene_number', 'text', s->'text', 'dialogue_kind', s->'dialogue_kind', 'dialogue_speaker', s->'dialogue_speaker', 'editor_speaker', s->'editor_speaker', 'speaker', s->'speaker')) order by n),'[]'::jsonb)
 from jsonb_array_elements(p->'subtitles') with ordinality a(s,n)) else null end))
$$;
create or replace function public.std_project_status_context(p_project_ids uuid[]) returns jsonb
language sql stable security invoker set search_path = '' as $$
 select coalesce(jsonb_agg((to_jsonb(p)-'project_payload'-'source_payload'-'progress_payload') || jsonb_build_object(
 'project_payload',public.std_compact_project_payload(p.project_payload::jsonb),
 'source_payload',public.std_compact_project_payload(p.source_payload::jsonb),
 'progress_payload', (jsonb_build_object(
 'tts_completed',p.progress_payload::jsonb->'tts_completed',
 'subtitle_tts_completed',p.progress_payload::jsonb->'subtitle_tts_completed',
 'script_changed_requires_audio_regeneration',p.progress_payload::jsonb->'script_changed_requires_audio_regeneration',
 'thumbnail_completed',p.progress_payload::jsonb->'thumbnail_completed',
 'thumbnail_url',p.progress_payload::jsonb->'thumbnail_url',
 'required_video_scene_count',p.progress_payload::jsonb->'required_video_scene_count',
 'video_scene_count',p.progress_payload::jsonb->'video_scene_count','video_scenes',p.progress_payload::jsonb->'video_scenes')),
 'generated_structure',coalesce(public.std_compact_structure(t.pregenerated_structure::jsonb),public.std_compact_structure(p.project_payload::jsonb->'structure'),public.std_compact_structure(p.source_payload::jsonb->'pregenerated_structure'))
 )), '[]'::jsonb)
 from public.std_projects p left join public.topics_queue t on t.id=coalesce(p.topic_queue_id::text,p.source_payload::jsonb->>'topic_queue_id',p.project_payload::jsonb->>'topic_queue_id')::bigint
 where p.id=any(p_project_ids)
$$;
revoke all on function public.std_compact_structure(jsonb),public.std_compact_project_payload(jsonb),public.std_project_status_context(uuid[]) from public, anon, authenticated;
grant execute on function public.std_compact_structure(jsonb),public.std_compact_project_payload(jsonb),public.std_project_status_context(uuid[]) to service_role;
