from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np, json, hashlib
D=Path(r'output/codex-local-console/ae-mouth/bc4c29de2593671d4e9a852c3a6ff4985deb2298d5658314466a17ab3d2c94a5/scene-34/speaker-0')
ref=Image.open(D/'mouth-reference.png').convert('RGB'); a=np.array(ref); h,w=a.shape[:2]
def cleaned():
 b=a.copy(); y0,y1=5,min(h-4,24)
 top=a[max(0,y0-2)].astype(float); bot=a[min(h-1,y1+2)].astype(float)
 for y in range(y0,y1+1):
  t=(y-y0+1)/(y1-y0+2); b[y]=((1-t)*top+t*bot).astype(np.uint8)
 return Image.fromarray(b).resize((w*4,h*4),Image.Resampling.BICUBIC)
def save_pose(name):
 if name=='closed': im=ref.resize((w*4,h*4),Image.Resampling.BICUBIC)
 else:
  im=cleaned(); d=ImageDraw.Draw(im)
  cx=w*2; cy=13*4
  if name=='half':
   d.ellipse((cx-31*4,cy-3*4,cx+31*4,cy+4*4),fill=(81,39,29),outline=(56,28,23),width=2*4)
   d.arc((cx-29*4,cy-1*4,cx+29*4,cy+5*4),0,180,fill=(194,105,85),width=1*4)
  else:
   d.ellipse((cx-34*4,cy-6*4,cx+34*4,cy+8*4),fill=(55,25,24),outline=(49,25,22),width=2*4)
   d.arc((cx-25*4,cy+1*4,cx+25*4,cy+9*4),180,360,fill=(178,83,78),width=2*4)
 im=im.resize((w,h),Image.Resampling.LANCZOS).convert('RGBA'); im.putalpha(255); im.save(D/(name+'.png'))
for p in ('closed','half','open'):save_pose(p)
for p in ('closed','half','open'):
 rp=D/(p+'.receipt.json'); r=json.load(open(rp,encoding='utf-8'));r['sha256']=hashlib.sha256((D/(p+'.png')).read_bytes()).hexdigest();rp.write_text(json.dumps(r),encoding='utf-8')
print(w,h)
