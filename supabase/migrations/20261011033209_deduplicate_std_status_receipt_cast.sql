-- Preserve null fields inside cast/receipts: their JSON identity binds approvals.
create or replace function public.std_compact_structure(p jsonb) returns jsonb
language sql immutable security invoker set search_path = '' as $$
 select case when p is null or p='null'::jsonb then null else (
 jsonb_build_object('main_character', p->'main_character', 'supporting_characters', p->'supporting_characters', 'scene_cast', p->'scene_cast', 'required_video_scene_count', p->'required_video_scene_count', 'video_scene_count', p->'video_scene_count', 'video_scenes', p->'video_scenes', 'comic_plan', p->'comic_plan') || jsonb_build_object('scenes', case when p ? 'scenes' then (select coalesce(jsonb_agg((jsonb_build_object('scene_number', s->'scene_number', 'scene_order', s->'scene_order', 'scene_text', s->'scene_text', 'narration', s->'narration', 'image_url', s->'image_url', 'video_url', s->'video_url', 'video_prompt_required', s->'video_prompt_required', 'video_generation_mode', s->'video_generation_mode')) order by n), '[]'::jsonb)
from jsonb_array_elements(case when jsonb_typeof(p->'scenes')='array' then p->'scenes' else '[]'::jsonb end) with ordinality a(s,n)) else null end)) end
$$;

-- Each image receipt used to repeat the complete cast. Compare it in the DB,
-- retaining one current cast and an explicit match result for each receipt.
create or replace function public.std_compact_generated_structure(p jsonb, current_cast jsonb) returns jsonb
language sql immutable security invoker set search_path='' as $$
 select jsonb_build_object('scenes',coalesce((select jsonb_agg(jsonb_build_object(
 'scene_number',s->'scene_number','scene_order',s->'scene_order','metadata',jsonb_build_object('cowork_image_asset',jsonb_build_object('speaker_geometry',
 case when jsonb_typeof(s#>'{metadata,cowork_image_asset,speaker_geometry}')='object' then
 ((s#>'{metadata,cowork_image_asset,speaker_geometry}')-'cast') || jsonb_build_object('cast_matches', jsonb_build_object(
 'main',coalesce(nullif(s#>'{metadata,cowork_image_asset,speaker_geometry,cast,main}','null'::jsonb),'{}'::jsonb),
 'supporting',coalesce(nullif(s#>'{metadata,cowork_image_asset,speaker_geometry,cast,supporting}','null'::jsonb),'[]'::jsonb),
 'scene_cast',coalesce(nullif(s#>'{metadata,cowork_image_asset,speaker_geometry,cast,scene_cast}','null'::jsonb),'[]'::jsonb))=current_cast)
 else null end))) order by n)
 from jsonb_array_elements(case when jsonb_typeof(p->'scenes')='array' then p->'scenes' else '[]'::jsonb end) with ordinality a(s,n)), '[]'::jsonb))
$$;
revoke all on function public.std_compact_generated_structure(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.std_compact_generated_structure(jsonb,jsonb) to service_role;
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
 'generated_structure',public.std_compact_generated_structure(coalesce(nullif(t.pregenerated_structure::jsonb,'null'::jsonb),p.project_payload::jsonb->'structure',p.source_payload::jsonb->'pregenerated_structure'),jsonb_build_object('main',coalesce(nullif(p.project_payload::jsonb#>'{structure,main_character}','null'::jsonb),nullif(p.project_payload::jsonb->'main_character','null'::jsonb),'{}'::jsonb),'supporting',coalesce(nullif(p.project_payload::jsonb#>'{structure,supporting_characters}','null'::jsonb),nullif(p.project_payload::jsonb->'supporting_characters','null'::jsonb),'[]'::jsonb),'scene_cast',coalesce(nullif(p.project_payload::jsonb#>'{structure,scene_cast}','null'::jsonb),'[]'::jsonb)))
 )), '[]'::jsonb)
 from public.std_projects p left join public.topics_queue t on t.id=coalesce(p.topic_queue_id::text,p.source_payload::jsonb->>'topic_queue_id',p.project_payload::jsonb->>'topic_queue_id')::bigint
 where p.id=any(p_project_ids)
$$;
