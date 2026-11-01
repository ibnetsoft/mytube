-- Rollback-only regression probe. Never calls a model or changes user content.
begin;
set local role service_role;
do $$
declare
  a text := replace(gen_random_uuid()::text,'-','');
  b text := replace(gen_random_uuid()::text,'-','');
  c text := replace(gen_random_uuid()::text,'-','');
  source text := gen_random_uuid()::text;
  row_a jsonb; row_b jsonb; row_c jsonb; v bigint;
begin
  row_a := jsonb_build_object('id',a,'title','concurrency probe','mode','new','status','queued',
    'worker_id','probe-'||a,'created_at',1,'updated_at',1,'job_record',jsonb_build_object('id',a),
    'request_data','{}'::jsonb,'source_snapshot','{}'::jsonb,'candidate','{}'::jsonb,'reference_sources','[]'::jsonb);
  row_b := row_a || jsonb_build_object('id',b,'worker_id','probe-'||b,'job_record',jsonb_build_object('id',b));
  assert public.save_script_worker_job(row_a,null)=1;
  assert public.save_script_worker_job(row_b,null)=1;
  assert public.save_script_worker_job(row_a,null)=1, 'Lost-response retry must be idempotent';
  row_c := row_a || jsonb_build_object('id',c,'job_record',jsonb_build_object('id',c));
  begin
    perform public.save_script_worker_job(row_c,null);
    raise exception 'Same worker accepted two active scripts';
  exception when unique_violation then null;
  end;
  row_a := row_a || jsonb_build_object('status','running','updated_at',2);
  assert public.save_script_worker_job(row_a,1)=2;
  begin
    perform public.save_script_worker_job(row_a || jsonb_build_object('status','failed'),1);
    raise exception 'Stale revision overwrote current job';
  exception when serialization_failure then null;
  end;
  begin
    perform public.save_script_worker_job(row_a || jsonb_build_object('worker_id','probe-other'),null);
    raise exception 'Another computer overwrote an existing job';
  exception when serialization_failure then null;
  end;
  row_a := row_a || jsonb_build_object('mode','repair','request_data',jsonb_build_object('kind','project','source_id',source));
  assert public.save_script_worker_job(row_a,2)=3;
  begin
    perform public.save_script_worker_job(row_b || jsonb_build_object('mode','repair','request_data',row_a->'request_data'),1);
    raise exception 'Same repair source executed twice';
  exception when unique_violation then null;
  end;
  row_a := row_a || jsonb_build_object('request_data',jsonb_build_object('web_topic_id',source));
  assert public.save_script_worker_job(row_a,3)=4;
  begin
    perform public.save_script_worker_job(row_b || jsonb_build_object('request_data',row_a->'request_data'),1);
    raise exception 'Same submitted topic executed twice';
  exception when unique_violation then null;
  end;
  row_a := row_a || jsonb_build_object('job_record',jsonb_build_object('id',a,'retry_of',source));
  assert public.save_script_worker_job(row_a,4)=5;
  begin
    perform public.save_script_worker_job(row_b || jsonb_build_object('job_record',jsonb_build_object('id',b,'retry_of',source)),1);
    raise exception 'Same failed job retried twice';
  exception when unique_violation then null;
  end;
  assert not has_function_privilege('anon','public.save_script_worker_job(jsonb,bigint)','execute');
  assert not has_function_privilege('authenticated','public.save_script_worker_job(jsonb,bigint)','execute');
end $$;
rollback;
select 'multi-computer script worker regression checks passed; probe rows rolled back' as result;
