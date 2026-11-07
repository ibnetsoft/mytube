-- A reserved pending topic has an owner but has not been claimed into a project.
-- Bind preparation to that exact owner instead of treating reservation as a claim.
drop function public.publish_wuxia_topic_mouth_art(bigint,jsonb,jsonb);
create function public.publish_wuxia_topic_mouth_art(p_topic_id bigint,p_expected_package jsonb,p_result jsonb,p_expected_owner_email text default null)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare t public.topics_queue; current_source jsonb; expected_source jsonb; pkg jsonb;
begin
 select * into t from public.topics_queue where id=p_topic_id for update;
 if t.id is null or t.status<>'pending' or t.assigned_at is not null
  or coalesce(t.pregenerated_structure#>>'{wuxia_mouth_policy,auto_prepare}','false')<>'true'
  or coalesce(t.pregenerated_structure#>>'{wuxia_mouth_policy,enabled}','true')='false'
 then return jsonb_build_object('applied',false,'reason','disabled'); end if;
 if coalesce(nullif(t.assigned_employee_email,''),'') is distinct from coalesce(nullif(p_expected_owner_email,''),'')
 then return jsonb_build_object('applied',false,'reason','owner_changed'); end if;
 current_source:=public.wuxia_mouth_source(t.pregenerated_structure)->'package';
 expected_source:=public.wuxia_mouth_source(jsonb_build_object('wuxia_ae_package',p_expected_package))->'package';
 if current_source is distinct from expected_source then return jsonb_build_object('applied',false,'reason','source_changed'); end if;
 pkg:=public.apply_wuxia_mouth_result(t.pregenerated_structure->'wuxia_ae_package',p_result,false);
 update public.topics_queue set pregenerated_structure=jsonb_set(pregenerated_structure,'{wuxia_ae_package}',pkg) where id=t.id;
 return jsonb_build_object('applied',true,'state',p_result->'report'->>'state');
end $$;
revoke all on function public.publish_wuxia_topic_mouth_art(bigint,jsonb,jsonb,text) from public,anon,authenticated;
grant execute on function public.publish_wuxia_topic_mouth_art(bigint,jsonb,jsonb,text) to service_role;
