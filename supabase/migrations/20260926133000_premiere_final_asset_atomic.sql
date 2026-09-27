-- Keep the final package status independent of concurrent AE scene updates.
-- The Premiere worker sends only its asset record, never a stale project JSON.
create or replace function public.air_update_premiere_final_asset(
    p_project_id text,
    p_asset jsonb,
    p_expected_status text default '',
    p_expected_updated_at text default ''
) returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_payload jsonb;
    v_progress jsonb;
    v_settings jsonb;
    v_current_asset jsonb;
    v_submitted_at timestamptz;
begin
    if current_user <> 'service_role' then
        raise insufficient_privilege using message = 'service_role required';
    end if;
    if p_project_id is null or p_project_id !~ '^[A-Za-z0-9-]{1,80}$' or
       pg_catalog.jsonb_typeof(p_asset) is distinct from 'object' or
       coalesce(p_asset ->> 'status', '') not in
           ('ready', 'package_ready', 'retry_wait', 'needs_attention') or
       pg_catalog.length(p_asset::text) > 100000 then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'invalid_request');
    end if;

    select project_payload, progress_payload, submitted_at
      into v_payload, v_progress, v_submitted_at
      from public.std_projects where id::text = p_project_id for update;
    if not found then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'not_found');
    end if;
    if v_submitted_at is null then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'project_not_submitted');
    end if;
    if pg_catalog.jsonb_typeof(v_payload) is distinct from 'object' then
        v_payload := '{}'::jsonb;
    end if;
    if pg_catalog.jsonb_typeof(v_progress) is distinct from 'object' then
        v_progress := '{}'::jsonb;
    end if;
    v_settings := v_payload -> 'render_settings';
    if pg_catalog.jsonb_typeof(v_settings) is distinct from 'object' then
        v_settings := '{}'::jsonb;
    end if;
    v_current_asset := v_settings -> 'premiere_final_asset';
    if coalesce(v_current_asset ->> 'status', '') is distinct from
           coalesce(p_expected_status, '') or
       coalesce(v_current_asset ->> 'updated_at', '') is distinct from
           coalesce(p_expected_updated_at, '') then
        return pg_catalog.jsonb_build_object('applied', false, 'code', 'asset_conflict');
    end if;

    v_settings := v_settings || pg_catalog.jsonb_build_object('premiere_final_asset', p_asset);
    v_payload := pg_catalog.jsonb_set(v_payload, '{render_settings}', v_settings, true);
    v_progress := v_progress || pg_catalog.jsonb_build_object('premiere_final_asset', p_asset);
    update public.std_projects
       set project_payload = v_payload,
           progress_payload = v_progress,
           updated_at = pg_catalog.now()
     where id::text = p_project_id;
    return pg_catalog.jsonb_build_object('applied', true, 'asset', p_asset);
end;
$$;

revoke all on function public.air_update_premiere_final_asset(text, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.air_update_premiere_final_asset(text, jsonb, text, text)
    to service_role;
