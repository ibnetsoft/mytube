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
        ('angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
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
        if v_template in ('angled_triple_reaction', 'body_following_qi', 'ink_splat_impact',
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
