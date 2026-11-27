-- A candidate is private until the worker has examined its actual pixels.
-- This migration is staged locally; it does not activate or publish an image.
create table if not exists public.std_scene_image_reviews (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.std_projects(id),
 scene_id uuid not null references public.std_project_scenes(id),
 scene_number integer not null check (scene_number > 0),
 owner_id uuid not null,
 owner_email text not null,
 source_sha256 text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
 candidate_sha256 text not null check (candidate_sha256 ~ '^[0-9a-f]{64}$'),
 candidate_bucket text not null,
 candidate_path text not null,
 project_updated_at timestamptz not null,
 scene_updated_at timestamptz not null,
 status text not null default 'queued' check (status in ('queued','running','review_failed','conflict','completed')),
 claim_token uuid,
 claimed_at timestamptz,
 attempt_count integer not null default 0,
 next_attempt_at timestamptz not null default now(),
 review jsonb,
 error text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create unique index if not exists std_scene_image_reviews_one_active
 on public.std_scene_image_reviews(project_id,scene_id) where status in ('queued','running');
alter table public.std_scene_image_reviews enable row level security;
revoke all on public.std_scene_image_reviews from public,anon,authenticated;
grant select,insert,update on public.std_scene_image_reviews to service_role;

create or replace function public.claim_std_scene_image_review()
returns setof public.std_scene_image_reviews language plpgsql security invoker set search_path='' as $$
declare candidate uuid;
begin
 select id into candidate from public.std_scene_image_reviews
  where (status='queued' and next_attempt_at<=clock_timestamp()) or (status='running' and claimed_at < clock_timestamp()-interval '30 minutes')
  order by created_at for update skip locked limit 1;
 if candidate is null then return; end if;
 return query update public.std_scene_image_reviews set status='running',claim_token=gen_random_uuid(),
   claimed_at=clock_timestamp(),attempt_count=attempt_count+1,updated_at=clock_timestamp(),error=null
  where id=candidate returning *;
end $$;
revoke all on function public.claim_std_scene_image_review() from public,anon,authenticated;
grant execute on function public.claim_std_scene_image_review() to service_role;

-- Worker-only claim renewal: a stale worker cannot publish a later claim.
create or replace function public.touch_std_scene_image_review(p_id uuid,p_claim_token uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 update public.std_scene_image_reviews set claimed_at=clock_timestamp(),updated_at=clock_timestamp()
 where id=p_id and status='running' and claim_token=p_claim_token;
 return found;
end $$;
revoke all on function public.touch_std_scene_image_review(uuid,uuid) from public,anon,authenticated;
grant execute on function public.touch_std_scene_image_review(uuid,uuid) to service_role;

create or replace function public.std_scene_review_block_transition(v jsonb, cut text)
returns jsonb language plpgsql immutable set search_path='' as $$
declare ids jsonb;
begin
 if jsonb_typeof(v) is distinct from 'object' or not (coalesce(v->>'from_cut_id'=cut,false) or coalesce(v->>'to_cut_id'=cut,false)) then return v; end if;
 ids:=case when jsonb_typeof(v->'blocked_cut_ids')='array' then v->'blocked_cut_ids' else '[]'::jsonb end;
 if not ids ? cut then ids:=ids||to_jsonb(cut); end if;
 return v||jsonb_build_object('readiness','blocked_source','blocked_cut_ids',ids);
end $$;
revoke all on function public.std_scene_review_block_transition(jsonb,text) from public,anon,authenticated;
grant execute on function public.std_scene_review_block_transition(jsonb,text) to service_role;

create or replace function public.apply_std_scene_image_review(p_id uuid,p_claim_token uuid,p_review jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare j public.std_scene_image_reviews%rowtype; p public.std_projects%rowtype; s public.std_project_scenes%rowtype;
 oldmeta jsonb; newmeta jsonb; structure jsonb; scenes jsonb; item jsonb; arr jsonb; plan jsonb; trs jsonb;
 cut text; aid uuid; url text; backup_id uuid; cnt int; key text; v_payload jsonb; old_assets jsonb;
begin
 select * into j from public.std_scene_image_reviews where id=p_id for update;
 if not found or j.status<>'running' or j.claim_token is distinct from p_claim_token then raise exception '검수 작업이 변경되었습니다'; end if;
 if p_review->>'contract' is distinct from 'wuxia_scene_replacement/v1' or p_review->>'source_sha256' is distinct from j.candidate_sha256
    or p_review->>'previous_source_sha256' is distinct from j.source_sha256
    or p_review#>>'{anatomy_review,source_sha256}' is distinct from j.candidate_sha256
    or p_review->>'asset_id' is distinct from j.id::text
    or p_review#>>'{anatomy_review,asset_id}' is distinct from j.id::text
    or p_review#>>'{anatomy_review,scene_id}' is distinct from p_review->>'scene_id'
    or p_review#>>'{anatomy_review,contract}' is distinct from 'wuxia_anatomy_review/v1'
    or p_review#>>'{anatomy_review,pixel_evidence,source_sha256}' is distinct from j.candidate_sha256
    or p_review#>>'{continuity_review,source_sha256}' is distinct from j.source_sha256
    or p_review#>>'{continuity_review,candidate_sha256}' is distinct from j.candidate_sha256
    or p_review#>>'{continuity_review,verdict}' is distinct from 'pass'
    or jsonb_typeof(p_review#>'{continuity_review,evidence}') is distinct from 'array'
    or coalesce(jsonb_array_length(p_review#>'{continuity_review,evidence}'),0) = 0
    or p_review#>>'{anatomy_review,decision}' is distinct from 'passed' or p_review#>'{anatomy_review,passed}' is distinct from 'true'::jsonb
 then raise exception '실제 이미지 검수 결과가 일치하지 않습니다'; end if;
 select * into p from public.std_projects where id=j.project_id for update;
 select * into s from public.std_project_scenes where id=j.scene_id and project_id=j.project_id for update;
 if p.id is null or s.id is null or p.user_id is distinct from j.owner_id or lower(p.employee_email)<>lower(j.owner_email)
    or j.candidate_sha256=j.source_sha256
    or j.candidate_path is distinct from ('std-projects/'||j.project_id||'/scene-image-review/'||j.id||'/'||j.candidate_sha256||'.png')
    or p.status not in ('claimed','in_progress') or p.submitted_at is not null
    or p.updated_at is distinct from j.project_updated_at or s.updated_at is distinct from j.scene_updated_at
    or s.metadata->>'source_image_sha256' is distinct from j.source_sha256 or s.scene_number<>j.scene_number
 then raise exception '프로젝트 또는 원본이 변경되었습니다'; end if;
 if p.project_payload->>'strict_content_identity'='true' or p.project_payload#>'{structure,wuxia_ae_package}' is not null then
    raise exception '이 프로젝트의 원본 패키지는 별도 재검토가 필요합니다'; end if;
 oldmeta:=s.metadata; cut:=oldmeta->>'cut_id';
 if cut is null or p_review->>'scene_id' is distinct from coalesce(nullif(oldmeta->>'scene_id',''),oldmeta->>'cut_id') then raise exception '컷 연결이 다릅니다'; end if;
 structure:=p.project_payload->'structure'; scenes:=structure->'scenes';
 if jsonb_typeof(scenes) is distinct from 'array' then raise exception '씬 목록이 없습니다'; end if;
 select count(*) into cnt from jsonb_array_elements(scenes) e where e->>'cut_id'=cut and e->>'source_image_sha256'=j.source_sha256;
 if cnt<>1 then raise exception '원본 컷 연결이 변경되었습니다'; end if;
 aid:=j.id; url:='/api/std/projects/'||p.id||'/assets/file?assetId='||aid;
 perform 1 from public.std_project_assets where project_id=p.id and scene_number=j.scene_number order by id for update;
 if exists(select 1 from public.std_project_assets a where a.project_id=p.id and a.scene_number=j.scene_number
   and a.asset_type='video' and a.status in ('uploaded','assigned')
   and coalesce(a.metadata->>'ae_mouth_fingerprint','')='' and coalesce(a.metadata->>'lipsync_fingerprint','')=''
   and coalesce(a.metadata->>'kind','')<>'mouth_preview') then
    raise exception '원본 영상이 연결되어 이미지를 교체할 수 없습니다';
 end if;
 select coalesce(jsonb_agg(to_jsonb(a)),'[]'::jsonb) into old_assets from public.std_project_assets a where a.project_id=p.id and a.scene_number=j.scene_number and a.status in ('uploaded','assigned');
 backup_id:=gen_random_uuid();
 insert into public.std_project_assets(id,project_id,scene_id,scene_number,asset_type,status,file_name,mime_type,metadata)
 values(backup_id,p.id,s.id,j.scene_number,'other','uploaded','scene-image-before-replacement.json','application/json',
   jsonb_build_object('kind','scene_image_replacement_backup','source_sha256',j.source_sha256,'scene_metadata',oldmeta,'source_assets',old_assets,
    'structure_scene',(select e from jsonb_array_elements(scenes) e where e->>'cut_id'=cut limit 1),
    'transition_plan',structure->'cut_transition_plan',
    'adjacent_scenes',(select coalesce(jsonb_agg(jsonb_build_object('id',a.id,'metadata',a.metadata)),'[]'::jsonb) from public.std_project_scenes a where a.project_id=p.id and a.id<>s.id and a.metadata#>>'{outgoing_transition,to_cut_id}'=cut)));
 update public.std_project_assets a set status='replaced',updated_at=clock_timestamp()
  where a.project_id=p.id and a.scene_number=j.scene_number and a.status in ('uploaded','assigned') and a.id<>backup_id
   and (a.asset_type='image' or a.metadata->>'kind' in ('mouth_preview','ae_speaker_coordinates','wuxia_mouth_preparation','region_layer_package','ae_scene_preparation')
     or coalesce(a.metadata->>'ae_mouth_fingerprint','')<>'' or coalesce(a.metadata->>'lipsync_fingerprint','')<>'');
 insert into public.std_project_assets(id,project_id,scene_id,scene_number,asset_type,status,file_name,mime_type,file_size,metadata)
 values(aid,p.id,s.id,j.scene_number,'image','assigned','reviewed-scene.png','image/png',null,
   jsonb_build_object('storage_provider','gcs','storage_bucket',j.candidate_bucket,'storage_path',j.candidate_path,
     'gcs_bucket',j.candidate_bucket,'gcs_path',j.candidate_path,'sha256',j.candidate_sha256,'anatomy_review',p_review->'anatomy_review'));
 newmeta:=(oldmeta-array['cowork_image_asset','mouth_preview_url','speaker_geometry','dialogue_mouths','ambient_loops','energy_preparation','cinematic_review','motion_speed'])
   ||jsonb_build_object('image',url,'image_url',url,'gcs_bucket',j.candidate_bucket,'gcs_path',j.candidate_path,'storage_provider','gcs',
      'source_image_sha256',j.candidate_sha256,'image_asset_id',aid,'image_gcs_path',j.candidate_path,'image_file_name','reviewed-scene.png','image_use_status','approved','asset_status','ready','anatomy_review',p_review->'anatomy_review',
      'image_effect','none','transition_effect','none','source_bound_review',jsonb_build_object('status','review_required','source_sha256',j.candidate_sha256,
        'previous_source_sha256',j.source_sha256,'mouth_and_effects','review_required','adjacent_transitions','review_required'));
 if newmeta ? 'outgoing_transition' then newmeta:=jsonb_set(newmeta,'{outgoing_transition}',public.std_scene_review_block_transition(newmeta->'outgoing_transition',cut)); end if;
 update public.std_project_scenes set metadata=newmeta,asset_status='ready',updated_at=clock_timestamp() where id=s.id;
 update public.std_project_scenes a set metadata=jsonb_set(a.metadata||jsonb_build_object('transition_effect','none'),'{outgoing_transition}',public.std_scene_review_block_transition(a.metadata->'outgoing_transition',cut)),updated_at=clock_timestamp() where a.project_id=p.id and a.id<>s.id and a.metadata#>>'{outgoing_transition,to_cut_id}'=cut;
 arr:='[]'::jsonb;
 for item in select value from jsonb_array_elements(scenes) loop
  if item->>'cut_id'=cut then
   item:=(item-array['cowork_image_asset','mouth_preview_url','speaker_geometry','dialogue_mouths','ambient_loops','energy_preparation','cinematic_review','motion_speed'])
      ||jsonb_build_object('image',url,'image_url',url,'gcs_bucket',j.candidate_bucket,'gcs_path',j.candidate_path,'storage_provider','gcs',
        'source_image_sha256',j.candidate_sha256,'image_asset_id',aid,'image_gcs_path',j.candidate_path,'image_file_name','reviewed-scene.png','image_use_status','approved','asset_status','ready','anatomy_review',p_review->'anatomy_review',
        'image_effect','none','transition_effect','none','source_bound_review',newmeta->'source_bound_review');
   if jsonb_typeof(item->'metadata')='object' then item:=jsonb_set(item,'{metadata}',newmeta,true); end if;
  end if;
  if item#>>'{outgoing_transition,to_cut_id}'=cut then
   item:=item||jsonb_build_object('transition_effect','none');
   if jsonb_typeof(item->'metadata')='object' then item:=jsonb_set(item,'{metadata,transition_effect}',to_jsonb('none'::text),true); end if;
  end if;
  if item ? 'outgoing_transition' then item:=jsonb_set(item,'{outgoing_transition}',public.std_scene_review_block_transition(item->'outgoing_transition',cut)); end if;
  arr:=arr||jsonb_build_array(item);
 end loop;
 structure:=jsonb_set(structure,'{scenes}',arr,true);
 plan:=coalesce(structure->'cut_transition_plan',p.source_payload#>'{pregenerated_structure,cut_transition_plan}',p.source_payload#>'{structure,cut_transition_plan}',p.source_payload->'cut_transition_plan');
 if jsonb_typeof(plan->'transitions')='array' then
  trs:='[]'::jsonb;
  for item in select value from jsonb_array_elements(plan->'transitions') loop
   trs:=trs||jsonb_build_array(public.std_scene_review_block_transition(item,cut));
  end loop;
  plan:=jsonb_set(plan,'{transitions}',trs,true);
  plan:=jsonb_set(plan,'{blocked_transitions}',(select coalesce(jsonb_agg(x->>'transition_id'),'[]'::jsonb) from jsonb_array_elements(trs) x
    where case when jsonb_typeof(x->'blocked_cut_ids')='array' then jsonb_array_length(x->'blocked_cut_ids')>0 else false end),true);
  structure:=jsonb_set(structure,'{cut_transition_plan}',plan,true);
 end if;
 v_payload:=jsonb_set(p.project_payload,'{structure}',structure,true);
 if jsonb_typeof(v_payload->'scenes')='array' then
  arr:='[]'::jsonb;
  for item in select value from jsonb_array_elements(v_payload->'scenes') loop
   if item->>'cut_id'=cut then
    item:=(item-array['cowork_image_asset','mouth_preview_url','speaker_geometry','dialogue_mouths','ambient_loops','energy_preparation','cinematic_review','motion_speed'])||jsonb_build_object('image',url,'image_url',url,'gcs_bucket',j.candidate_bucket,'gcs_path',j.candidate_path,'source_image_sha256',j.candidate_sha256,'image_asset_id',aid,'image_gcs_path',j.candidate_path,'image_file_name','reviewed-scene.png','image_effect','none','transition_effect','none','source_bound_review',newmeta->'source_bound_review');
    if jsonb_typeof(item->'metadata')='object' then item:=jsonb_set(item,'{metadata}',newmeta,true); end if;
   end if;
   if item#>>'{outgoing_transition,to_cut_id}'=cut then
    item:=item||jsonb_build_object('transition_effect','none');
    if jsonb_typeof(item->'metadata')='object' then item:=jsonb_set(item,'{metadata,transition_effect}',to_jsonb('none'::text),true); end if;
   end if;
   if item ? 'outgoing_transition' then item:=jsonb_set(item,'{outgoing_transition}',public.std_scene_review_block_transition(item->'outgoing_transition',cut)); end if;
   arr:=arr||jsonb_build_array(item);
  end loop;
  v_payload:=jsonb_set(v_payload,'{scenes}',arr,true);
 end if;
 update public.std_projects set project_payload=v_payload,updated_at=clock_timestamp() where id=p.id;
 update public.std_scene_image_reviews set status='completed',review=p_review,updated_at=clock_timestamp() where id=j.id;
 return jsonb_build_object('success',true,'asset_id',aid,'backup_id',backup_id,'source_sha256',j.candidate_sha256);
end $$;
revoke all on function public.apply_std_scene_image_review(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.apply_std_scene_image_review(uuid,uuid,jsonb) to service_role;
