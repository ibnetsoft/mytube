-- Extend the reviewed manga template allowlists to explicit dialogue close-ups. Existing service-role-only RPC grants remain unchanged.
-- Patch one AE manga scene under a row lock. A full project_payload or
-- pregenerated_structure PATCH can overwrite another scene rendered while a
-- reviewer was watching the clip.
create or replace function public.air_update_ae_scene(
    p_source_type text,
    p_identity text,
    p_scene_number integer,
    p_operation text,
    p_plan_kind text default 'effect',
    p_expected_status text default null,
    p_expected_started_at text default null,
    p_expected_sha256 text default null,
    p_asset_patch jsonb default '{}'::jsonb,
    p_next_status text default null,
    p_media_url text default null,
    p_clear_media_url boolean default false,
    p_review_decision text default null,
    p_reviewer text default null,
    p_note text default null
) returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_payload jsonb;
    v_structure jsonb;
    v_scenes jsonb;
    v_scene jsonb;
    v_asset jsonb;
    v_next_scene jsonb;
    v_match_count integer;
    v_index integer;
    v_status text;
    v_submitted_at timestamptz;
    v_asset_key text;
    v_status_key text;
    v_video_key text;
    v_plan_key text;
    v_template text;
begin
    -- Data API functions are executable by PUBLIC by default. The grants below
    -- close that path; this check also fails closed if grants drift later.
    if current_user <> 'service_role' then
        raise insufficient_privilege using message = 'service_role required';
    end if;
    if coalesce(p_source_type, '') not in ('project', 'topic') or
       p_identity is null or p_identity !~ '^[A-Za-z0-9-]{1,80}$' or
       p_scene_number is null or p_scene_number < 1 or
       coalesce(p_operation, '') not in ('worker', 'review') or
       coalesce(p_plan_kind, '') not in ('effect', 'motion') then
        return jsonb_build_object('applied', false, 'code', 'invalid_request');
    end if;

    if p_source_type = 'project' then
        select project_payload, submitted_at into v_payload, v_submitted_at
          from public.std_projects where id::text = p_identity for update;
        if not found then
            return jsonb_build_object('applied', false, 'code', 'not_found');
        end if;
        if v_submitted_at is null then
            return jsonb_build_object('applied', false, 'code', 'project_not_submitted');
        end if;
        v_structure := v_payload -> 'structure';
    else
        select pregenerated_structure into v_structure
          from public.topics_queue where id::text = p_identity for update;
        if not found then
            return jsonb_build_object('applied', false, 'code', 'not_found');
        end if;
    end if;
    if jsonb_typeof(v_structure) is distinct from 'object' or
       jsonb_typeof(v_structure -> 'scenes') is distinct from 'array' then
        return jsonb_build_object('applied', false, 'code', 'invalid_structure');
    end if;

    v_scenes := v_structure -> 'scenes';
    select count(*), min(ordinality)::integer - 1 into v_match_count, v_index
      from pg_catalog.jsonb_array_elements(v_scenes) with ordinality as item(scene, ordinality)
      where coalesce(
          nullif(scene ->> 'scene_number', ''),
          nullif(scene ->> 'scene_order', ''), ordinality::text
      ) = p_scene_number::text;
    if v_match_count <> 1 then
        return jsonb_build_object('applied', false,
                                  'code', case when v_match_count = 0 then 'scene_not_found' else 'duplicate_scene_number' end);
    end if;
    v_scene := v_scenes -> v_index;
    if jsonb_typeof(v_scene) is distinct from 'object' then
        return jsonb_build_object('applied', false, 'code', 'invalid_scene');
    end if;
    v_asset_key := case when p_plan_kind = 'effect' then 'ae_effect_asset' else 'ae_motion_asset' end;
    v_status_key := case when p_plan_kind = 'effect' then 'ae_effect_status' else 'ae_motion_status' end;
    v_video_key := case when p_plan_kind = 'effect' then 'ae_video_url' else 'ae_motion_video_url' end;
    v_plan_key := case when p_plan_kind = 'effect' then 'ae_effect_plan' else 'ae_motion_plan' end;
    v_template := coalesce(v_scene #>> '{ae_effect_plan,template}', '');
    if coalesce(v_scene #>> array[v_plan_key, 'enabled'], '') <> 'true' then
        return jsonb_build_object('applied', false, 'code', 'ae_plan_disabled');
    end if;
    if p_operation = 'review' and
       (p_plan_kind <> 'effect' or v_template not in
        ('dialogue_closeup', 'angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
         'wall_impact_debris', 'glasses_reflection', 'kinetic_title_reveal',
         'backlit_hand_reveal')) then
        return jsonb_build_object('applied', false, 'code', 'not_manga_scene');
    end if;
    v_asset := coalesce(v_scene #> array['metadata', v_asset_key], '{}'::jsonb);
    if jsonb_typeof(v_asset) is distinct from 'object' then
        return jsonb_build_object('applied', false, 'code', 'invalid_asset');
    end if;

    if p_operation = 'review' then
        if coalesce(p_review_decision, '') not in ('approved', 'rejected') or
           pg_catalog.length(pg_catalog.btrim(coalesce(p_reviewer, ''))) not between 1 and 120 or
           pg_catalog.length(pg_catalog.btrim(coalesce(p_note, ''))) not between 1 and 1000 or
           p_expected_sha256 is null or p_expected_sha256 !~ '^[0-9a-f]{64}$' then
            return jsonb_build_object('applied', false, 'code', 'invalid_review');
        end if;
        if coalesce(v_asset ->> 'status', '') <> 'review_pending' or
           coalesce(v_asset ->> 'render_sha256', '') <> p_expected_sha256 then
            return jsonb_build_object('applied', false, 'code', 'review_conflict');
        end if;
        if coalesce(v_asset #>> '{manga_qa,plan,passed}', '') <> 'true' or
           coalesce(v_asset #>> '{manga_qa,render,passed}', '') <> 'true' then
            return jsonb_build_object('applied', false, 'code', 'qa_not_passed');
        end if;
        v_status := case when p_review_decision = 'approved' then 'ready' else 'needs_attention' end;
        v_asset := v_asset || jsonb_build_object(
            'status', v_status,
            'visual_review', jsonb_build_object(
                'decision', p_review_decision,
                'reviewer', pg_catalog.btrim(p_reviewer),
                'note', pg_catalog.btrim(p_note),
                'render_sha256', p_expected_sha256,
                'reviewed_at', pg_catalog.clock_timestamp()
            )
        );
        if p_review_decision = 'rejected' then
            v_asset := v_asset || jsonb_build_object(
                'error', 'Visual review rejected: ' || pg_catalog.left(pg_catalog.btrim(p_note), 300)
            );
        end if;
    else
        if coalesce(p_next_status, '') not in ('rendering', 'retry_wait', 'needs_attention', 'review_pending', 'ready') or
           jsonb_typeof(p_asset_patch) is distinct from 'object' or
           p_expected_status is null or
           coalesce(v_asset ->> 'status', '') <> p_expected_status or
           (p_expected_started_at is not null and
            v_asset ->> 'started_at' is distinct from p_expected_started_at) then
            return jsonb_build_object('applied', false, 'code', 'worker_conflict');
        end if;
        if v_template in ('dialogue_closeup', 'angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
                          'wall_impact_debris', 'glasses_reflection', 'kinetic_title_reveal',
                          'backlit_hand_reveal') and
           p_next_status = 'ready' then
            return jsonb_build_object('applied', false, 'code', 'review_required');
        end if;
        -- Metadata for the selected AE asset is merged against the locked row.
        -- Image assets and every other scene remain the database's latest copy.
        v_status := p_next_status;
        if v_status = 'rendering' then
            -- A forced rerender must not inherit an older approval or media
            -- URL. Keep local_path so a verified MP4 can still be resumed.
            v_asset := v_asset - 'visual_review' - 'render_sha256' -
                       'review_local_path' - 'manga_qa' - 'media_url' - 'review_required';
        end if;
        v_asset := v_asset || p_asset_patch || jsonb_build_object('status', v_status);
    end if;

    v_next_scene := pg_catalog.jsonb_set(
        v_scene, '{metadata}',
        (case when jsonb_typeof(v_scene -> 'metadata') = 'object'
              then v_scene -> 'metadata' else '{}'::jsonb end) ||
            jsonb_build_object(v_asset_key, v_asset), true
    );
    v_next_scene := pg_catalog.jsonb_set(v_next_scene, array[v_status_key],
                                          to_jsonb(v_status), true);
    v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{asset_status}',
                                          to_jsonb(v_status), true);
    if p_operation = 'worker' then
        if p_media_url is not null and p_media_url <> '' then
            v_next_scene := pg_catalog.jsonb_set(v_next_scene, array[v_video_key], to_jsonb(p_media_url), true);
            v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{video_url}', to_jsonb(p_media_url), true);
        elsif p_clear_media_url then
            v_next_scene := v_next_scene - v_video_key;
            if v_scene ->> 'video_url' = v_scene #>> array['metadata', v_asset_key, 'media_url'] then
                v_next_scene := v_next_scene - 'video_url';
            end if;
        end if;
    elsif p_review_decision = 'approved' and coalesce(v_asset ->> 'media_url', '') <> '' then
        -- GCS review clips are kept private in the scene until visual approval.
        v_next_scene := pg_catalog.jsonb_set(v_next_scene, array[v_video_key],
                                              to_jsonb(v_asset ->> 'media_url'), true);
        v_next_scene := pg_catalog.jsonb_set(v_next_scene, '{video_url}',
                                              to_jsonb(v_asset ->> 'media_url'), true);
    elsif p_review_decision = 'rejected' then
        v_next_scene := v_next_scene - v_video_key;
        if v_scene ->> 'video_url' = v_asset ->> 'media_url' then
            v_next_scene := v_next_scene - 'video_url';
        end if;
    end if;
    v_structure := pg_catalog.jsonb_set(v_structure, array['scenes', v_index::text], v_next_scene, false);
    if p_source_type = 'project' then
        update public.std_projects
           set project_payload = pg_catalog.jsonb_set(
                   (case when jsonb_typeof(project_payload) = 'object'
                         then project_payload else '{}'::jsonb end),
                   '{structure}', v_structure, true),
               updated_at = pg_catalog.now()
         where id::text = p_identity;
    else
        update public.topics_queue set pregenerated_structure = v_structure
         where id::text = p_identity;
    end if;
    return jsonb_build_object('applied', true, 'status', v_status, 'scene', v_next_scene);
end;
$$;

revoke all on function public.air_update_ae_scene(
    text, text, integer, text, text, text, text, text, jsonb, text, text, boolean, text, text, text
) from public, anon, authenticated;
grant execute on function public.air_update_ae_scene(
    text, text, integer, text, text, text, text, text, jsonb, text, text, boolean, text, text, text
) to service_role;

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
                   ('dialogue_closeup', 'angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
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

