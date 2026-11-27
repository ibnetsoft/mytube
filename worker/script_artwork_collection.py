"""Read-only review gallery for explicitly imported user cut boards.
Candidates are not production-approved images and never enter AE automatically.
"""
import hashlib
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

def register(app,jobs):
    @app.get('/api/jobs/{identity}/artwork/file/{cut_id}')
    def artwork(identity:str,cut_id:str):
        bundle=jobs.bundle(identity) if identity in jobs.rows else jobs.load(identity)
        collection=bundle.get('candidate',{}).get('manual_workflow',{}).get('artwork_collection',{})
        row=next((r for r in collection.get('cuts',[]) if r.get('cut_id')==cut_id),None)
        if not row:raise HTTPException(404,'등록된 컷이 없습니다.')
        if row.get('preview_status')!='review_candidate':raise HTTPException(409,'파일 누락 또는 인체 구조 검토를 위한 표시 제외 상태입니다.')
        expected=row.get('sha256');path=Path(row.get('local_path','')).resolve()
        root=(Path(__file__).resolve().parents[1]/'output').resolve()
        if path.is_relative_to(root) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:
            return FileResponse(path,media_type=row.get('mime_type','image/png'),headers={'Cache-Control':'private, max-age=300'})
        from worker.cowork_scene_assets import _gcs_credentials
        from urllib.parse import quote
        import requests
        creds,_=_gcs_credentials()
        url='https://storage.googleapis.com/storage/v1/b/'+quote(row['storage_bucket'],safe='')+'/o/'+quote(row['storage_path'],safe='')
        response=requests.get(url,params={'alt':'media'},headers={'Authorization':'Bearer '+creds.token},timeout=45)
        if not response.ok or hashlib.sha256(response.content).hexdigest()!=expected:raise HTTPException(502,'저장 이미지 무결성 확인 실패')
        return Response(response.content,media_type=row.get('mime_type','image/png'),headers={'Cache-Control':'private, max-age=300'})

    from pydantic import BaseModel, Field
    class VideoPlanRequest(BaseModel):
        expected_hash: str = Field(min_length=64,max_length=64)
        plan: dict
    globals()['ArtworkVideoPlanRequest']=VideoPlanRequest

    @app.post('/api/jobs/{identity}/artwork/video-plan')
    def save_video_plan(identity:str,body:VideoPlanRequest):
        import copy,json,time
        from worker.script_manual_workflow import digest,write,state_summary
        try:
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:
                    raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c.get('manual_workflow',{});a=w.get('artwork_collection');plan=body.plan
                if not a or plan.get('contract')!='manual_cut_video_plan/v1' or plan.get('job_id')!=identity or plan.get('scope')!='prompts_only_no_generation':
                    raise ValueError('현재 컷 목록에 연결된 영상 프롬프트 계획이 필요합니다.')
                groups=plan.get('groups',[]);known={r['cut_id']:r for r in a.get('cuts',[])}
                if not 1<=len(groups)<=120 or len(json.dumps(plan,ensure_ascii=False))>300000:raise ValueError('영상 프롬프트 크기를 확인하세요.')
                seen=set()
                for g in groups:
                    if not isinstance(g.get('id'),str) or g['id'] in seen:raise ValueError('영상 구간 ID를 확인하세요.')
                    seen.add(g['id'])
                    if not isinstance(g.get('video_prompt_ko'),str) or not g['video_prompt_ko'].strip() or not 0<float(g.get('duration_seconds',0))<=30:raise ValueError('프롬프트와 구간 길이가 필요합니다.')
                    ids=g.get('cut_ids',[]);refs=g.get('source_images',[])
                    if not ids or len(ids)!=len(set(ids)) or [r.get('cut_id') for r in refs]!=ids:raise ValueError('컷별 참조 연결을 확인하세요.')
                    for r in refs:
                        source=known.get(r['cut_id'],{})
                        if source.get('preview_status')!='review_candidate' or r.get('sha256')!=source.get('sha256'):raise ValueError('누락·제외·변경된 원화는 영상 프롬프트 참조로 확정할 수 없습니다.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-video-plan-{time.time_ns()}.json',c)
                a['video_plan']=copy.deepcopy(plan);w['revision']=w.get('revision',0)+1
                write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':
                    jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'groups':len(groups),'sync_status':jobs.rows[identity].get('sync_status'),'candidate_hash':digest(c)}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/artwork/ae-plan')
    def save_ae_plan(identity:str,body:VideoPlanRequest):
        import copy,json,time,math
        from worker.script_manual_workflow import digest,write,state_summary
        try:
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:
                    raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c.get('manual_workflow',{});a=w.get('artwork_collection');plan=body.plan
                if not a or plan.get('contract')!='manual_cut_ae_plan/v1' or plan.get('job_id')!=identity or plan.get('scope')!='directions_only_no_render':
                    raise ValueError('현재 컷 목록에 연결된 AE 작업지침이 필요합니다.')
                video_plan=a.get('video_plan')
                if not video_plan or digest(video_plan)!=plan.get('video_plan_sha256'):raise ValueError('영상 선택이 변경됐습니다. 중복 적용 범위를 다시 확인하세요.')
                video={cid for group in video_plan.get('groups',[]) for cid in group.get('cut_ids',[])}
                if sorted(video)!=plan.get('excluded_video_cut_ids'):raise ValueError('영상클립 제외 컷이 일치하지 않습니다.')
                rows=plan.get('directions',[]);known={r['cut_id']:r for r in a.get('cuts',[])};seen=set()
                if not 1<=len(rows)<=120 or plan.get('selected_count')!=len(rows) or len(json.dumps(plan,ensure_ascii=False))>600000:
                    raise ValueError('AE 지침 수와 크기를 확인하세요.')
                for row in rows:
                    cid=row.get('cut_id');source=known.get(cid,{})
                    if cid in seen or cid in video or source.get('preview_status')!='review_candidate' or source.get('sha256')!=row.get('source_sha256'):
                        raise ValueError('중복·영상클립·누락·제외·변경된 컷은 AE 지침에 연결할 수 없습니다.')
                    seen.add(cid)
                    if not isinstance(row.get('effects'),list) or not row['effects']:raise ValueError('효과별 시점·길이를 지정하세요.')
                    for effect in row['effects']:
                        start=effect.get('start_seconds');duration=effect.get('duration_seconds')
                        if not isinstance(start,(int,float)) or not math.isfinite(start) or start<0:raise ValueError('효과 시작 시각을 확인하세요.')
                        if duration is None:
                            if not effect.get('duration_expression'):raise ValueError('음성·컷 길이에 연결할 지속시간 식이 필요합니다.')
                        elif not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0<duration<=30:raise ValueError('효과 지속시간을 확인하세요.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-ae-plan-{time.time_ns()}.json',c)
                a['ae_plan']=copy.deepcopy(plan)
                for cut in a.get('cuts',[]):cut.pop('ae_direction',None)
                for row in rows:known[row['cut_id']]['ae_direction']=copy.deepcopy(row)
                w['revision']=w.get('revision',0)+1
                write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':
                    jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'cuts':len(rows),'video_overlap':[],'sync_status':jobs.rows[identity].get('sync_status'),'candidate_hash':digest(c)}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/artwork/transitions')
    def save_transitions(identity:str,body:VideoPlanRequest):
        import copy,json,time,math
        from worker.script_manual_workflow import digest,write,state_summary
        try:
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c.get('manual_workflow',{});a=w.get('artwork_collection');p=body.plan
                if not a or p.get('contract')!='manual_cut_transition_plan/v1' or p.get('job_id')!=identity or p.get('scope')!='transition_directions_only_no_render':raise ValueError('현재 컷 목록의 전환 지침이 필요합니다.')
                if digest(a.get('video_plan'))!=p.get('video_plan_sha256') or digest(a.get('ae_plan'))!=p.get('ae_plan_sha256'):raise ValueError('영상/내부 효과 지침 변경을 먼저 반영하세요.')
                cuts=a.get('cuts',[]);rows=p.get('transitions',[])
                if len(rows)!=len(cuts)-1 or p.get('transition_count')!=len(rows) or len(json.dumps(p,ensure_ascii=False))>600000:raise ValueError('전체 이웃 연결을 순서대로 지정하세요.')
                internal={tuple(g['cut_ids'][i:i+2]):g['id'] for g in a['video_plan']['groups'] for i in range(len(g['cut_ids'])-1)}
                for i,row in enumerate(rows):
                    left,right=cuts[i:i+2]
                    if (row.get('from_cut_id'),row.get('to_cut_id'))!=(left['cut_id'],right['cut_id']) or row.get('transition_id')!=f'T{i+1:03d}':raise ValueError('컷 연결 순서가 다릅니다.')
                    if row.get('source_sha256')!=left.get('sha256') or row.get('destination_sha256')!=right.get('sha256'):raise ValueError('원화 버전이 변경됐습니다.')
                    d=row.get('duration_seconds')
                    if row.get('effect') not in ('hard_cut','dissolve','dip_black','punch_zoom','push','slide') or not isinstance(d,(int,float)) or not math.isfinite(d) or not 0<=d<=1:raise ValueError('전환 종류와 길이를 확인하세요.')
                    blocked=[r['cut_id'] for r in (left,right) if r.get('preview_status')!='review_candidate']
                    if row.get('blocked_cut_ids')!=blocked or (blocked and row.get('readiness')!='blocked_source'):raise ValueError('누락/제외 원화 연결은 적용 보류여야 합니다.')
                    clip=internal.get((left['cut_id'],right['cut_id']))
                    if clip and (row.get('video_group_id')!=clip or row.get('execution_owner')!='video_clip_internal_edit' or not row.get('avoid_duplicate') or row['effect']!='hard_cut' or d!=0):raise ValueError('영상클립 내부 편집에 전환을 중복할 수 없습니다.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-transitions-{time.time_ns()}.json',c)
                a['transition_plan']=copy.deepcopy(p)
                from worker.script_transition_export import attach_transition_display
                attach_transition_display(c)
                for cut in cuts:cut.pop('outgoing_transition',None)
                for cut,row in zip(cuts,rows):cut['outgoing_transition']=copy.deepcopy(row)
                w['revision']=w.get('revision',0)+1;write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'transitions':len(rows),'blocked_transitions':p.get('blocked_transitions'),'sync_status':jobs.rows[identity].get('sync_status'),'candidate_hash':digest(c)}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/artwork/parallax-plan')
    def save_parallax(identity:str,body:VideoPlanRequest):
        import copy,json,time
        from worker.script_manual_workflow import digest,write,state_summary
        try:
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c.get('manual_workflow',{});a=w.get('artwork_collection');p=body.plan
                if not a or p.get('contract')!='manual_cut_parallax_plan/v1' or p.get('job_id')!=identity or p.get('scope')!='source_and_directions_only_ae_execution_later' or p.get('ae_execution_deferred') is not True:raise ValueError('나중 AE 작업용 패럴럭스 지침이 필요합니다.')
                rows=p.get('directions',[]);known={r['cut_id']:r for r in a['cuts']}
                if len(rows)!=2 or [r.get('cut_id') for r in rows]!=['C048','C079'] or len(json.dumps(p))>100000:raise ValueError('선택한 48번과 79번의 지침을 확인하세요.')
                for r in rows:
                    source=known[r['cut_id']]
                    if source.get('preview_status')!='review_candidate' or source.get('sha256')!=r.get('source_sha256') or len(r.get('layers',[]))!=3:raise ValueError('원화 버전·깊이 구성을 확인하세요.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-parallax-{time.time_ns()}.json',c)
                a['parallax_plan']=copy.deepcopy(p)
                for cut in a['cuts']:cut.pop('parallax_direction',None)
                for r in rows:known[r['cut_id']]['parallax_direction']=copy.deepcopy(r)
                w['revision']=w.get('revision',0)+1;write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'cuts':['C048','C079'],'ae_execution_deferred':True,'sync_status':jobs.rows[identity].get('sync_status')}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/artwork/import-image')
    def import_image(identity:str,body:VideoPlanRequest):
        import copy,json,time
        from PIL import Image
        from worker.script_manual_workflow import digest,write,state_summary
        from worker.script_transition_export import attach_transition_display
        try:
            asset=body.plan;cid=asset.get('cut_id');path=Path(asset.get('local_path','')).resolve();root=(Path(__file__).resolve().parents[1]/'output').resolve()
            if asset.get('source_kind') not in ('user_upload','builtin_image_gen_reviewed_repair') or not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=asset.get('sha256'):raise ValueError('이미지 파일과 검증값을 확인하세요.')
            if asset.get('source_kind')=='builtin_image_gen_reviewed_repair':
                review=asset.get('anatomy_review') or {}
                if review.get('source_sha256')!=asset.get('sha256') or review.get('verdict')!='pass' or not review.get('findings') or not asset.get('generation_source_path'):raise ValueError('수정 원화의 실제 SHA에 연결된 인체 검수 근거가 필요합니다.')
            with Image.open(path) as im:
                im.load();mime={'JPEG':'image/jpeg','PNG':'image/png'}.get(im.format)
                if not mime or asset.get('mime_type')!=mime or list(im.size)!=asset.get('dimensions'):raise ValueError('이미지 형식·크기를 확인하세요.')
            if not asset.get('storage_bucket') or not str(asset.get('storage_path','')).startswith('script-worker/'+identity+'/artwork/'+str(cid)+'/'):raise ValueError('현재 작업의 저장소 경로를 확인하세요.')
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c.get('manual_workflow',{});a=w.get('artwork_collection');known={r['cut_id']:r for r in (a or {}).get('cuts',[])}
                if cid not in known:raise ValueError('현재 목록에 있는 컷을 선택하세요.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-image-{cid}-{time.time_ns()}.json',c)
                row=known[cid]
                if row.get('sha256')!=asset.get('sha256'):row.setdefault('asset_history',[]).append({k:copy.deepcopy(v) for k,v in row.items() if k not in ('asset_history','outgoing_transition','ae_direction','parallax_direction')})
                row.update(copy.deepcopy(asset));row.pop('reason',None)
                if asset.get('source_kind')=='builtin_image_gen_reviewed_repair':
                    def bind_repaired_source(value):
                        if isinstance(value,list):
                            for item in value:bind_repaired_source(item)
                        elif isinstance(value,dict):
                            if value.get('cut_id')==cid and ('image_use_status' in value or 'image_prompt' in value):
                                value.update(image_url=asset['storage_url'],image=asset['storage_url'],source_image_sha256=asset['sha256'],image_use_status='approved',asset_status='ready',storage_provider='gcs',gcs_bucket=asset['storage_bucket'],gcs_path=asset['storage_path'],anatomy_review=copy.deepcopy(asset['anatomy_review']))
                                value.pop('image_exclusion_reason',None)
                                if asset.get('visual_action'):value['visual_action']=asset['visual_action']
                                if asset.get('corrected_image_prompt'):value['image_prompt']=asset['corrected_image_prompt']
                            for child in list(value.values()):
                                if isinstance(child,(dict,list)):bind_repaired_source(child)
                    bind_repaired_source(c.get('structure',{}))
                    for stage in w.get('stages',[]):bind_repaired_source(stage.get('output',{}))
                for stale in ('ae_direction','parallax_direction'):row.pop(stale,None)
                for key in ('ae_plan','parallax_plan'):
                    for r in (a.get(key) or {}).get('directions',[]):
                        if r.get('cut_id')==cid:r['status']='stale_source';r['production_approved']=False
                a['image_count']=sum(bool(r.get('sha256')) for r in a['cuts']);a['missing']=[r['cut_id'] for r in a['cuts'] if not r.get('sha256')]
                p=a.get('transition_plan')
                if p:
                    for t in p['transitions']:
                        left,right=known[t['from_cut_id']],known[t['to_cut_id']]
                        t['source_sha256']=left.get('sha256');t['destination_sha256']=right.get('sha256');t['blocked_cut_ids']=[r['cut_id'] for r in (left,right) if r.get('preview_status')!='review_candidate'];t['readiness']='blocked_source' if t['blocked_cut_ids'] else 'direction_ready_pending_timeline_review'
                        if not t['blocked_cut_ids']:t['implementation_note']=t['implementation_note'].split(' 현재 해당 원화 누락/표시 제외로 실행 보류.')[0]
                        known[t['from_cut_id']]['outgoing_transition']=copy.deepcopy(t)
                    p['blocked_transitions']=[t['transition_id'] for t in p['transitions'] if t['blocked_cut_ids']]
                    p['global_rules']=[r for r in p.get('global_rules',[]) if not ('C063' in r and '이미지 없음' in r)]
                    p['global_rules'].append('C063은 사용자 제공 이미지로 보완. 원화 표시 제외 상태는 해당 컷에만 별도 유지.')
                    attach_transition_display(c)
                w['revision']=w.get('revision',0)+1;write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'cut_id':cid,'image_count':a['image_count'],'missing':a['missing'],'sync_status':jobs.rows[identity].get('sync_status')}
        except (ValueError,KeyError,TypeError,OSError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/voice-cast')
    def save_voice_cast(identity:str,body:VideoPlanRequest):
        import copy,json,time
        from worker.script_manual_workflow import digest,write,state_summary
        from worker.script_voice_cast import attach_voice_cast
        try:
            p=body.plan
            if p.get('contract')!='manual_voice_cast/v1' or p.get('job_id')!=identity or p.get('scope')!='voice_settings_only_no_generation' or p.get('generation_requested') is not False:raise ValueError('음성 생성 없는 성우 설정만 저장할 수 있습니다.')
            if len(json.dumps(p))>200000:raise ValueError('성우 설정 크기를 확인하세요.')
            path=Path(p.get('source_path','')).resolve();root=(Path(__file__).resolve().parents[1]/'output').resolve()
            if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=p.get('source_sha256'):raise ValueError('1화 출처 저장본을 확인하세요.')
            source=json.loads(path.read_text());payload=source.get('project_payload',source);actual={}
            for s in payload.get('subtitles',[]):
                role='내레이터' if s.get('dialogue_kind')=='narration' else s.get('dialogue_speaker') if s.get('dialogue_kind')=='dialogue' else None
                if role and s.get('voice_id'):
                    if role in actual and actual[role]!=s['voice_id']:raise ValueError('1화 성우 설정이 화자별로 충돌합니다.')
                    actual[role]=s['voice_id']
            if any(actual.get(role)!=v.get('voice_id') for role,v in p.get('applied_cast',{}).items()):raise ValueError('1화 실제 화자별 성우와 일치하지 않습니다.')
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c['manual_workflow'];scenes={s['scene_id']:s for s in w['stages'][0]['output']['scenes']};seen=set()
                for binding in p.get('bindings',[])+p.get('unassigned',[]):
                    key=(binding['scene_id'],binding['block_index'])
                    if key in seen:raise ValueError('발화 연결이 중복됩니다.')
                    seen.add(key);block=scenes[key[0]]['spoken_blocks'][key[1]];role='내레이터' if block['kind']=='narration' else block.get('speaker')
                    if binding['speaker']!=role or binding['text_sha256']!=hashlib.sha256(block['text'].encode()).hexdigest():raise ValueError('2화 대사·화자 버전이 변경됐습니다.')
                    if binding.get('voice_id') and actual.get(role)!=binding['voice_id']:raise ValueError('다른 인물의 성우를 연결할 수 없습니다.')
                if len(seen)!=sum(len(s['spoken_blocks']) for s in scenes.values()):raise ValueError('모든 발화의 연결/미지정 상태가 필요합니다.')
                write(jobs.root/identity/'manual-history'/f'{w.get("revision",0)}-before-voice-cast-{time.time_ns()}.json',c)
                w['voice_cast']=copy.deepcopy(p);w['revision']=w.get('revision',0)+1;attach_voice_cast(c);write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'updated_at':time.time()}
                if j.get('sync_status')=='pending':jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'assigned_blocks':len(p['bindings']),'unassigned_blocks':len(p['unassigned']),'generation_requested':False,'sync_status':jobs.rows[identity].get('sync_status')}
        except (ValueError,KeyError,TypeError,IndexError,OSError) as exc:raise HTTPException(409,str(exc)) from exc

    @app.post('/api/jobs/{identity}/topic-registration')
    def save_topic_registration(identity:str,body:VideoPlanRequest):
        import copy,time
        from worker.script_manual_workflow import digest,write,state_summary
        try:
            p=body.plan
            if p.get('source_job_id')!=identity or p.get('status')!='registered_readback_verified' or not isinstance(p.get('topic_id'),int):raise ValueError('확인된 주제 등록 영수증이 필요합니다.')
            rows,_=jobs.store.request('GET','topics_queue',params={'id':'eq.'+str(p['topic_id']),'select':'id,package:progress_payload->>source_package_id,job:pregenerated_structure->voice_cast->>job_id,script:pregenerated_script','limit':1})
            if len(rows)!=1:raise ValueError('주제의 원본 작업 연결을 확인하세요.')
            marker_match=rows[0].get('package')==p.get('source_package_id')
            source_match=rows[0].get('job')==identity and hashlib.sha256(str(rows[0].get('script','')).encode()).hexdigest()==p.get('source_script_sha256')
            if not (marker_match or source_match):raise ValueError('주제의 원본 작업 연결을 확인하세요.')
            with jobs.lock:
                b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate'])
                if j.get('worker_id')!=jobs.worker_id or j.get('published') or j.get('status') in ('running','queued','canceled','cancelled') or identity in jobs.inflight:raise ValueError('이 컴퓨터의 편집 가능한 작업을 선택하세요.')
                if digest(c)!=body.expected_hash:raise ValueError('저장 버전이 변경됐습니다. 다시 열어 주세요.')
                w=c['manual_workflow'];w['topic_registration']=copy.deepcopy(p);w['revision']=w.get('revision',0)+1;write(jobs.root/identity/'candidate.json',c)
                fields={'candidate_hash':digest(c),'manual_workflow':state_summary(w),'registered_topic_id':p['topic_id'],'stage':f'120컷 대본 · 유저웹 주제 #{p["topic_id"]} 등록 확인','updated_at':time.time()}
                if j.get('sync_status')=='pending':jobs.rows[identity].update(fields);write(jobs.root/identity/'job.json',jobs.rows[identity])
                else:jobs.update(identity,**fields)
                return {'saved':True,'topic_id':p['topic_id'],'sync_status':jobs.rows[identity].get('sync_status')}
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
