-- Copy a newly approved topic PSD into already claimed projects without
-- replacing a user's scene edits or an AE worker's concurrent state change.
-- The project row lock serializes with air_update_ae_scene.
create or replace function public.air_sync_manga_layer_assets(p_topic_id text)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_topic jsonb;
    v_topic_scenes jsonb;
    v_project record;
    v_project_scenes jsonb;
    v_claim_scenes jsonb;
    v_topic_scene jsonb;
    v_project_scene jsonb;
    v_claim_scene jsonb;
    v_topic_meta jsonb;
    v_project_meta jsonb;
    v_claim_meta jsonb;
    v_psd jsonb;
    v_ae_asset jsonb;
    v_next_meta jsonb;
    v_next_scene jsonb;
    v_scene_number text;
    v_topic_index integer;
    v_project_index integer;
    v_claim_index integer;
    v_project_matches integer;
    v_claim_matches integer;
    v_project_match_count integer;
    v_projects_updated integer := 0;
    v_scene_updates integer := 0;
    v_requeued integer := 0;
    v_recoverable boolean;
    v_error text;
begin
    if current_user <> 'service_role' then
        raise insufficient_privilege using message = 'service_role required';
    end if;
    if p_topic_id is null or p_topic_id !~ '^[0-9]{1,20}$' then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_topic_id');
    end if;
    select pregenerated_structure into v_topic
      from public.topics_queue where id::text = p_topic_id for update;
    if not found then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'topic_not_found');
    end if;
    v_topic_scenes := v_topic -> 'scenes';
    if pg_catalog.jsonb_typeof(v_topic_scenes) is distinct from 'array' then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_topic_structure');
    end if;

    for v_project in
        select id, status, submitted_at, project_payload, source_payload
          from public.std_projects
         where topic_queue_id::text = p_topic_id
           and status in ('claimed', 'in_progress', 'review_requested')
         order by id for update
    loop
        -- The claim-time topic copy provides a stable baseline for detecting
        -- edits. A changed script or missing baseline is never auto-synced.
        if coalesce(pg_catalog.btrim(v_project.project_payload ->> 'script'), '') = '' or
           pg_catalog.btrim(v_project.project_payload ->> 'script') is distinct from
               pg_catalog.btrim(v_project.source_payload ->> 'pregenerated_script') then
            continue;
        end if;
        v_project_scenes := v_project.project_payload #> '{structure,scenes}';
        v_claim_scenes := v_project.source_payload #> '{pregenerated_structure,scenes}';
        if pg_catalog.jsonb_typeof(v_project_scenes) is distinct from 'array' or
           pg_catalog.jsonb_typeof(v_claim_scenes) is distinct from 'array' then
            continue;
        end if;
        v_project_matches := 0;
        for v_topic_index in 0..pg_catalog.jsonb_array_length(v_topic_scenes) - 1 loop
            v_topic_scene := v_topic_scenes -> v_topic_index;
            v_scene_number := coalesce(
                nullif(v_topic_scene ->> 'scene_number', ''),
                nullif(v_topic_scene ->> 'scene_order', ''),
                (v_topic_index + 1)::text
            );
            if v_scene_number !~ '^[0-9]{1,8}$' or
               v_topic_scene #>> '{ae_effect_plan,enabled}' is distinct from 'true' or
               coalesce(v_topic_scene #>> '{ae_effect_plan,template}', '') not in
                   ('angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
                    'wall_impact_debris', 'glasses_reflection', 'kinetic_title_reveal',
                    'backlit_hand_reveal') then
                continue;
            end if;
            v_topic_meta := coalesce(v_topic_scene -> 'metadata', '{}'::jsonb);
            if pg_catalog.jsonb_typeof(v_topic_meta) is distinct from 'object' then
                continue;
            end if;
            v_psd := v_topic_meta -> 'psd_layer_asset';
            if pg_catalog.jsonb_typeof(v_psd) is distinct from 'object' or
               v_psd ->> 'qa_status' is distinct from 'approved' or
               v_psd ->> 'source' is distinct from 'independently_authored_png_layers' or
               coalesce(v_psd ->> 'gcs_path', '') !~* '\.psd$' or
               coalesce(v_psd ->> 'sha256', '') !~ '^[0-9a-f]{64}$' or
               pg_catalog.jsonb_typeof(v_psd -> 'layers') is distinct from 'array' then
                continue;
            end if;
            if coalesce(v_topic_scene ->> 'image_url', '') = '' then
                continue;
            end if;
            select count(*), min(ordinality)::integer - 1
              into v_project_match_count, v_project_index
              from pg_catalog.jsonb_array_elements(v_project_scenes)
                   with ordinality as item(scene, ordinality)
             where coalesce(
                 nullif(scene ->> 'scene_number', ''),
                 nullif(scene ->> 'scene_order', ''), ordinality::text
             ) = v_scene_number;
            select count(*), min(ordinality)::integer - 1
              into v_claim_matches, v_claim_index
              from pg_catalog.jsonb_array_elements(v_claim_scenes)
                   with ordinality as item(scene, ordinality)
             where coalesce(
                 nullif(scene ->> 'scene_number', ''),
                 nullif(scene ->> 'scene_order', ''), ordinality::text
             ) = v_scene_number;
            if v_project_match_count <> 1 or v_claim_matches <> 1 then
                continue;
            end if;
            -- A user-uploaded scene image/video takes precedence over a later
            -- topic asset even when the copied structure still looks untouched.
            if exists (
                select 1 from public.std_project_assets asset
                 where asset.project_id = v_project.id
                   and asset.scene_number = v_scene_number::integer
                   and asset.asset_type in ('image', 'video')
                   and asset.status in ('uploaded', 'assigned')
            ) then
                continue;
            end if;
            v_project_scene := v_project_scenes -> v_project_index;
            v_claim_scene := v_claim_scenes -> v_claim_index;
            if v_project_scene -> 'ae_effect_plan' is distinct from v_claim_scene -> 'ae_effect_plan' or
               v_claim_scene -> 'ae_effect_plan' is distinct from v_topic_scene -> 'ae_effect_plan' or
               (v_project_scene ->> 'image_url' is distinct from v_claim_scene ->> 'image_url' and
                v_project_scene ->> 'image_url' is distinct from v_topic_scene ->> 'image_url') then
                continue;
            end if;
            v_project_meta := coalesce(v_project_scene -> 'metadata', '{}'::jsonb);
            v_claim_meta := coalesce(v_claim_scene -> 'metadata', '{}'::jsonb);
            if pg_catalog.jsonb_typeof(v_project_meta) is distinct from 'object' or
               pg_catalog.jsonb_typeof(v_claim_meta) is distinct from 'object' then
                continue;
            end if;
            v_ae_asset := v_project_meta -> 'ae_effect_asset';
            v_error := coalesce(v_ae_asset ->> 'error', '');
            v_recoverable := coalesce(v_ae_asset ->> 'status', '') = 'needs_attention' and
                (v_error like 'Manga template needs a layered PSD%' or
                 v_error like 'Manga PSD layer package has not passed layer review%' or
                 v_error like 'Manga template requires a layered PSD source asset%') and
                coalesce(v_ae_asset #>> '{visual_review,decision}', '') <> 'rejected' and
                coalesce(v_ae_asset ->> 'render_sha256', '') = '';
            if v_ae_asset is not null and v_ae_asset <> '{}'::jsonb and not v_recoverable then
                continue;
            end if;
            if (v_project_scene ->> 'asset_status' is distinct from v_claim_scene ->> 'asset_status' and
                v_project_scene ->> 'asset_status' is distinct from v_topic_scene ->> 'asset_status' and
                not v_recoverable) or
               (v_project_scene ->> 'local_layer_status' is distinct from v_claim_scene ->> 'local_layer_status' and
                v_project_scene ->> 'local_layer_status' is distinct from v_topic_scene ->> 'local_layer_status') or
               (v_project_scene ->> 'psd_layer_status' is distinct from v_claim_scene ->> 'psd_layer_status' and
                v_project_scene ->> 'psd_layer_status' is distinct from v_topic_scene ->> 'psd_layer_status') then
                continue;
            end if;
            if (v_project_meta -> 'cowork_image_asset' is distinct from v_claim_meta -> 'cowork_image_asset' and
                v_project_meta -> 'cowork_image_asset' is distinct from v_topic_meta -> 'cowork_image_asset' and
                v_project_meta #>> '{cowork_image_asset,source}' is distinct from 'cowork_builtin_imagegen') or
               (v_project_meta -> 'local_layer_asset' is distinct from v_claim_meta -> 'local_layer_asset' and
                v_project_meta -> 'local_layer_asset' is distinct from v_topic_meta -> 'local_layer_asset' and
                v_project_meta #>> '{local_layer_asset,source}' is distinct from 'local_depth_proxy_from_single_scene_image') or
               (v_project_meta -> 'psd_layer_asset' is distinct from v_claim_meta -> 'psd_layer_asset' and
                v_project_meta -> 'psd_layer_asset' is distinct from v_topic_meta -> 'psd_layer_asset' and
                v_project_meta #>> '{psd_layer_asset,source}' is distinct from 'independently_authored_png_layers') then
                continue;
            end if;

            v_next_meta := v_project_meta || pg_catalog.jsonb_build_object('psd_layer_asset', v_psd);
            if pg_catalog.jsonb_typeof(v_topic_meta -> 'cowork_image_asset') = 'object' then
                v_next_meta := v_next_meta || pg_catalog.jsonb_build_object(
                    'cowork_image_asset', v_topic_meta -> 'cowork_image_asset');
            end if;
            if pg_catalog.jsonb_typeof(v_topic_meta -> 'local_layer_asset') = 'object' then
                v_next_meta := v_next_meta || pg_catalog.jsonb_build_object(
                    'local_layer_asset', v_topic_meta -> 'local_layer_asset');
            end if;
            if v_recoverable then
                v_next_meta := v_next_meta || pg_catalog.jsonb_build_object(
                    'ae_effect_asset', (v_ae_asset - 'error' - 'started_at') ||
                        pg_catalog.jsonb_build_object('status', 'planned', 'attempts', 0, 'next_retry_at', 0));
            end if;
            v_next_scene := pg_catalog.jsonb_set(v_project_scene, '{metadata}', v_next_meta, true);
            v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{image_url}',
                pg_catalog.to_jsonb(v_topic_scene ->> 'image_url'), true);
            v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{psd_layer_status}', '"ready"'::jsonb, true);
            v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{asset_status}', '"ready"'::jsonb, true);
            if v_topic_scene ? 'local_layer_status' then
                v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{local_layer_status}',
                    v_topic_scene -> 'local_layer_status', true);
            end if;
            if v_recoverable then
                v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{ae_effect_status}', '"planned"'::jsonb, true);
            end if;
            if v_next_scene is distinct from v_project_scene then
                v_project_scenes := pg_catalog.jsonb_set(v_project_scenes,
                    array[v_project_index::text], v_next_scene, false);
                v_project_matches := v_project_matches + 1;
                v_scene_updates := v_scene_updates + 1;
                if v_recoverable then
                    v_requeued := v_requeued + 1;
                end if;
            end if;
        end loop;
        if v_project_matches > 0 then
            update public.std_projects
               set project_payload = pg_catalog.jsonb_set(
                       project_payload, '{structure,scenes}', v_project_scenes, false),
                   updated_at = pg_catalog.now()
             where id = v_project.id;
            v_projects_updated := v_projects_updated + 1;
        end if;
    end loop;
    return pg_catalog.jsonb_build_object('applied', true, 'projects_updated', v_projects_updated,
        'scenes_updated', v_scene_updates, 'requeued', v_requeued);
end;
$$;

revoke all on function public.air_sync_manga_layer_assets(text) from public, anon, authenticated;
grant execute on function public.air_sync_manga_layer_assets(text) to service_role;
