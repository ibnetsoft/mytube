-- Local AE workers poll versions, not complete multi-MB structures.
create or replace function public.std_ae_candidate_manifest(p_source text, p_limit integer default 20)
returns jsonb language sql stable security invoker set search_path='' as $$
 select case p_source
 when 'topic' then (select coalesce(jsonb_agg(row),'[]'::jsonb) from (
   select jsonb_build_object('id',id,'topic',topic,'generated_title',generated_title,
     'pregenerated_structure_status',pregenerated_structure_status,'created_at',created_at,
     'version',md5(pregenerated_structure::text)) as row
   from public.topics_queue where pregenerated_structure_status='ready'
   order by created_at desc limit least(100,greatest(1,p_limit))) q)
 when 'project' then (select coalesce(jsonb_agg(row),'[]'::jsonb) from (
   select jsonb_build_object('id',id,'title',title,'submitted_at',submitted_at,'updated_at',updated_at,
     'version',md5(project_payload::text)) as row
   from public.std_projects where (submitted_at is not null or project_payload::jsonb#>>'{ae_mouth,enabled}'='true')
     and status not in ('approved','canceled') order by updated_at desc
   limit least(100,greatest(1,p_limit))) q)
 else '[]'::jsonb end
$$;
create or replace function public.std_ae_candidate_payloads(p_source text, p_ids text[])
returns jsonb language sql stable security invoker set search_path='' as $$
 select case p_source
 when 'topic' then (select coalesce(jsonb_agg(jsonb_build_object('id',id,'topic',topic,
   'generated_title',generated_title,'pregenerated_structure',pregenerated_structure,
   'pregenerated_structure_status',pregenerated_structure_status,'created_at',created_at,
   'version',md5(pregenerated_structure::text))),'[]'::jsonb)
   from public.topics_queue where id::text=any(p_ids))
 when 'project' then (select coalesce(jsonb_agg(jsonb_build_object('id',id,'title',title,
   'submitted_at',submitted_at,'project_payload',project_payload,'updated_at',updated_at,
   'version',md5(project_payload::text))),'[]'::jsonb)
   from public.std_projects where id::text=any(p_ids))
 else '[]'::jsonb end
$$;
revoke all on function public.std_ae_candidate_manifest(text,integer),public.std_ae_candidate_payloads(text,text[]) from public,anon,authenticated;
grant execute on function public.std_ae_candidate_manifest(text,integer),public.std_ae_candidate_payloads(text,text[]) to service_role;
