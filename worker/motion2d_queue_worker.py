"""Local, lease-backed 2D preview worker. Never submits or publishes projects."""
from __future__ import annotations
import argparse
import copy
import os
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from motion2d_saved_assets import prepare_and_render, ROLES, sha256
from worker.workflow_roles import PREPARATION, asset_query, belongs, assert_project
from worker.content_identity import speech_text, timeline_rows


def check_current(ae, base, headers, job, snapshot):
    projects=ae._request('GET',base+'/rest/v1/std_projects',headers,params={'select':'id,status,submitted_at,progress_payload,project_payload','id':'eq.'+job['project_id'],'limit':1}).json()
    project=projects[0] if projects else None
    assert_project(project,PREPARATION)
    scenes=ae._request('GET',base+'/rest/v1/std_project_scenes',headers,params={'select':'id,scene_number','project_id':'eq.'+job['project_id'],'order':'scene_number.asc','limit':1000}).json()
    if [{'id':s['id'],'scene_number':int(s['scene_number'])} for s in scenes]!=snapshot.get('scene_identity'):raise ValueError('씬 순서가 변경되었습니다.')
    payload=project.get('project_payload') or {};progress=project.get('progress_payload') or {}
    voice_id=snapshot['audio']['id']
    audio_url=str(payload.get('audio_url') or payload.get('tts_url') or '')
    url_id=(parse_qs(urlsplit(audio_url).query).get('assetId') or [None])[0]
    for recorded_id in (progress.get('tts_asset_id'),payload.get('subtitle_source_audio_id'),url_id):
        if recorded_id and str(recorded_id)!=str(voice_id):raise ValueError('확정 음성이 변경되었습니다.')
    if not progress.get('tts_asset_id') and not url_id:
        candidates=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'id,metadata','project_id':'eq.'+job['project_id'],'asset_type':'eq.audio','status':'in.(uploaded,assigned)','limit':100}).json()
        candidates=[a for a in candidates if (a.get('metadata') or {}).get('audio_role') not in ('bgm','sfx','background')]
        if len(candidates)!=1 or str(candidates[0]['id'])!=str(voice_id):raise ValueError('확정 음성이 변경되었습니다.')
    rows=timeline_rows(payload.get('subtitles') or [])
    recorded=timeline_rows((snapshot['audio'].get('metadata') or {}).get('subtitle_timeline') or [])
    if not rows or len(rows)!=len(recorded):raise ValueError('자막 또는 음성 시간표가 변경되었습니다.')
    audio_meta=snapshot['audio'].get('metadata') or {}
    speed=payload.get('tts_speed')
    if speed is None:speed=progress.get('tts_speed')
    if speed is not None and abs(float(speed)-float(audio_meta.get('tts_speed',0)))>.001:raise ValueError('확정 음성의 속도가 변경되었습니다.')
    voice_segments=audio_meta.get('voice_segments') or []
    for index,subtitle in enumerate(payload.get('subtitles') or []):
        if index<len(voice_segments) and str(subtitle.get('direction') or '')!=str(voice_segments[index].get('direction') or ''):raise ValueError('음성 연출이 변경되었습니다.')
    for a,b in zip(rows,recorded):
        if a['text']!=b['text'] or a['voice_id']!=b['voice_id'] or abs(a['start']-b['start'])>.12 or abs(a['end']-b['end'])>.12:raise ValueError('자막 또는 음성 시간표가 변경되었습니다.')
    script=payload.get('script')
    if script and speech_text(script)!=''.join(r['text'] for r in rows):raise ValueError('대본 내용이 변경되었습니다.')
    url=base+'/rest/v1/std_project_assets'; scene=snapshot['scene']
    expected=[snapshot['image'],snapshot['audio'],snapshot['background'],*snapshot['patches'].values()]
    ids=[str(a['id']) for a in expected]
    current=ae._request('GET',url,headers,params={'select':'id,project_id,scene_number,asset_type,status,metadata','project_id':'eq.'+job['project_id'],'id':'in.('+','.join(ids)+')','limit':len(ids)}).json()
    byid={str(a['id']):a for a in current}
    for old in expected:
        new=byid.get(str(old['id']))
        if not new or new.get('status') not in ('uploaded','assigned') or any(new.get(k)!=old.get(k) for k in ('project_id','scene_number','asset_type','metadata')):raise ValueError('렌더 원본 또는 저장 패치가 변경되었습니다.')
    latest=ae._request('GET',url,headers,params={'select':'id','project_id':'eq.'+job['project_id'],'scene_number':'eq.'+str(scene),'asset_type':'eq.image','status':'in.(uploaded,assigned)','order':'created_at.desc','limit':1}).json()
    if not latest or latest[0]['id']!=snapshot['image']['id']:raise ValueError('씬 이미지가 변경되었습니다.')
    for role in ROLES:
        latest=ae._request('GET',url,headers,params={'select':'id','project_id':'eq.'+job['project_id'],'scene_number':'eq.'+str(scene),'status':'in.(uploaded,assigned)','metadata->>kind':'eq.motion2d_patch','metadata->>role':'eq.'+role,'metadata->>imageId':'eq.'+snapshot['image']['id'],'metadata->>imageSha256':'eq.'+snapshot['image_sha256'],'order':'created_at.desc','limit':1}).json()
        if not latest or latest[0]['id']!=snapshot['patches'][role]['id']:raise ValueError('새 패치가 저장되었습니다. 다시 렌더링해 주세요.')


