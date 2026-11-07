-- Old workers must not silently pass through a frozen native webtoon timeline.
-- No project-payload expansion: the submission carries its small required contract.
create or replace function public.guard_wuxia_native_worker_claim()
returns trigger language plpgsql security invoker set search_path=public as $$
declare required text;
begin
 if new.metadata->>'kind' is distinct from 'motion_automation' then return new; end if;
 required:=coalesce(new.metadata->'input'->>'required_worker_contract',new.metadata->>'required_worker_contract');
 if required is null then return new; end if;
 if new.metadata->>'state' in ('processing','complete') and (
  new.metadata->'worker_contract_ack'->>'contract' is distinct from required
  or nullif(new.metadata->>'worker_token','') is null
  or new.metadata->'worker_contract_ack'->>'lease_token' is distinct from new.metadata->>'worker_token'
 ) then raise exception 'Native wuxia worker update required: %',required; end if;
 return new;
end $$;
revoke all on function public.guard_wuxia_native_worker_claim() from public,anon,authenticated;
create trigger guard_wuxia_native_worker_claim
before insert or update of metadata on public.std_project_assets
for each row execute function public.guard_wuxia_native_worker_claim();
