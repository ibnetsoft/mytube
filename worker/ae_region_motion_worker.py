"""Standalone web region-motion queue. Windows backend only, no installer changes."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
import worker_config
import ae_highlight_worker as ae
from ae_media_utils import ref
from ae_region_motion import render, validate_input


def timeline(project, number):
    rows=[]
    for i,r in enumerate((project.get('project_payload') or {}).get('subtitles',[])):
        if int(r.get('scene_number') or 0)!=number:continue
        a=float(r.get('start_num',r.get('start_time',r.get('start',0))));b=float(r.get('end_num',r.get('end_time',r.get('end',0))))
        if b>a:rows.append({'id':str(r.get('id') or f'index-{i}'),'text':str(r.get('text') or ''),'start':a,'end':b})
    start=min((r['start'] for r in rows),default=0)
    return {'duration':max((r['end'] for r in rows),default=0)-start,'subtitles':[{**r,'start':r['start']-start,'end':r['end']-start} for r in rows]}


def process_one():
    base,headers=ae._supabase();url=base+'/rest/v1/std_project_assets'
    jobs=ae._request('GET',url,headers,params={'select':'*','metadata->>kind':'eq.region_motion_plan','metadata->>state':'in.(queued,processing)','order':'created_at.asc','limit':'20'}).json()
    job=next((j for j in jobs if j['metadata']['state']=='queued' or (datetime.now(timezone.utc)-datetime.fromisoformat(j['updated_at'].replace('Z','+00:00'))).total_seconds()>1800),None)
    if not job:return False
    meta=copy.deepcopy(job['metadata']);lease=uuid.uuid4().hex
    meta.update(state='processing',lease=lease,error=None,progress='원본 확인')
    claimed=ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},json={'metadata':meta,'updated_at':ae._now()}).json()
    if not claimed:return False
    stop=threading.Event()
    def save(**changes):
        meta.update(changes)
        ae._request('PATCH',url,headers,params={'id':'eq.'+job['id'],'metadata->>lease':'eq.'+lease},json={'metadata':meta,'updated_at':ae._now()})
    def heartbeat():
        while not stop.wait(20):
            try:ae._request('PATCH',url,headers,params={'id':'eq.'+job['id'],'metadata->>lease':'eq.'+lease},json={'updated_at':ae._now()})
            except Exception:pass
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    def current():
        projects=ae._request('GET',base+'/rest/v1/std_projects',headers,params={'select':'*','id':'eq.'+job['project_id']}).json()
        assets=ae._request('GET',url,headers,params={'select':'*','project_id':'eq.'+job['project_id'],'status':'in.(uploaded,assigned)','order':'created_at.desc'}).json()
        image=next((a for a in assets if a.get('asset_type')=='image' and a.get('scene_number')==meta['input']['number']),None)
        latest=next((a for a in assets if (a.get('metadata') or {}).get('kind')=='region_motion_plan' and a.get('scene_number')==meta['input']['number']),None)
        if not projects or projects[0].get('status')=='canceled' or not image or image['id']!=meta['input']['image']['id'] or not latest or latest['id']!=job['id'] or timeline(projects[0],meta['input']['number'])!=meta['input']['timeline']:
            raise ValueError('설정·원본·자막 시간이 변경됐습니다. 다시 렌더링해 주세요.')
    try:
        validate_input(meta['input']);current()
        directory=worker_config.TEMP_DIR/'region-motion'/job['id'];directory.mkdir(parents=True,exist_ok=True)
        source=directory/'source.png';bucket,path=ref(meta['input']['image']);ae._download_gcs_file(ae.GcsRef(bucket,path),source)
        save(progress='영역 분리와 배경 보정')
        output=render(source,directory,meta['input'])
        current()
        # Detect replacement bytes even if the storage path and asset ID stayed the same.
        check=directory/'source-current.png';ae._download_gcs_file(ae.GcsRef(bucket,path),check)
        if hashlib.sha256(check.read_bytes()).hexdigest()!=meta['input']['imageSha256']:raise ValueError('원본 이미지가 변경됐습니다.')
        save(progress='AE 결과 저장')
        out_bucket,out_path,media_url=ae._upload_gcs_file(output,f"std-region-motion/{job['project_id']}/{job['id']}.mp4",'video/mp4')
        current()
        save(state='ready',progress='결과 확인 가능',result={'gcs_bucket':out_bucket,'gcs_path':out_path,'video_url':media_url,'duration_seconds':meta['input']['timeline']['duration'],'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    except Exception as error:
        save(state='failed',error=str(error)[:1200],progress='확인 필요')
        print('Region motion failed:',job['id'],str(error),flush=True)
    finally:stop.set();thread.join(timeout=1)
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    lock=worker_config.STATE_DIR/'region_motion_worker.lock'
    with lock.open('a+b') as file:
        import msvcrt
        file.seek(0);msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        print('Region motion worker ready',flush=True)
        while True:
            try:process_one()
            except Exception as error:print('Region motion poll:',type(error).__name__,flush=True)
            if args.once:break
            time.sleep(5)
if __name__=='__main__':main()
