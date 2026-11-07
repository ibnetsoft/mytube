-- Qualify the table alias separately from the project row variable.
create or replace function public.claim_std_wuxia_mouth(p_token uuid)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare j public.std_project_assets; p public.std_projects;
begin
 for j in select a.* from public.std_project_assets a join public.std_projects project_row on project_row.id=a.project_id
 where a.metadata->>'kind'='wuxia_mouth_preparation' and project_row.submitted_at is null and project_row.status not in ('approved','canceled','cancelled','completed','paid')
 and ((a.metadata->>'state'='queued' and coalesce((a.metadata->>'retry_after')::timestamptz,'-infinity'::timestamptz)<=now())
 or (a.metadata->>'state'='processing' and a.updated_at<now()-interval '3 minutes'))
 order by a.created_at limit 100 for update of a skip locked loop
  if not pg_try_advisory_xact_lock(hashtextextended(j.project_id::text,71)) then continue;end if;
  if exists(select 1 from public.std_project_assets a where a.project_id=j.project_id and a.id<>j.id
   and a.metadata->>'kind'='wuxia_mouth_preparation' and a.metadata->>'state'='processing' and a.updated_at>=now()-interval '3 minutes') then continue;end if;
  select * into p from public.std_projects where id=j.project_id;
  if coalesce(p.project_payload#>>'{structure,wuxia_mouth_policy,auto_prepare}','false')<>'true' or coalesce(p.project_payload#>>'{structure,wuxia_mouth_policy,enabled}','true')='false' then
   update public.std_project_assets set metadata=metadata||'{"state":"canceled"}'::jsonb,updated_at=now() where id=j.id;continue;
  end if;
  update public.std_project_assets set metadata=metadata||jsonb_build_object('state','processing','worker_token',p_token,'error',null,'heartbeat_at',now()),updated_at=now() where id=j.id returning * into j;
  return to_jsonb(j);
 end loop;
 return null;
end $$;
