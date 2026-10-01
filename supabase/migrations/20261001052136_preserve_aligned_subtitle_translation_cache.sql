alter table public.std_subtitle_translation_jobs add column cached_blocks jsonb not null default '[]';

create or replace function public.complete_std_subtitle_translation(job_id uuid, translated_blocks jsonb)
returns void language plpgsql security invoker set search_path = public as $$
declare j std_subtitle_translation_jobs; payload jsonb; merged jsonb;
begin
  select * into j from std_subtitle_translation_jobs where id=job_id and status='running' for update;
  if not found then raise exception 'Translation job is not running'; end if;
  if jsonb_array_length(translated_blocks) <> jsonb_array_length(j.source_blocks)
     or exists(select 1 from jsonb_array_elements(j.source_blocks) s where not exists(
         select 1 from jsonb_array_elements(translated_blocks) t where t->'index'=s->'index'
         and t->>'source_text'=s->>'source_text' and length(trim(t->>'translated_text')) > 0))
  then raise exception 'Translation result does not match source'; end if;
  select coalesce(project_payload,'{}') into payload from std_projects where id=j.project_id for update;
  -- Cache is already aligned to the current subtitle sequence by the web route.
  -- Replacing by old numeric indexes would discard translations after a split.
  select coalesce(jsonb_agg(b order by (b->>'index')::int),'[]') into merged from (
    select b from jsonb_array_elements(j.cached_blocks) b where not exists(
      select 1 from jsonb_array_elements(translated_blocks) t where t->'index'=b->'index')
    union all select b from jsonb_array_elements(translated_blocks) b
  ) rows;
  if coalesce((payload->'subtitle_translations'->j.target_language->>'request_created_at')::timestamptz,'epoch') <= j.created_at then
    payload := jsonb_set(payload,'{subtitle_translations}',
      coalesce(payload->'subtitle_translations','{}') || jsonb_build_object(j.target_language,
        jsonb_build_object('version',1,'updated_at',now(),'request_created_at',j.created_at,'blocks',merged,'provider','local-codex')));
    update std_projects set project_payload=payload where id=j.project_id;
  end if;
  update std_subtitle_translation_jobs set status='completed', result_blocks=translated_blocks, completed_at=now() where id=j.id;
end $$;
