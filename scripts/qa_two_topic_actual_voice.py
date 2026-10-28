import sys,json,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_media_utils import ffmpeg,run
from ae_mouth import digest,decode_scene_audio,amplitude_cues
from mouth_geometry import animatable
from worker_config import TEMP_DIR
from PIL import Image,ImageDraw
import cv2,numpy as np
base,headers=ae._supabase()
JOBS={3376:'0db3979f-cded-4f78-899d-687123bffb87',3377:'9159c849-ebbf-4d5a-8429-d25b397cca50'}
for topic,job_id in JOBS.items():
 job=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'id,project_id,metadata','id':'eq.'+job_id}).json()[0];meta=job['metadata'];snapshot=meta['input'];identity=meta['fingerprint']
 folder=ROOT/f'output/codex-local-console/two-topic-mouths/{topic}/final-voice';qa=folder/'qa';qa.mkdir(exist_ok=True)
 qa_file=qa/'actual-voice-qa.json';checked=json.loads(qa_file.read_text(encoding='utf8')) if qa_file.exists() else {}
 assets=ae._request('GET',base+'/rest/v1/std_project_assets',headers,params={'select':'id,scene_number,metadata','project_id':'eq.'+job['project_id'],'asset_type':'eq.video','status':'in.(uploaded,assigned)','metadata->>ae_mouth_fingerprint':'eq.'+identity}).json()
 master=ROOT/'output/codex-local-console/ae-mouth'/identity/'final-narration.mp3'
 for asset in assets:
  n=asset['scene_number'];m=asset['metadata'];old=checked.get(str(n));
  if old and old.get('review_version')==2 and old['sha256']==m['render_sha256']:continue
  scene=next(s for s in snapshot['scenes'] if s['number']==n);duration=scene['end']-scene['start']
  file=ROOT/'output/codex-local-console/ae-mouth'/identity/f'scene-{n}/ae-mouth-preview.mp4'
  if file.exists() and digest(file)!=m['render_sha256']:
   alternate=file.with_name('ae-mouth-web.mp4')
   if alternate.exists() and digest(alternate)==m['render_sha256']:file=alternate
  if m.get('preserve_original'):file=folder/f'scene-{n:03d}-actual-voice-preserved.mp4'
  assert file.exists() and digest(file)==m['render_sha256']
  assert m['voice_synced'] and m['timing_mode']=='final_voice' and m['source_audio_id']==snapshot['audio']['id']
  assert abs(m['duration_seconds']-duration)<.12
  quality=m.get('web_copy_ssim')
  if m.get('delivery_variant')=='web_cq20' and quality is None:
   candidates=[p for p in (TEMP_DIR/'ae_highlight').glob(f'{job["project_id"]}-{n:03d}-motion-*/render/ae_highlight.mp4') if p.exists()]
   assert len(candidates)==1,(topic,n,'ambiguous source render',len(candidates))
   result=subprocess.run([ffmpeg(),'-hide_banner','-i',str(candidates[0]),'-i',str(file),'-lavfi','ssim','-an','-f','null','NUL'],capture_output=True,text=True,check=True,timeout=120)
   quality=float(re.findall(r'All:([0-9.]+)',result.stderr)[-1])
  if quality is not None:assert quality>=.99,(topic,n,quality)
  run([ffmpeg(),'-v','error','-i',str(file),'-map','0:v:0','-map','0:a:0','-f','null','NUL'])
  actual_pcm=subprocess.run([ffmpeg(),'-v','error','-i',str(file),'-ac','1','-ar','8000','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=120).stdout
  expected=np.array(decode_scene_audio(ffmpeg(),master,scene['start'],duration),dtype=float)
  actual=np.frombuffer(actual_pcm,dtype='<i2').astype(float)
  assert len(actual)>=(duration-.12)*8000
  # AAC is lossy; require the same voice waveform, allowing at most 0.08 s encoder offset.
  correlations=[]
  for lag in range(-640,641,8):
   l=max(0,lag);r=max(0,-lag);size=min(len(expected)-l,len(actual)-r)
   x=expected[l:l+size:4];y=actual[r:r+size:4]
   if size>8000 and x.std()>0 and y.std()>0:correlations.append(float(np.corrcoef(x,y)[0,1]))
  correlation=max(correlations,default=0);assert correlation>.92,(topic,n,'voice mismatch',correlation)
  cap=cv2.VideoCapture(str(file));fps=cap.get(cv2.CAP_PROP_FPS);frames=cap.get(cv2.CAP_PROP_FRAME_COUNT);w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
  assert (w,h)==(1920,1080) and abs(frames/fps-duration)<.12
  source=Image.open(folder.parent/f'scene-{n:03d}.png').convert('RGB');faces=[]
  for i,s in enumerate(scene['speaker_regions']['speakers']):
   if not s.get('face_box'):continue
   animate=animatable(s,digest(folder.parent/f'scene-{n:03d}.png'))
   at=min(.4,duration/2)
   if animate:
    rows=[r for r in snapshot['subtitles'] if r['scene_number']==n and r['kind']=='dialogue' and r['speaker']==s['speaker']]
    cues=amplitude_cues(expected.tolist(),rows,start=scene['start'],duration=duration)
    at=next(c['at_seconds']+.001 for c in cues if c['pose']=='open')
   cap.set(cv2.CAP_PROP_POS_MSEC,at*1000);ok,frame=cap.read();assert ok
   actual_image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));rect=lambda width,height:tuple(round(v*(width if j%2==0 else height)) for j,v in enumerate(s['face_box']))
   source_file=qa/f'scene-{n}-{i}-source.png';actual_file=qa/f'scene-{n}-{i}-actual.png';source.crop(rect(source.width,source.height)).save(source_file);actual_image.crop(rect(w,h)).save(actual_file)
   faces.append({'label':f'{n}-{i} '+('ANIMATED' if animate else 'PRESERVED'),'source':str(source_file),'actual':str(actual_file),'at':at})
  cap.release();checked[str(n)]={'review_version':2,'asset_id':asset['id'],'sha256':m['render_sha256'],'duration':duration,'voice_correlation':correlation,'web_copy_ssim':quality,'decoded':True,'faces':faces}
  qa_file.write_text(json.dumps(checked,indent=2),encoding='utf8');print(json.dumps({'topic':topic,'scene':n,'checked':True,'voice_correlation':round(correlation,4)}),flush=True)
 all_faces=[f for n in sorted(checked,key=int) for f in checked[n]['faces']]
 if all_faces:
  sheet=Image.new('RGB',(1000,((len(all_faces)+1)//2)*290),'#222222');draw=ImageDraw.Draw(sheet)
  for i,f in enumerate(all_faces):
   x=i%2*500;y=i//2*290;draw.text((x+4,y+4),f'{topic} #{f["label"]} SOURCE | ACTUAL VOICE CLIP',fill='white')
   for offset,key in [(0,'source'),(250,'actual')]:
    image=Image.open(f[key]);image.thumbnail((245,260));sheet.paste(image,(x+offset,y+25))
  sheet.save(qa/'actual-voice-contact.jpg')
 print(json.dumps({'topic':topic,'published_voice_clips':len(assets),'checked':len(checked),'job_state':meta['state']}),flush=True)