def process_one():
    import ae_highlight_worker as ae
    import worker_config
    from ae_scene_preparation import claimable_filter
    base,headers=ae._supabase();url=base+'/rest/v1/std_project_assets'
    jobs=ae._request('GET',url,headers,params=asset_query(PREPARATION,{'select':'*','metadata->>kind':'eq.motion2d_render','or':claimable_filter(),'order':'created_at.asc','limit':1})).json()
    if not jobs:return False
    job=jobs[0]
    if not belongs(job,PREPARATION):return False
    token=uuid.uuid4().hex;meta=copy.deepcopy(job['metadata']);stop=threading.Event();lost=threading.Event();guard=threading.Lock()
    claimed=ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},json={'metadata':{**meta,'state':'processing','worker_token':token,'heartbeat_at':ae._now()},'updated_at':ae._now()}).json()
    if not claimed:return False
    meta=claimed[0]['metadata']
    def save(**values):
        with guard:
            if lost.is_set():raise RuntimeError('2D render lease lost')
            updated={**meta,**values,'heartbeat_at':ae._now()}
            result=ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id'],'metadata->>worker_token':'eq.'+token},json={'metadata':updated,'updated_at':ae._now()}).json()
            if not result:lost.set();raise RuntimeError('2D render lease lost')
            meta.update(updated)
    def heartbeat():
        while not stop.wait(15):
            try:save()
            except Exception:lost.set();return
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        snapshot=meta['input'];check_current(ae,base,headers,job,snapshot)
        executable=os.getenv('AIR_MOTION2D_RHUBARB') or shutil.which('rhubarb') or 'D:/AIRStudio/Tools/Rhubarb/1.14.0/rhubarb.exe'
        if not Path(executable).is_file():raise RuntimeError('Rhubarb를 영문 경로에 설치하고 AIR_MOTION2D_RHUBARB를 설정해 주세요.')
        directory=worker_config.TEMP_DIR/'motion2d'/job['id']/token
        result=prepare_and_render(snapshot,directory,lambda b,k,p:ae._download_gcs_file(ae.GcsRef(b,k),p),executable)
        check_current(ae,base,headers,job,snapshot)
        if lost.is_set():raise RuntimeError('2D render lease lost')
        output=Path(result.pop('output'));checksum=sha256(output)
        import imageio_ffmpeg
        frames,duration=imageio_ffmpeg.count_frames_and_secs(str(output))
        if frames!=96 or abs(duration-4)>.05:raise ValueError('렌더 프레임 또는 길이가 올바르지 않습니다.')
        bucket,key,_=ae._upload_gcs_file(output,f"std-motion2d/{job['project_id']}/renders/{job['id']}/{token}.mp4",'video/mp4')
        check_current(ae,base,headers,job,snapshot)
        save(state='ready',error=None,result={**result,'gcs_bucket':bucket,'gcs_path':key,'sha256':checksum})
    except Exception as error:
        if not lost.is_set():save(state='failed',error=str(error)[:1000])
        print('2D motion preview failed:',job['id'],str(error),flush=True)
    finally:
        stop.set();thread.join(timeout=2)
    return True


if __name__=='__main__':
    from ae_mouth_runtime import instance_lock
    import worker_config
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    with instance_lock(worker_config.STATE_DIR/'motion2d_queue_worker.lock'):
        while True:
            worked=process_one()
            if args.once:break
            time.sleep(1 if worked else 10)
