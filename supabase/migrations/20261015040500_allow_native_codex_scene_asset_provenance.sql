-- Preserve the current function's row locks, CAS checks and permissions.
do $migration$
declare
  definition text;
  old_guard text := 'v_patch_meta #>> ''{cowork_image_asset,source}'' is distinct from ''cowork_builtin_imagegen''';
  new_guard text := 'coalesce(v_patch_meta #>> ''{cowork_image_asset,source}'', '''') not in (''cowork_builtin_imagegen'', ''codex_builtin_imagegen'')';
begin
  definition := pg_get_functiondef('public.air_patch_topic_scene_assets(text,jsonb)'::regprocedure);
  if position(old_guard in definition) > 0 then
    execute replace(definition, old_guard, new_guard);
  elsif position(new_guard in definition) = 0 then
    raise exception 'Unexpected scene asset source guard; refusing to replace the function';
  end if;
end
$migration$;
