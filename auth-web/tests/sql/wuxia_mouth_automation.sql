-- Bounded integration fixture. Rollback preserves all production projects/media.
begin;
set local statement_timeout='8s';
do $$
declare p uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); a2 uuid:=gen_random_uuid(); token uuid:=gen_random_uuid(); j jsonb; answer jsonb; job uuid; n int;
 pkg jsonb:='{"contract":"wuxia_still_ae_episode/v1","scenes":[{"scene_id":"E01_S01","graphics":[],"states":[{"asset_id":"S1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","dialogue_mouths":[{"id":"manual"}]}]}]}'::jsonb;
 result jsonb:='{"states":[{"scene_id":"E01_S01","asset_id":"S1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","art":[]}],"report":{"state":"not_required","selection_complete":true,"eligible_count":0}}';
begin
 insert into public.std_projects(id,employee_email,title,project_payload) values(p,'worker-mouth-fixture@example.invalid','ROLLBACK selective mouth automation',
  jsonb_build_object('structure',jsonb_build_object('wuxia_ae_package',pkg,'wuxia_mouth_policy',jsonb_build_object('enabled',true,'auto_prepare',true))));
 select count(*) into n from public.std_project_assets where project_id=p;
 if n<>1 then raise exception 'Insert did not atomically enqueue art';end if;
 perform public.request_std_wuxia_mouth(p,'art');
 select count(*) into n from public.std_project_assets where project_id=p;
 if n<>1 then raise exception 'Duplicate enqueue';end if;
 j:=public.claim_std_wuxia_mouth(token);
 if j->>'project_id'<>p::text or j#>>'{metadata,input,task}'<>'art' then raise exception 'Art claim failed';end if;
 job:=(j->>'id')::uuid;
 if public.claim_std_wuxia_mouth(gen_random_uuid()) is not null then raise exception 'Project claimed twice';end if;
 answer:=public.finish_std_wuxia_mouth(job,token,result);
 if answer->>'applied'<>'true' or answer->>'state'<>'not_required' then raise exception 'Zero not normal';end if;
 if (select project_payload#>>'{structure,wuxia_ae_package,scenes,0,states,0,dialogue_mouths,0,id}' from public.std_projects where id=p)<>'manual' then raise exception 'Manual mouth was overwritten';end if;
 if public.request_std_wuxia_mouth(p,'timing')->>'state'<>'waiting_audio' then raise exception 'Audio wait failed';end if;
 insert into public.std_project_assets(id,project_id,asset_type,status,file_name,metadata) values(a,p,'audio','uploaded','voice.wav',jsonb_build_object('sha256',repeat('b',64),'subtitle_timeline','[]'::jsonb));
 update public.std_projects set project_payload=project_payload||jsonb_build_object('subtitle_source_audio_id',a,'subtitles','[]'::jsonb) where id=p;
 j:=public.claim_std_wuxia_mouth(token);
 if j#>>'{metadata,input,task}'<>'timing' then raise exception 'Voice save did not enqueue timing';end if;
 answer:=public.finish_std_wuxia_mouth((j->>'id')::uuid,token,result||jsonb_build_object('states',jsonb_build_array((result->'states'->0)||'{"mouths":[]}'::jsonb)));
 if answer->>'state'<>'not_required' or answer->>'applied'<>'true' then raise exception 'Final-voice zero-cut completion failed';end if;
 if (select project_payload#>>'{structure,wuxia_ae_package,scenes,0,states,0,dialogue_mouths,0,id}' from public.std_projects where id=p)<>'manual' then raise exception 'Timing overwrote manual art';end if;
 insert into public.std_project_assets(id,project_id,asset_type,status,file_name,metadata) values(a2,p,'audio','uploaded','voice2.wav',jsonb_build_object('sha256',repeat('c',64),'subtitle_timeline','[]'::jsonb));
 update public.std_projects set project_payload=project_payload||jsonb_build_object('subtitle_source_audio_id',a2) where id=p;
 j:=public.claim_std_wuxia_mouth(token);
 if j#>>'{metadata,input,recording,id}'<>a2::text then raise exception 'Replacement voice not queued';end if;
 -- Replacing actual selected audio invalidates a running job, without applying its result.
 update public.std_projects set project_payload=project_payload-'subtitle_source_audio_id' where id=p;
 answer:=public.finish_std_wuxia_mouth((j->>'id')::uuid,token,result||jsonb_build_object('states',jsonb_build_array((result->'states'->0)||'{"mouths":[]}'::jsonb)));
 if answer->>'applied'<>'false' or answer->>'reason'<>'source_changed' then raise exception 'Stale voice applied';end if;
 -- Closing ownership prevents new work.
 update public.std_projects set submitted_at=now() where id=p;
 if public.request_std_wuxia_mouth(p,'art')->>'state'<>'closed' then raise exception 'Submitted project accepted preparation';end if;
 begin
  perform public.apply_wuxia_mouth_result(pkg,'{"states":[],"report":{"state":"not_required","selection_complete":true}}',false);
  raise exception 'Incomplete selection was accepted';
 exception when others then
  if SQLERRM<>'Incomplete mouth selection' then raise;end if;
 end;
 -- Service role only, never callable with an anonymous/user token.
 if has_function_privilege('anon','public.request_std_wuxia_mouth(uuid,text)','execute') or has_function_privilege('authenticated','public.claim_std_wuxia_mouth(uuid)','execute') then raise exception 'Unsafe function grant';end if;
end $$;
rollback;
