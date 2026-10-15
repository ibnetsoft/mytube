-- Match the source snapshot emitted by current web/script workers.
do $migration$
declare
 definition text;
 marker text := '''image_generation_policy'', case';
begin
 definition := pg_get_functiondef('public.air_patch_topic_scene_assets(text,jsonb)'::regprocedure);
 if position('''scene_direction_plan'', case' in definition) = 0 then
   if position(marker in definition) = 0 then
     raise exception 'Unexpected scene asset source snapshot; refusing to replace the function';
   end if;
   definition := replace(definition, marker,
     '''scene_direction_plan'', case when pg_catalog.jsonb_typeof(v_scene -> ''scene_direction_plan'') = ''object'' then v_scene -> ''scene_direction_plan'' else ''{}''::jsonb end, ' || marker);
   execute definition;
 end if;
end
$migration$;
