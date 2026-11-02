do $$
declare input jsonb := '{"scene_direction_plans":[{"x":1}],"scenes":[{"scene_number":1,"scene_text":"text","image_prompt":"prompt","image_url":"url","ae_motion_plan":{"x":2},"metadata":{"image_url":"url"}}]}'::jsonb; web jsonb; source jsonb;
begin
 web:=public.std_web_structure(input);
 assert web#>>'{scenes,0,scene_text}'='text';
 assert web#>>'{scenes,0,image_prompt}'='prompt';
 assert not(web ? 'scene_direction_plans');
 assert not(web#>'{scenes,0}' ? 'ae_motion_plan');
 source:=public.std_web_source_structure(input);
 assert source#>>'{scenes,0,image_url}'='url';
 assert source#>>'{scenes,0,metadata,image_url}'='url';
 assert not(source#>'{scenes,0}' ? 'image_prompt');
 assert not has_function_privilege('anon','public.std_user_web_project(uuid)','execute');
 assert has_function_privilege('service_role','public.std_user_web_project(uuid)','execute');
end $$;
