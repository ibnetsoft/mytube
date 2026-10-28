import hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from PIL import Image,ImageDraw
import cv2
from ae_media_utils import ffmpeg,run
from worker_config import TEMP_DIR
BASE=ROOT/'output/codex-local-console/two-topic-mouths'
all_results=[]
for topic in [3376,3377]:
 folder=BASE/str(topic);qa=folder/'qa';qa.mkdir(exist_ok=True);faces=[];results=[]
 for receipt in sorted(folder.glob('scene-*-speaker-coordinates.json')):
  data=json.loads(receipt.read_text(encoding='utf8'));preview=data.get('mouth_preview') or {}
  if preview.get('state')!='ready':continue
  n=data['number'];target=qa/f'scene-{n:03d}.mp4';expected=preview['sha256']
  if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
   candidates=[folder/f'scene-{n:03d}-preserve-original-1080p.mp4',folder/f'scene-{n:03d}-preserve-original.mp4']+list((TEMP_DIR/'ae_highlight').glob(f'{topic}-{n:03d}-motion-*/render/ae_highlight.mp4'))
   found=next((p for p in candidates if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==expected),None)
   if not found:raise ValueError(f'No matching rendered video for {topic}/{n}')
   shutil.copy2(found,target)
  run([ffmpeg(),'-v','error','-i',str(target),'-map','0:v:0','-f','null','NUL'])
  source=Image.open(folder/f'scene-{n:03d}.png').convert('RGB')
  cap=cv2.VideoCapture(str(target));fps=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));assert fps>0 and abs(count/fps-3)<.08
  assert (w,h)==(1920,1080)
  cap.set(cv2.CAP_PROP_POS_MSEC,400);ok,frame=cap.read();cap.release();assert ok
  actual=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));actual.save(qa/f'scene-{n:03d}-actual-open.png')
  for i,speaker in enumerate(data['speakers']):
   if not speaker.get('face_box'):continue
   rect=tuple(round(v*(w if j%2==0 else h)) for j,v in enumerate(speaker['face_box']));source_rect=tuple(round(v*(source.width if j%2==0 else source.height)) for j,v in enumerate(speaker['face_box']));faces.append((f'{n}-{i} '+('PRESERVED' if speaker.get('status')!='visible' else 'ANIMATED'),source.crop(source_rect),actual.crop(rect)))
  row={'topic':topic,'scene':n,'sha256':expected,'duration':count/fps,'width':w,'height':h,'frames':count,'fps':fps,'decoded':True,'preserve_original':bool(preview.get('preserve_original'))};results.append(row)
 if faces:
  sheet=Image.new('RGB',(1000,((len(faces)+1)//2)*290),'#222222');draw=ImageDraw.Draw(sheet)
  for i,(name,source,actual) in enumerate(faces):
   x=(i%2)*500;y=(i//2)*290;draw.text((x+4,y+4),f'{topic} #{name} SOURCE | ACTUAL VIDEO',fill='white')
   for offset,im in [(0,source),(250,actual)]:
    im.thumbnail((245,260));sheet.paste(im,(x+offset,y+25))
  sheet.save(qa/'actual-rendered-mouths.jpg')
 (qa/'technical-qa.json').write_text(json.dumps(results,indent=2),encoding='utf8');all_results.extend(results)
 print(json.dumps({'topic':topic,'clips_checked':len(results),'all_decoded':all(r['decoded'] for r in results)}),flush=True)
(BASE/'technical-qa.json').write_text(json.dumps(all_results,indent=2),encoding='utf8')
