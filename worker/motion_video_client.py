"""Selected-model video calls through the server vault; provider keys never reach jobs or logs."""
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
import requests


def generated_insert(job,token,scene,plan,preview,directory,headers,save,fresh):
    import ae_highlight_worker as ae
    from motion_automation_worker import NeedsReview,digest,save_json
    output=directory/'generated-insert.mp4';receipt=directory/'generated-insert.json'
    identity=hashlib.sha256(json.dumps(plan['ai'],sort_keys=True).encode()).hexdigest()
    if output.exists() and receipt.exists():
        saved=json.loads(receipt.read_text())
        if saved.get('identity')==identity and saved.get('sha256')==digest(output):return output
    fresh();number=str(scene['number']);source_hash=digest(preview)
    bucket,path,_=ae._upload_gcs_file(preview,f'std-motion/{job["id"]}/sources/{number}-{source_hash}.png','image/png')
    meta=save()
    save(ai_sources={**meta.get('ai_sources',{}),number:{'bucket':bucket,'path':path,'sha256':source_hash}})
    origin=os.getenv('AIR_STUDIO_WEB_URL','https://studio.airing.work').rstrip('/')
    endpoint=origin+'/api/worker/motion-video'
    deadline=time.monotonic()+2700
    while time.monotonic()<deadline:
        fresh()
        response=requests.post(endpoint,headers=headers,json={'job_id':job['id'],'worker_token':token,'scene_number':scene['number'],'action':'create'},timeout=(10,45),allow_redirects=False)
        data=response.json()
        if data.get('state')=='retry_before_create':time.sleep(1);continue
        if not response.ok:raise NeedsReview(str(data.get('error') or 'Video provider connection failed')[:1800])
        if data.get('state')=='complete':
            url=data['url'];parsed=urlparse(url)
            if parsed.scheme!='https' or parsed.username or parsed.password or not any(parsed.hostname==h or parsed.hostname.endswith('.'+h) for h in ('fal.media','replicate.delivery')):raise NeedsReview('Invalid generated video download host')
            temporary=output.with_suffix('.download')
            size=0
            with requests.get(url,stream=True,timeout=(10,60),allow_redirects=False) as download:
                download.raise_for_status()
                with temporary.open('wb') as target:
                    for block in download.iter_content(1024*1024):
                        fresh();size+=len(block)
                        if size>100*1024*1024:raise NeedsReview('Generated insert exceeds download limit')
                        target.write(block)
            temporary.replace(output)
            save_json(receipt,{'identity':identity,'sha256':digest(output)})
            return output
        time.sleep(10)
    raise NeedsReview('영상 제공자가 아직 처리 중입니다. 기존 작업 ID를 유지하며 새 생성 요청은 보내지 않습니다.')
