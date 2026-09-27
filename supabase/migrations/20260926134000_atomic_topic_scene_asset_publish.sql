-- Merge approved CoWork scene assets under the same topic row lock used by
-- air_update_ae_scene. Never replace a stale pregenerated_structure snapshot.
create or replace function public.air_patch_topic_scene_assets(
    p_topic_id text,
    p_scene_updates jsonb
) returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_structure jsonb;
    v_scenes jsonb;
    v_item jsonb;
    v_scene jsonb;
    v_meta jsonb;
    v_patch jsonb;
    v_patch_meta jsonb;
    v_source jsonb;
    v_current_assets jsonb;
    v_next_scene jsonb;
    v_number text;
    v_seen text[] := array[]::text[];
    v_index integer;
    v_match_count integer;
    v_changed integer := 0;
begin
    if current_user <> 'service_role' then
        raise insufficient_privilege using message = 'service_role required';
    end if;
    if p_topic_id is null or p_topic_id !~ '^[0-9]{1,20}$' or
       pg_catalog.jsonb_typeof(p_scene_updates) is distinct from 'array' then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
    end if;
    if pg_catalog.jsonb_array_length(p_scene_updates) < 1 or
       pg_catalog.jsonb_array_length(p_scene_updates) > 1000 or
       pg_catalog.length(p_scene_updates::text) > 5000000 then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
    end if;

    select pregenerated_structure into v_structure
      from public.topics_queue where id::text = p_topic_id for update;
    if not found then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'topic_not_found');
    end if;
    if pg_catalog.jsonb_typeof(v_structure) is distinct from 'object' or
       pg_catalog.jsonb_typeof(v_structure -> 'scenes') is distinct from 'array' then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_topic_structure');
    end if;
    v_scenes := v_structure -> 'scenes';

    -- All checks and changes are staged in memory. One conflict aborts the
    -- whole batch; the row is written only after every scene passes.
    for v_item in select value from pg_catalog.jsonb_array_elements(p_scene_updates)
    loop
        if pg_catalog.jsonb_typeof(v_item) is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
        end if;
        if (v_item - 'scene_number' - 'expected_source' - 'expected_assets' - 'asset_patch') <> '{}'::jsonb then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
        end if;
        v_number := v_item ->> 'scene_number';
        if v_number is null or v_number !~ '^[1-9][0-9]{0,7}$' or
           v_number = any(v_seen) or
           pg_catalog.jsonb_typeof(v_item -> 'expected_source') is distinct from 'object' or
           pg_catalog.jsonb_typeof(v_item -> 'expected_assets') is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
        end if;
        v_seen := pg_catalog.array_append(v_seen, v_number);
        v_patch := v_item -> 'asset_patch';
        if pg_catalog.jsonb_typeof(v_patch) is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_asset_patch');
        end if;
        if (v_patch - 'image_url' - 'asset_status' - 'local_layer_status' -
             'psd_layer_status' - 'metadata') <> '{}'::jsonb or
           pg_catalog.jsonb_typeof(v_patch -> 'image_url') is distinct from 'string' or
           coalesce(v_patch ->> 'image_url', '') = '' or
           v_patch ->> 'asset_status' is distinct from 'ready' or
           pg_catalog.jsonb_typeof(v_patch -> 'metadata') is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_asset_patch');
        end if;
        v_patch_meta := v_patch -> 'metadata';
        if pg_catalog.jsonb_typeof(v_patch_meta) is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_asset_patch');
        end if;
        if (v_patch_meta - 'cowork_image_asset' - 'local_layer_plan' -
            'local_layer_asset' - 'psd_layer_asset' - 'psd_layer_plan') <> '{}'::jsonb or
           pg_catalog.jsonb_typeof(v_patch_meta -> 'cowork_image_asset') is distinct from 'object' or
           v_patch_meta #>> '{cowork_image_asset,source}' is distinct from 'cowork_builtin_imagegen' or
           (v_patch ? 'local_layer_status' and
            (v_patch ->> 'local_layer_status' is distinct from 'ready' or
             pg_catalog.jsonb_typeof(v_patch_meta -> 'local_layer_asset') is distinct from 'object')) or
           (v_patch ? 'psd_layer_status' and
            (v_patch ->> 'psd_layer_status' is distinct from 'ready' or
             pg_catalog.jsonb_typeof(v_patch_meta -> 'psd_layer_asset') is distinct from 'object' or
             v_patch_meta #>> '{psd_layer_asset,qa_status}' is distinct from 'approved' or
             v_patch_meta #>> '{psd_layer_asset,source}' is distinct from 'independently_authored_png_layers' or
             coalesce(v_patch_meta #>> '{psd_layer_asset,gcs_path}', '') !~* '\.psd$' or
             coalesce(v_patch_meta #>> '{psd_layer_asset,sha256}', '') !~ '^[0-9a-f]{64}$')) then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_asset_patch');
        end if;

        select count(*), min(ordinality)::integer - 1 into v_match_count, v_index
          from pg_catalog.jsonb_array_elements(v_scenes)
               with ordinality as item(scene, ordinality)
         where coalesce(nullif(scene ->> 'scene_number', ''),
                        nullif(scene ->> 'scene_order', ''), ordinality::text) = v_number;
        if v_match_count <> 1 then
            return pg_catalog.jsonb_build_object('applied', false,
                'code', case when v_match_count = 0 then 'scene_not_found' else 'duplicate_scene_number' end,
                'scene_number', v_number);
        end if;
        v_scene := v_scenes -> v_index;
        if pg_catalog.jsonb_typeof(v_scene) is distinct from 'object' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_scene');
        end if;
        v_source := pg_catalog.jsonb_build_object(
            'scene_number', v_number::integer,
            'scene_text', coalesce(nullif(v_scene ->> 'scene_text', ''), v_scene ->> 'narration'),
            'image_prompt', v_scene -> 'image_prompt',
            'image_style', v_scene -> 'image_style',
            'ae_effect_plan', case when pg_catalog.jsonb_typeof(v_scene -> 'ae_effect_plan') = 'object'
                then v_scene -> 'ae_effect_plan' else '{}'::jsonb end,
            'image_generation_policy', case when pg_catalog.jsonb_typeof(v_scene -> 'image_generation_policy') = 'object'
                then v_scene -> 'image_generation_policy' else '{}'::jsonb end,
            'local_layer_plan', case when pg_catalog.jsonb_typeof(v_scene -> 'local_layer_plan') = 'object'
                then v_scene -> 'local_layer_plan' else '{}'::jsonb end,
            'psd_layer_plan', case when pg_catalog.jsonb_typeof(v_scene -> 'psd_layer_plan') = 'object'
                then v_scene -> 'psd_layer_plan' else '{}'::jsonb end
        );
        if v_source is distinct from v_item -> 'expected_source' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'source_conflict',
                                                 'scene_number', v_number);
        end if;
        v_meta := v_scene -> 'metadata';
        if pg_catalog.jsonb_typeof(v_meta) is distinct from 'object' then
            v_meta := '{}'::jsonb;
        end if;
        v_current_assets := pg_catalog.jsonb_build_object(
            'image_url', v_scene -> 'image_url',
            'asset_status', v_scene -> 'asset_status',
            'local_layer_status', v_scene -> 'local_layer_status',
            'psd_layer_status', v_scene -> 'psd_layer_status',
            'metadata', pg_catalog.jsonb_build_object(
                'cowork_image_asset', v_meta -> 'cowork_image_asset',
                'local_layer_plan', v_meta -> 'local_layer_plan',
                'local_layer_asset', v_meta -> 'local_layer_asset',
                'psd_layer_asset', v_meta -> 'psd_layer_asset',
                'psd_layer_plan', v_meta -> 'psd_layer_plan'
            )
        );
        if v_current_assets is distinct from v_item -> 'expected_assets' then
            return pg_catalog.jsonb_build_object('applied', false, 'code', 'asset_conflict',
                                                 'scene_number', v_number);
        end if;

        v_next_scene := v_scene || (v_patch - 'metadata');
        v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{metadata}', v_meta || v_patch_meta, true);
        if v_next_scene is distinct from v_scene then
            v_scenes := pg_catalog.jsonb_set(v_scenes, array[v_index::text], v_next_scene, false);
            v_changed := v_changed + 1;
        end if;
    end loop;

    if v_changed > 0 then
        v_structure := pg_catalog.jsonb_set(v_structure, '{scenes}', v_scenes, false);
        update public.topics_queue set pregenerated_structure = v_structure
         where id::text = p_topic_id;
    end if;
    return pg_catalog.jsonb_build_object('applied', true, 'scenes_updated', v_changed);
end;
$$;

revoke all on function public.air_patch_topic_scene_assets(text, jsonb)
    from public, anon, authenticated;
grant execute on function public.air_patch_topic_scene_assets(text, jsonb)
    to service_role;
