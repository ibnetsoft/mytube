"""Render the full authorized project using the reviewed AE scenes and saved narration."""
from pathlib import Path
import os, sys, json, time, base64, shutil, uuid
from urllib.parse import quote, urlencode
from concurrent.futures import ThreadPoolExecutor
import requests
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'worker'))
sys.path.insert(0, str(ROOT))
import worker_config
from google.oauth2 import service_account
RUN = Path(os.environ.get('AIR_FINAL_RUN', str(ROOT/'_dev/artifacts/final_3373_ae_v2')))
RUN.mkdir(parents=True, exist_ok=True)
creds = service_account.Credentials.from_service_account_info({'type':'service_account','private_key':os.environ['GCS_PRIVATE_KEY'].replace('\\n','\n'),'client_email':os.environ['GCS_CLIENT_EMAIL'],'token_uri':'https://oauth2.googleapis.com/token','project_id':os.environ.get('GCS_PROJECT_ID','air-studio-prod')})
def signed(bucket, path, method='GET', mime=''):
    resource=quote('/'+bucket+'/'+path,safe='/'); expires=str(int(time.time())+604800)
    sig=base64.b64encode(creds.sign_bytes((method+'\n\n'+mime+'\n'+expires+'\n'+resource).encode())).decode()
    return 'https://storage.googleapis.com'+resource+'?'+urlencode({'GoogleAccessId':creds.service_account_email,'Expires':expires,'Signature':sig})
def download(entry):
    dst=RUN/entry['path']; dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() and dst.stat().st_size>0:return
    for attempt in range(3):
        try:
            r=requests.get(signed(entry['gcs_bucket'],entry['gcs_path']),timeout=(15,90));r.raise_for_status();dst.write_bytes(r.content);return
        except Exception:
            if attempt==2:raise
    
def main():
    cfg=json.loads((ROOT/'_dev/artifacts/ae_3373_review/render_config.json').read_text(encoding='utf-8'))
    assets=json.loads((ROOT/'_dev/artifacts/ae_3373_review/audio_assets.json').read_text(encoding='utf-8'))
    timeline=next(a for a in assets if '1791071804136' in a['file_name'])['metadata']['subtitle_timeline']
    assert len(timeline)==len(cfg['subtitles']) and all(a['text']==b['text'] for a,b in zip(timeline,cfg['subtitles']))
    oldsubs=cfg['subtitles']; points={0.0:0.0}
    for old,new in zip(oldsubs,timeline):
        points[float(old['start'])]=float(new['start']);points[float(old['end'])]=float(new['end'])
    xp=sorted(points);yp=[points[x] for x in xp]
    assert all(b>=a for a,b in zip(yp,yp[1:])), 'Nonmonotonic audio timing'
    scenes=json.loads((ROOT/'_dev/artifacts/current_ae_project.json').read_text(encoding='utf-8'))['project_payload']['structure']['scenes']
    # Some visual scenes have no independent subtitle. Place their boundary
    # between surrounding spoken scene anchors, avoiding zero-length shots.
    anchors={0:0.0}
    for old,new in zip(oldsubs,timeline):
        index=int(old['scene_number'])-1
        if index not in anchors:anchors[index]=float(new['start'])
    anchors[101]=float(timeline[-1]['end'])
    indices=sorted(anchors)
    starts=[float(np.interp(i,indices,[anchors[x] for x in indices])) for i in range(101)]
    assert len(starts)==101 and all(b>a for a,b in zip(starts,starts[1:])), 'Invalid scene boundaries'
    for old,new in zip(oldsubs,timeline):old.update(start=new['start'],end=new['end'])
    cfg.update(worker_tts=None,image_timing_starts=starts,render_version=2)
    pending=[]
    for e in cfg['asset_manifest']['files']:
        n=e.get('scene_number',0)
        if 1<=n<=25:
            name=f'scene_{n:03d}.mp4';cfg['images'][n-1]=name
            dst=RUN/'images'/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/f'_dev/artifacts/ae_3373_run/v1/scene_{n:02d}.mp4',dst)
        else:pending.append(e)
    print('Downloading render inputs',len(pending),flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(download,pending))
    import imageio_ffmpeg
    from services.ffmpeg_slideshow_service import _media_duration
    info={'duration':_media_duration(imageio_ffmpeg.get_ffmpeg_exe(),str(RUN/'audio'/cfg['audio_filename']))}
    cfg['audio_duration']=info['duration']
    assert abs(info['duration']-timeline[-1]['end'])<1, 'Narration duration mismatch'
    (RUN/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    (RUN/'timing_qa.json').write_text(json.dumps({'audio_duration':info['duration'],'subtitle_count':len(timeline),'scene_starts':starts,'method':'recorded subtitle scene anchors; interpolate visual-only scenes between spoken anchors'},indent=2),encoding='utf-8')
    print('Rendering full 101 scenes',info['duration'],flush=True)
    from services.remote_render_service import remote_render_executor_func
    remote_render_executor_func('3373-ae-v2',str(RUN),use_gpu=True)
    out=RUN/'output.mp4';gen=imageio_ffmpeg.read_frames(str(out));result=next(gen);gen.close()
    assert abs(result['duration']-info['duration'])<2 and result['size']==(1920,1080)
    assert result.get('audio_codec'), 'Final video must contain narration audio'
    (RUN/'final_qa.json').write_text(json.dumps(result,default=str,indent=2),encoding='utf-8')
    print('FINAL_RENDER_COMPLETE',str(out),out.stat().st_size,flush=True)
if __name__=='__main__':main()
