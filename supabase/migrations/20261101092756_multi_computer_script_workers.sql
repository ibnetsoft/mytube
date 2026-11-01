-- Independent computers may generate different scripts concurrently.
-- Keep one active job per worker and one repair per source.
alter table public.script_worker_jobs add column revision bigint not null default 0;
drop index public.script_worker_one_active;
create unique index script_worker_one_active_per_worker
  on public.script_worker_jobs(worker_id) where status in ('queued','running');
create unique index script_worker_one_active_repair_source
  on public.script_worker_jobs ((request_data->>'kind'), (request_data->>'source_id'))
  where status in ('queued','running') and mode='repair';
create unique index script_worker_one_active_web_topic
  on public.script_worker_jobs ((request_data->>'web_topic_id'))
  where status in ('queued','running') and nullif(request_data->>'web_topic_id','') is not null;
create unique index script_worker_one_active_retry
  on public.script_worker_jobs ((job_record->>'retry_of'))
  where status in ('queued','running') and nullif(job_record->>'retry_of','') is not null;

-- Serialize only writes to the SAME job, with optimistic version checks.
-- Exact retries after a lost HTTP response return the committed revision.
create function public.save_script_worker_job(p_row jsonb, p_expected_revision bigint)
returns bigint language plpgsql security invoker set search_path=public as $$
declare existing public.script_worker_jobs; incoming public.script_worker_jobs; next_revision bigint;
begin
  incoming := jsonb_populate_record(null::public.script_worker_jobs, p_row);
  if incoming.id is null or incoming.id !~ '^[a-f0-9]{32}$'
     or nullif(trim(incoming.worker_id),'') is null then
    raise exception 'Invalid script worker identity' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('script-worker:' || incoming.id, 0));
  select * into existing from public.script_worker_jobs where id=incoming.id for update;
  if found then
    if existing.revision=coalesce(p_expected_revision,0)+1
       and to_jsonb(existing)-'revision'=p_row then
      return existing.revision;
    end if;
    if p_expected_revision is null or existing.revision<>p_expected_revision then
      raise exception 'Script job changed on another worker; reload before saving' using errcode='40001';
    end if;
    next_revision := existing.revision+1;
    update public.script_worker_jobs set title=incoming.title,mode=incoming.mode,status=incoming.status,
      worker_id=incoming.worker_id,created_at=incoming.created_at,updated_at=incoming.updated_at,
      job_record=incoming.job_record,request_data=incoming.request_data,source_snapshot=incoming.source_snapshot,
      candidate=incoming.candidate,reference_sources=incoming.reference_sources,revision=next_revision
      where id=incoming.id;
  else
    if p_expected_revision is not null then
      raise exception 'Script job no longer exists' using errcode='40001';
    end if;
    next_revision := 1;
    insert into public.script_worker_jobs(id,title,mode,status,worker_id,created_at,updated_at,
      job_record,request_data,source_snapshot,candidate,reference_sources,revision)
    values(incoming.id,incoming.title,incoming.mode,incoming.status,incoming.worker_id,
      incoming.created_at,incoming.updated_at,incoming.job_record,incoming.request_data,
      incoming.source_snapshot,incoming.candidate,incoming.reference_sources,next_revision);
  end if;
  return next_revision;
end $$;
revoke all on function public.save_script_worker_job(jsonb,bigint) from public,anon,authenticated;
grant execute on function public.save_script_worker_job(jsonb,bigint) to service_role;
