-- Keep production direction in the database while sending only editor state.
create or replace function public.std_subtitle_compact_payload(p jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare doc jsonb := coalesce(p,'{}'::jsonb); result jsonb; scenes jsonb;
begin
  select coalesce(jsonb_object_agg(key,value),'{}'::jsonb) into result
  from jsonb_each(doc) where key not in ('structure','scenes');
  select coalesce(jsonb_agg(jsonb_build_object('scene_number',s->'scene_number',
    'scene_order',s->'scene_order','scene_text',s->'scene_text',
    'narration',s->'narration','script_excerpt',s->'script_excerpt') order by n),'[]'::jsonb)
    into scenes from jsonb_array_elements(case when jsonb_typeof(doc#>'{structure,scenes}')='array'
      then doc#>'{structure,scenes}' when jsonb_typeof(doc->'scenes')='array' then doc->'scenes' else '[]'::jsonb end)
      with ordinality t(s,n);
  return result || jsonb_build_object('structure',jsonb_build_object('scenes',scenes));
end $$;

create or replace function public.std_subtitle_save_context(p_project_id uuid) returns jsonb
language sql stable security invoker set search_path='' as $$
  select (to_jsonb(p)-'project_payload'-'source_payload') || jsonb_build_object(
    'project_payload',public.std_subtitle_compact_payload(p.project_payload), 'source_payload','{}'::jsonb)
  from public.std_projects p where p.id=p_project_id
$$;

create or replace function public.std_save_subtitle_patch(
  p_project_id uuid, p_updated_at timestamptz, p_status text,
  p_payload jsonb, p_progress jsonb, p_revisions jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare r public.std_projects%rowtype; rev jsonb; current_payload jsonb;
begin
 select * into r from public.std_projects where id=p_project_id for update;
 if not found or r.updated_at is distinct from p_updated_at or r.status is distinct from p_status then return null; end if;
 if jsonb_typeof(p_payload)<>'object' or jsonb_typeof(p_progress)<>'object'
    or (p_payload - array['subtitles','subtitles_saved','deleted_subtitle_scene_numbers','deleted_subtitle_scene_archive',
     'render_settings','subtitle_editor_snapshot','content_identity','content_revision_history','dialogue_scene_index']) <> '{}'::jsonb
    or (p_progress - array['subtitles_saved','subtitles_completed','subtitle_tts_completed','subtitle_tts_completed_at']) <> '{}'::jsonb
 then raise exception 'Invalid subtitle patch'; end if;
 current_payload := coalesce(r.project_payload,'{}'::jsonb);
 for rev in select * from jsonb_array_elements(p_revisions) loop
   if not exists(select 1 from public.std_project_assets where id=(rev->>'id')::uuid) then
     insert into public.std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
     values ((rev->>'id')::uuid,r.id,'other','uploaded','script-'||(rev#>>'{identity,script_sha256}')||'.json','application/json',
       jsonb_build_object('kind','content_revision','content_identity',rev->'identity',
        'snapshot',jsonb_build_object('script',coalesce(current_payload->'script','""'::jsonb),
         'subtitles',case when rev->>'version'='new' then p_payload->'subtitles' else current_payload->'subtitles' end,
         'structure',coalesce(current_payload->'structure','{}'::jsonb),
         'source_audio_id',coalesce(current_payload->'subtitle_source_audio_id',r.progress_payload->'tts_asset_id')),
        'captured_at',clock_timestamp())) on conflict(id) do nothing;
   end if;
 end loop;
 update public.std_projects set project_payload=current_payload || p_payload,
   progress_payload=coalesce(r.progress_payload,'{}'::jsonb)||p_progress, updated_at=clock_timestamp()
 where id=r.id;
 return public.std_subtitle_save_context(r.id);
end $$;
revoke all on function public.std_subtitle_compact_payload(jsonb),public.std_subtitle_save_context(uuid),public.std_save_subtitle_patch(uuid,timestamptz,text,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.std_subtitle_compact_payload(jsonb),public.std_subtitle_save_context(uuid),public.std_save_subtitle_patch(uuid,timestamptz,text,jsonb,jsonb,jsonb) to service_role;
