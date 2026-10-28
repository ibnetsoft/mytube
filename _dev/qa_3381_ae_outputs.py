import sys,json,hashlib,subprocess,math
from pathlib import Path
sys.path[:0]=['worker']
import ae_highlight_worker as ae
from ae_media_utils import ffmpeg
from PIL import Image,ImageDraw,ImageFont
import cv2, numpy as np
P='6b46f709-b4bf-4ccd-ac12-9c8c3981e249';J='8a5880c3-ce87-41e6-8478-6fadb38b6540'
ROOT=Path(__file__).resolve().parents[1]
JOBDIR=ROOT/'output/codex-local-console/ae-mouth/bc4c29de2593671d4e9a852c3a6ff4985deb2298d5658314466a17ab3d2c94a5'
OUT=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package/ae-mouth-final-qa';OUT.mkdir(parents=True,exist_ok=True)
b,h=ae._supabase();u=b+'/rest/v1/std_project_assets'
job=ae._request('GET',u,h,params={'select':'*','id':'eq.'+J}).json()[0]; meta=job['metadata']; scenes={s['number']:s for s in meta['input']['scenes']}
assets={a['id']:a for a in ae._request('GET',u,h,params={'select':'*','project_id':'eq.'+P,'asset_type':'eq.video'}).json()}
receipts=[]; thumbs=[]
for res in sorted(meta['results'],key=lambda x:x['number']):
 assert res['status']=='review_pending',res
 n=res['number']; local=JOBDIR/f'scene-{n}'/'ae-mouth-preview.mp4'; assert local.exists(),local
 local_sha=hashlib.sha256(local.read_bytes()).hexdigest(); assert local_sha==res['render_sha256']
 asset=assets[res['asset_id']]; am=asset['metadata']; remote=OUT/f'scene-{n}-gcs.mp4'; ae._download_gcs_file(ae.GcsRef(am['gcs_bucket'],am['gcs_path']),remote)
 remote_sha=hashlib.sha256(remote.read_bytes()).hexdigest(); assert remote_sha==local_sha
 cap=cv2.VideoCapture(str(local)); fps=cap.get(cv2.CAP_PROP_FPS); frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); duration=frames/fps
 assert frames>0 and abs(duration-res['duration'])<.15,(n,duration,res['duration'])
 # Read every frame to catch decode errors.
 decoded=0
 while True:
  ok,_=cap.read()
  if not ok:break
  decoded+=1
 cap.release(); assert decoded==frames,(n,decoded,frames)
 # Confirm decodable audio and non-silent scene slice.
 pcm=subprocess.run([ffmpeg(),'-v','error','-i',str(local),'-map','0:a:0','-ac','1','-ar','8000','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=120).stdout
 vals=np.frombuffer(pcm,dtype='<i2').astype(np.float64); rms=float(np.sqrt(np.mean(vals*vals))); assert len(vals)>=int((duration-.15)*8000) and rms>20,(n,len(vals),rms)
 cues=[]
 for v in res.get('visibility',[]):
  active=[float(c['at_seconds']) for c in v.get('cues',[]) if c.get('pose')!='closed']
  if active:cues.append(sum(active)/len(active))
 times=[0.25,*cues,max(.25,duration-.25)]
 for idx,t in enumerate(times):
  cap=cv2.VideoCapture(str(local));cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,fr=cap.read();cap.release();assert ok
  fr=cv2.cvtColor(fr,cv2.COLOR_BGR2RGB); im=Image.fromarray(fr).resize((480,270),Image.Resampling.LANCZOS)
  d=ImageDraw.Draw(im);d.rectangle((0,0,200,25),fill=(0,0,0,180));d.text((6,5),f'Scene {n}  {t:.2f}s',fill='white')
  thumbs.append((n,t,im))
 receipts.append({'scene':n,'asset_id':res['asset_id'],'duration_expected':res['duration'],'duration_decoded':duration,'fps':fps,'frames':frames,'decoded_frames':decoded,'audio_samples_8k':len(vals),'audio_rms':round(rms,2),'local_sha256':local_sha,'gcs_sha256':remote_sha,'gcs_bucket':am['gcs_bucket'],'gcs_path':am['gcs_path'],'sample_times':times})
# two sheets, preserve all samples (dual speakers add a column)
for page,start in enumerate(range(0,len(thumbs),15),1):
 batch=thumbs[start:start+15]; sheet=Image.new('RGB',(1440,math.ceil(len(batch)/3)*270),(25,25,25))
 for i,(_,_,im) in enumerate(batch):sheet.paste(im,((i%3)*480,(i//3)*270))
 sheet.save(OUT/f'contact-sheet-{page}.jpg',quality=94)
(OUT/'qa-receipt.json').write_text(json.dumps({'project_id':P,'job_id':J,'passed':True,'checks':['all_frames_decoded','duration_within_0.15s','audio_stream_decoded_non_silent','local_sha_matches_job','gcs_sha_matches_local','visual_sample_contact_sheets'],'scenes':receipts},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':True,'scenes':[(r['scene'],r['frames'],r['duration_decoded'],r['audio_rms']) for r in receipts],'sheets':len(list(OUT.glob('contact-sheet-*.jpg')))},ensure_ascii=False))

