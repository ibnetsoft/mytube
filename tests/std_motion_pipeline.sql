-- Run as service-role-capable test connection. All fixture rows are rolled back.
begin;
do $$
declare pid uuid:=gen_random_uuid(); uid uuid; rid uuid:=gen_random_uuid(); jid uuid:=gen_random_uuid();
 aid uuid:=gen_random_uuid(); stamp timestamptz:=now(); result jsonb; h text:=repeat('a',64); final jsonb; review jsonb;
begin
 select id into uid from profiles limit 1;
 insert into std_projects(id,user_id,employee_email,title,updated_at) values(pid,uid,'motion-qa@test.invalid','ROLLBACK motion contract QA',stamp);
 begin
  perform register_std_motion_pipeline(pid,gen_random_uuid(),stamp,rid,jid,'{}',h);
  raise exception 'ownership guard failed';
 exception when others then if sqlerrm<>'Project ownership mismatch' then raise; end if; end;
 result:=register_std_motion_pipeline(pid,uid,stamp,rid,jid,jsonb_build_object('version',1,'project',jsonb_build_object('id',pid),
  'automation',jsonb_build_object('snapshot_json','{"scenes":[{"number":1}]}','fingerprint',h)),h);
 if result->>'job_id'<>jid::text then raise exception 'job not registered'; end if;
 result:=register_std_motion_pipeline(pid,uid,stamp,gen_random_uuid(),gen_random_uuid(),'{}',h);
 if result->>'already_submitted'<>'true' or result->>'job_id'<>jid::text then raise exception 'idempotence failed'; end if;
 update std_project_assets set metadata=metadata||'{"state":"processing","worker_token":"qa-lease"}' where id=jid;
 result:=patch_std_motion_job(jid,'qa-lease','{"phase":"review"}');
 if result->>'phase'<>'review' or result->'input'->>'snapshot_json'<>'{"scenes":[{"number":1}]}' then raise exception 'patch lost frozen input'; end if;
 begin perform patch_std_motion_job(jid,'bad-token','{}');raise exception 'lease guard failed';
 exception when others then if sqlerrm<>'Motion worker lease lost' then raise; end if; end;
 begin perform patch_std_motion_job(jid,'qa-lease','{"input":{}}');raise exception 'immutable guard failed';
 exception when others then if sqlerrm<>'Frozen job fields cannot change' then raise; end if; end;
 final:=jsonb_build_object('gcs_bucket','fixture-only','gcs_path','std-motion/'||jid||'/final/'||h||'.mp4','sha256',h);
 begin perform complete_std_motion_job(jid,'qa-lease',aid,final,'{}');raise exception 'review guard failed';
 exception when others then if sqlerrm<>'Reviewed output evidence required' then raise; end if; end;
 review:=jsonb_build_object('passed',true,'render_sha256',h,'reviewer','local_codex_cli','scenes','[{"passed":true}]'::jsonb);
 result:=complete_std_motion_job(jid,'qa-lease',aid,final,review);
 if result->>'state'<>'complete' then raise exception 'completion missing'; end if;
 perform complete_std_motion_job(jid,'qa-lease',aid,final,review);
 if (select count(*) from remote_render_queue where id=jid)<>1 then raise exception 'duplicate final render'; end if;
 if (select status from std_projects where id=pid)<>'review_requested' then raise exception 'production approval changed'; end if;
 if (select metadata->>'admin_publish_status' from remote_render_queue where id=jid)<>'pending_review' then raise exception 'admin review missing'; end if;
end $$;
rollback;
