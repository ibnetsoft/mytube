-- Return ownership and a fingerprint without transferring project JSON.
create or replace function public.std_project_read_fingerprint(p_project_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('employee_email',p.employee_email,'version',md5(
 to_jsonb(p)::text || coalesce((select string_agg(md5(to_jsonb(s)::text),',' order by s.id) from public.std_project_scenes s where s.project_id=p.id),'') ||
 coalesce((select string_agg(md5(to_jsonb(a)::text),',' order by a.id) from public.std_project_assets a where a.project_id=p.id),'') ||
 coalesce((select string_agg(md5(to_jsonb(t)::text),',' order by t.id) from public.topics_queue t where t.id::text=coalesce(p.topic_queue_id::text,p.source_payload::jsonb->>'topic_queue_id',p.project_payload::jsonb->>'topic_queue_id',p.source_payload::jsonb->>'id',p.project_payload::jsonb->>'topic_id')),'') ||
 coalesce((select string_agg(md5(to_jsonb(r)::text),',' order by r.id) from public.remote_render_queue r where r.metadata @> jsonb_build_object('std_web_project_id',p.id::text)),'')))
 from public.std_projects p where p.id::text=p_project_id
$$;
revoke all on function public.std_project_read_fingerprint(text) from public,anon,authenticated;
grant execute on function public.std_project_read_fingerprint(text) to service_role;
