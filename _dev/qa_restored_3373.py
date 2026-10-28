"""Inspect the completed restored render, without publishing it."""
import sys,json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import ae_highlight_worker as ae
from ae_media_utils import ffmpeg
import imageio_ffmpeg
from PIL import Image,ImageDraw
import numpy as np
DIR=ROOT/'output/project-recovery-e9233112'
receipt=json.loads((DIR/'restored-final-render-receipt.json').read_text(encoding='utf8'))
assert receipt['status']=='completed'
meta=receipt['metadata']
video=DIR/'restored-final-render.mp4'
if not video.exists():
 ae._download_gcs_file(ae.GcsRef(meta['gcs_bucket'],meta['gcs_path']),video)
config_path=DIR/'restored-final-render-config.json'
cfg=meta['gcs_config']
if not config_path.exists():
 ae._download_gcs_file(ae.GcsRef(cfg['bucket'],cfg['path']),config_path)
config=json.loads(config_path.read_text(encoding='utf8'))
assert len(config['subtitles'])==714
assert all(len([r for r in config['subtitles'] if r['scene_number']==n])==7 for n in [37,38])
expected=2053.4073469387763
frames=imageio_ffmpeg.read_frames(str(video));info=next(frames);frames.close()
assert info['audio_codec']=='aac' and abs(info['duration']-expected)<.5,info
assert info['size']==(1920,1080),info
audio=ROOT/'output/codex-local-console/ae-mouth/db93c4ef790211c53236f3ea8ca1655add9ff30e2156bb2af4dce8c98ebf5241/final-narration.mp3'
def decode(path,start,duration):
 r=subprocess.run([ffmpeg(),'-v','error','-ss',str(start),'-i',str(path),'-t',str(duration),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'],capture_output=True,timeout=60)
 assert r.returncode==0,r.stderr[-1000:]
 return np.frombuffer(r.stdout,dtype='<i2').astype(float)
numbers=[1,37,38,45,62,100]
sheet=Image.new('RGB',(1280,len(numbers)//2*390),'#181818');draw=ImageDraw.Draw(sheet)
checks=[]
for i,number in enumerate(numbers):
 rows=[r for r in config['subtitles'] if r['scene_number']==number]
 assert rows
 start=rows[0]['start'];duration=min(12,rows[-1]['end']-start)
 a,b=decode(audio,start,duration),decode(video,start,duration)
 n=min(len(a),len(b));a,b=a[:n],b[:n]
 corr=float(np.corrcoef(a,b)[0,1]);gain=float(np.linalg.norm(b)/np.linalg.norm(a))
 # Final template mixing may change gain; compare waveform identity and timing.
 assert corr>.80,(number,corr,gain)
 checks.append({'scene':number,'start':start,'duration':duration,'audio_correlation':corr,'mix_gain':gain})
 sample=start+min(2,duration/2);target=DIR/f'restored-final-scene-{number}.jpg'
 r=subprocess.run([ffmpeg(),'-v','error','-ss',str(sample),'-i',str(video),'-frames:v','1','-y',str(target)],capture_output=True,timeout=30)
 assert r.returncode==0,r.stderr
 im=Image.open(target).convert('RGB');im.thumbnail((640,360));x=(i%2)*640;y=(i//2)*390;sheet.paste(im,(x,y+30));draw.text((x+10,y+7),f'Scene {number} / {sample:.2f}s',fill='white')
sheet.save(DIR/'restored-final-contact.jpg',quality=92)
audit={'queue_id':receipt['id'],'video':str(video),'bytes':video.stat().st_size,'video_sha256':hashlib.file_digest(video.open('rb'),'sha256').hexdigest(),'info':info,'subtitles':714,'audio_samples':checks,'publishing_performed':False}
(DIR/'restored-final-qa.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(audit,ensure_ascii=False,default=str),flush=True)
