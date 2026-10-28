-- Pure JSON gate tests. No projects, assets or render jobs are created.
do $test$
declare s jsonb:=$snapshot${"submitted_video_postwork":"submitted_video_postwork/v1","scenes":[{"number":1,"source_kind":"video","postwork":{"contract":"submitted_video_postwork/v1","mouth_required":true,"dialogue":[{"speaker":"hero"}]}}]}$snapshot$::jsonb;
 r jsonb:=$results$[{"number":1,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","review":{"passed":true,"render_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","final_voice_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","batches":[{"passed":true,"critical_issues":[],"checks":[{"id":"postwork_narrative_fit","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"source_playback_preserved","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"transition_plan","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"dialogue_mouth_timing","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"tracked_mouth_alignment","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"}]}]},"submitted_video_postwork":{"contract":"submitted_video_postwork/v1","source_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","final_voice_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","playback_rate":1,"mouth_required":true,"mouth_applied":true,"offscreen_speakers":[]}}]$results$::jsonb;
 v jsonb:=$review${"submitted_video_postwork_contract":"submitted_video_postwork/v1","passed":true,"reviewer":"local_codex_cli","final_voice_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","scenes":[{"passed":true,"critical_issues":[],"checks":[{"id":"captions","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"scene_boundary","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"visual_quality","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"postwork_continuity","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"},{"id":"voice_clock_preserved","passed":true,"evidence":"Synthetic SQL gate fixture; no production approval"}]}]}$review$::jsonb;
 rejected boolean;
begin
 perform public.assert_std_submitted_video_postwork_review(s,r,v);
 perform public.assert_std_submitted_video_postwork_review('{}',null,null);
 rejected:=false;
 begin perform public.assert_std_submitted_video_postwork_review(s,r,v||'{"skipped":true}'); exception when raise_exception then rejected:=true; end;
 if not rejected then raise exception 'Review bypass incorrectly accepted'; end if;
 rejected:=false;
 begin perform public.assert_std_submitted_video_postwork_review(s,jsonb_set(r,'{0,submitted_video_postwork,mouth_applied}','false'),v); exception when raise_exception then rejected:=true; end;
 if not rejected then raise exception 'Required mouth fallback incorrectly accepted'; end if;
 rejected:=false;
 begin perform public.assert_std_submitted_video_postwork_review(s,jsonb_set(r,'{0,review,batches}','[]'),v); exception when raise_exception then rejected:=true; end;
 if not rejected then raise exception 'Missing actual frame review incorrectly accepted'; end if;
 rejected:=false;
 begin perform public.assert_std_submitted_video_postwork_review(s,r,jsonb_set(v,'{scenes}','[]')); exception when raise_exception then rejected:=true; end;
 if not rejected then raise exception 'Missing final review incorrectly accepted'; end if;
end $test$;
select 'passed: valid, legacy, review bypass blocked, mouth fallback blocked, missing frames blocked, missing final review blocked' as postwork_gate_test;

