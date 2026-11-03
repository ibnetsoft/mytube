-- Atomic replacement of a project's script version.  Only the trusted server
-- role may call this; the caller must supply the previously-read row versions.
create or replace function public.std_apply_content_revision(
 p_project_id uuid, p_owner uuid, p_expected_updated_at timestamptz, p_job_id text, p_job_revision bigint,
 p_backup_id uuid, p_project_payload jsonb, p_source_payload jsonb,
 p_progress_payload jsonb, p_scenes jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare p public.std_projects%rowtype; job public.script_worker_jobs%rowtype; old_scenes jsonb; n integer; updated_count integer;
begin
 select * into p from public.std_projects where id=p_project_id for update;
 if not found or p.user_id is distinct from p_owner then raise exception 'Project ownership mismatch'; end if;
 if p.updated_at is distinct from p_expected_updated_at then raise exception 'Project changed'; end if;
 if p.submitted_at is not null or p.status not in ('claimed','in_progress') then raise exception 'Project not editable'; end if;
 select * into job from public.script_worker_jobs where id=p_job_id for update;
 if not found or job.revision is distinct from p_job_revision
    or job.status in ('canceled','cancelled') or job.job_record->>'status' in ('canceled','cancelled')
    or job.job_record->>'topic_queue_id' is distinct from p.topic_queue_id::text
 then raise exception 'Source job changed or canceled'; end if;
 if jsonb_typeof(p_project_payload) is distinct from 'object'
    or jsonb_typeof(p_source_payload) is distinct from 'object'
    or jsonb_typeof(p_progress_payload) is distinct from 'object'
    or jsonb_typeof(p_scenes) is distinct from 'array'
    or jsonb_typeof(p_project_payload->'subtitles') is distinct from 'array'
    or jsonb_array_length(p_project_payload->'subtitles')<>0
    or jsonb_typeof(p_project_payload->'subtitle_editor_snapshot') is distinct from 'array'
    or jsonb_array_length(p_project_payload->'subtitle_editor_snapshot')<>0
    or coalesce(jsonb_array_length(p_project_payload#>'{render_settings,sfx_cues}'),0)<>0
    or p_project_payload ?| array['sfx_cues','sfx_plan','deleted_subtitle_scene_archive']
    or (p_project_payload->'render_settings') ? 'sfx_plan'
    or p_project_payload ?| array['audio_url','tts_url','tts_asset_id','tts_drive_file_id','tts_file_name','subtitle_source_audio_id']
    or p_progress_payload ?| array['audio_url','tts_url','tts_asset_id','tts_drive_file_id','tts_file_name']
    or coalesce((p_project_payload->>'tts_completed')::boolean,false)
    or coalesce((p_progress_payload->>'tts_completed')::boolean,false)
    or p_project_payload->'strict_content_identity' is distinct from 'true'::jsonb
    or nullif(btrim(p_project_payload->>'script'),'') is null
    or p_project_payload->>'script' is distinct from p_source_payload->>'pregenerated_script'
 then raise exception 'Invalid revision payload'; end if;
 n:=jsonb_array_length(p_scenes);
 if n<1 or n>500 or n<>(select count(distinct e->>'id') from jsonb_array_elements(p_scenes) e)
    or n<>(select count(distinct e->>'scene_number') from jsonb_array_elements(p_scenes) e)
 then raise exception 'Invalid scene list'; end if;
 if jsonb_typeof(p_project_payload#>'{structure,scenes}') is distinct from 'array'
    or jsonb_typeof(p_source_payload#>'{pregenerated_structure,scenes}') is distinct from 'array'
    or jsonb_array_length(p_project_payload#>'{structure,scenes}')<>n
    or jsonb_array_length(p_source_payload#>'{pregenerated_structure,scenes}')<>n
    or exists(select 1 from jsonb_array_elements(p_scenes) e
      left join jsonb_array_elements(p_project_payload#>'{structure,scenes}') a
        on (a->>'scene_number')::integer=(e->>'scene_number')::integer
      left join jsonb_array_elements(p_source_payload#>'{pregenerated_structure,scenes}') b
        on (b->>'scene_number')::integer=(e->>'scene_number')::integer
      where a is null or b is null or a->>'narration' is distinct from e->>'scene_text'
        or b->>'narration' is distinct from e->>'scene_text')
 then raise exception 'Revision structures do not match scenes'; end if;
 -- Lock all existing scene rows before checking their optimistic versions.
 perform 1 from public.std_project_scenes where project_id=p.id order by id for update;
 if n<>(select count(*) from public.std_project_scenes where project_id=p.id)
    or exists(select 1 from jsonb_array_elements(p_scenes) e
      left join public.std_project_scenes s on s.id=(e->>'id')::uuid and s.project_id=p.id
      where s.id is null or s.scene_number is distinct from (e->>'scene_number')::integer
       or s.updated_at is distinct from (e->>'expected_updated_at')::timestamptz
       or nullif(e->>'scene_title','') is null or nullif(e->>'scene_text','') is null or jsonb_typeof(e->'metadata') is distinct from 'object'
       or nullif(e->>'image_prompt','') is null or jsonb_typeof(e->'video_prompt') is distinct from 'string'
       or (e->'metadata') ?| array['image_url','video_url','image_asset_id','video_asset_id','cowork_image_asset','cowork_video_asset']
       or e->>'scene_text' is distinct from e#>>'{metadata,narration}')
 then raise exception 'Scenes changed or invalid'; end if;
 if regexp_replace(p_project_payload->>'script','\s','','g') is distinct from
    (select regexp_replace(string_agg(e->>'scene_text','' order by (e->>'scene_number')::int),'\s','','g')
      from jsonb_array_elements(p_scenes) e)
 then raise exception 'Script and scene text differ'; end if;
 if exists(select 1 from public.std_project_assets where id=p_backup_id) then raise exception 'Backup ID already exists'; end if;
 select jsonb_agg(to_jsonb(s) order by s.scene_number) into old_scenes
   from public.std_project_scenes s where s.project_id=p.id;
 insert into public.std_project_assets(id,project_id,asset_type,status,file_name,mime_type,metadata)
 values(p_backup_id,p.id,'other','uploaded','content-revision-backup.json','application/json',
   jsonb_build_object('kind','content_revision_backup','captured_at',clock_timestamp(),
     'snapshot',jsonb_build_object('project_payload',p.project_payload,'source_payload',p.source_payload,
       'progress_payload',p.progress_payload,'scenes',old_scenes)));
 update public.std_project_scenes s set scene_title=e->>'scene_title',scene_text=e->>'scene_text',image_prompt=e->>'image_prompt',
   video_prompt=e->>'video_prompt',metadata=e->'metadata',shot_hints='[]'::jsonb,asset_status='missing',updated_at=clock_timestamp()
 from jsonb_array_elements(p_scenes) e where s.id=(e->>'id')::uuid and s.project_id=p.id;
 get diagnostics updated_count = row_count;
 if updated_count<>n then raise exception 'Scene update count mismatch'; end if;
 update public.std_projects set project_payload=p_project_payload,source_payload=p_source_payload,
   progress_payload=p_progress_payload,updated_at=clock_timestamp() where id=p.id;
 return jsonb_build_object('success',true,'scene_count',n,'backup_id',p_backup_id);
end $$;
revoke all on function public.std_apply_content_revision(uuid,uuid,timestamptz,text,bigint,uuid,jsonb,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.std_apply_content_revision(uuid,uuid,timestamptz,text,bigint,uuid,jsonb,jsonb,jsonb,jsonb) to service_role;
