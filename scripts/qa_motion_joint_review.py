from pathlib import Path
import json, os, subprocess, hashlib, sys
import numpy as np
from PIL import Image, ImageDraw

root=Path(__file__).resolve().parents[1]
out=root/'output/motion-joint-comparison'
ffmpeg=os.environ['MOTION_FFMPEG']
accepted='--accepted' in sys.argv
numbers=[25,29] if accepted else [19,25,29]
video=out/('joint-review-accepted.mp4' if accepted else 'joint-review.mp4')
run=lambda args:subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y',*args],capture_output=True,check=True)
run(['-i',str(video),'-f','null','-'])
audio=lambda p:np.frombuffer(run(['-i',str(p),'-map','0:a:0','-ac','1','-ar','16000','-f','f32le','-']).stdout,dtype='<f4')
expected=audio(out/'accepted-narration.wav' if accepted else root/'output/motion-fullbody-validation/joined-recording.wav');actual=audio(video)
n=min(len(expected),len(actual));corr=float(np.corrcoef(expected[:n],actual[:n])[0,1])
assert corr>.999,'Audio mismatch'
lags=range(-160,161,16)
def score(lag):
 a=expected[max(0,-lag):min(len(expected),len(actual)-lag)]
 b=actual[max(0,lag):max(0,lag)+len(a)]
 return float(np.corrcoef(a,b)[0,1])
lag=max(lags,key=score)
rows=json.loads((root/'output/motion-longform-validation/source-manifest.json').read_text(encoding='utf-8'))['rows']
sheet=Image.new('RGB',(1920,1170),'#111111');draw=ImageDraw.Draw(sheet);cursor=0;samples=[]
for si,number in enumerate(numbers):
 row=next(r for r in rows if r['number']==number);duration=row['end']-row['start']
 for j,name in enumerate(['shoulder','elbow','pelvis']):
  t=cursor+(j+.5)*duration/3;p=out/f'encoded-{number}-{name}.png'
  run(['-ss',str(t),'-i',str(video),'-frames:v','1',str(p)])
  image=Image.open(p).convert('RGB');a=np.asarray(image)
  assert a.std()>10,'Blank frame'
  sheet.paste(image.resize((640,360)),(j*640,si*390+30));draw.text((j*640+8,si*390+8),f'Scene {number}: {name}',fill='white')
  samples.append({'scene':number,'pose':name,'time':t,'file':p.name})
 cursor+=duration
sheet.save(out/('encoded-accepted.png' if accepted else 'encoded-review.png'))
receipt={'full_decode_passed':True,'audio_correlation':corr,'audio_lag_ms':lag/16,'audio_padding_ms':(len(actual)-len(expected))/16,'samples':samples,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'scope':'Source footage and finalized recording excerpts; no publishing'}
(out/('accepted-qa.json' if accepted else 'review-qa.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))
