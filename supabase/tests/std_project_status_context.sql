-- Read-only projection contract checks. Run after optimize_std_project_reads.
do $$
declare
 fixture jsonb := '{"script":"saved","prompt":"private prompt","structure":{"main_character":{"name":"A","optional":null},"supporting_characters":[],"scene_cast":[{"name":"A","detail":null}],"scenes":[{"scene_number":19,"scene_text":"line","image_url":"image","image_prompt":"private","metadata":{"large_receipt":"omit"}}]},"subtitles":[{"scene_number":19,"text":"line","dialogue_override":true,"dialogue_speaker":"A","audio_data":"omit"}],"render_settings":{"comic":{"enabled":true},"large_overlay":"omit"}}'::jsonb;
 compact jsonb;
begin
 compact := public.std_compact_project_payload(fixture);
 assert compact->>'script'='saved';
 assert compact#>'{structure,main_character}'=fixture#>'{structure,main_character}';
 assert compact#>'{structure,scene_cast}'=fixture#>'{structure,scene_cast}';
 assert compact#>>'{structure,scenes,0,scene_text}'='line';
 assert compact#>'{subtitles,0,dialogue_override}'='true'::jsonb;
 assert not(compact ? 'prompt');
 assert not(compact#>'{structure,scenes,0}' ? 'metadata');
 assert not(compact#>'{structure,scenes,0}' ? 'image_prompt');
 assert not(compact#>'{subtitles,0}' ? 'audio_data');
 assert not(compact->'render_settings' ? 'large_overlay');
 assert public.std_project_status_context('{}'::uuid[])='[]'::jsonb;
 assert not has_function_privilege('anon','public.std_project_status_context(uuid[])','EXECUTE');
 assert not has_function_privilege('authenticated','public.std_project_status_context(uuid[])','EXECUTE');
 assert has_function_privilege('service_role','public.std_project_status_context(uuid[])','EXECUTE');
end $$;
