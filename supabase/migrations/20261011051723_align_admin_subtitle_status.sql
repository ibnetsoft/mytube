-- Keep AI dialogue annotations and user override in the compact admin projection.
create or replace function public.std_compact_structure(p jsonb) returns jsonb
language sql immutable security invoker set search_path = '' as $$
 select case when p is null or p='null'::jsonb then null else (
 jsonb_build_object('dialogue_annotations',p->'dialogue_annotations','main_character', p->'main_character', 'supporting_characters', p->'supporting_characters', 'scene_cast', p->'scene_cast', 'required_video_scene_count', p->'required_video_scene_count', 'video_scene_count', p->'video_scene_count', 'video_scenes', p->'video_scenes', 'comic_plan', p->'comic_plan') || jsonb_build_object('scenes', case when p ? 'scenes' then (select coalesce(jsonb_agg((jsonb_build_object('scene_number', s->'scene_number', 'scene_order', s->'scene_order', 'scene_text', s->'scene_text', 'narration', s->'narration', 'image_url', s->'image_url', 'video_url', s->'video_url', 'video_prompt_required', s->'video_prompt_required', 'video_generation_mode', s->'video_generation_mode')) order by n), '[]'::jsonb)
from jsonb_array_elements(case when jsonb_typeof(p->'scenes')='array' then p->'scenes' else '[]'::jsonb end) with ordinality a(s,n)) else null end)) end
$$;
create or replace function public.std_compact_project_payload(p jsonb) returns jsonb
language sql immutable security invoker set search_path = '' as $$
 select jsonb_strip_nulls(jsonb_build_object('topic_queue_id', p->'topic_queue_id', 'main_character', p->'main_character', 'supporting_characters', p->'supporting_characters', 'required_video_scene_count', p->'required_video_scene_count', 'video_scene_count', p->'video_scene_count', 'video_scenes', p->'video_scenes', 'script', p->'script', 'pregenerated_script', p->'pregenerated_script', 'audio_url', p->'audio_url', 'tts_url', p->'tts_url', 'thumbnail_url', p->'thumbnail_url') || jsonb_build_object(
 'structure',public.std_compact_structure(p->'structure'),
 'pregenerated_structure',public.std_compact_structure(p->'pregenerated_structure'),
 'scenes',public.std_compact_structure(p)->'scenes',
 'render_settings',jsonb_build_object('comic',p#>'{render_settings,comic}'),
 'subtitles',case when jsonb_typeof(p->'subtitles')='array' then (
 select coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object('scene_number', s->'scene_number', 'text', s->'text', 'dialogue_override',s->'dialogue_override','dialogue_kind', s->'dialogue_kind', 'dialogue_speaker', s->'dialogue_speaker', 'editor_speaker', s->'editor_speaker', 'speaker', s->'speaker')) order by n),'[]'::jsonb)
 from jsonb_array_elements(p->'subtitles') with ordinality a(s,n)) else null end))
$$;
