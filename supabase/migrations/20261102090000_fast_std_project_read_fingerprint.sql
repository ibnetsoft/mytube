-- Fingerprint row versions instead of serializing and hashing entire project payloads.
-- xmin changes on every committed row update, including updates that do not touch
-- updated_at. Include IDs so inserts and deletes also invalidate cached responses.
create or replace function public.std_project_read_fingerprint(p_project_id text)
returns jsonb
language sql stable security invoker
set search_path = ''
as $$
  select jsonb_build_object(
    'employee_email', p.employee_email,
    'version', md5(
      'row-versions-v1|' || p.id::text || ':' || p.xmin::text || '|' ||
      coalesce((select string_agg(s.id::text || ':' || s.xmin::text, ',' order by s.id)
        from public.std_project_scenes s where s.project_id = p.id), '') || '|' ||
      coalesce((select string_agg(a.id::text || ':' || a.xmin::text, ',' order by a.id)
        from public.std_project_assets a where a.project_id = p.id), '') || '|' ||
      coalesce((select string_agg(t.id::text || ':' || t.xmin::text, ',' order by t.id)
        from public.topics_queue t where t.id::text = coalesce(
          p.topic_queue_id::text, p.source_payload::jsonb ->> 'topic_queue_id',
          p.project_payload::jsonb ->> 'topic_queue_id', p.source_payload::jsonb ->> 'id',
          p.project_payload::jsonb ->> 'topic_id')), '') || '|' ||
      coalesce((select string_agg(r.id::text || ':' || r.xmin::text, ',' order by r.id)
        from public.remote_render_queue r
        where r.metadata @> jsonb_build_object('std_web_project_id', p.id::text)), '')
    )
  )
  from public.std_projects p
  where p.id = case
    when p_project_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      then p_project_id::uuid
    else null::uuid
  end;
$$;

revoke all on function public.std_project_read_fingerprint(text) from public, anon, authenticated;
grant execute on function public.std_project_read_fingerprint(text) to service_role;
