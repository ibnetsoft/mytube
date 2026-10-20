"""Inspect actual native-AE FK reference frames; no claim of Puppet parity."""
from pathlib import Path
import json, os, subprocess, hashlib
from PIL import Image, ImageDraw
import numpy as np

root=Path(__file__).resolve().parents[1];out=root/'output/motion-joint-comparison';ffmpeg=os.environ['MOTION_FFMPEG']
metrics=[]
for number in [25,29]:
 sheet=Image.new('RGB',(1920,1170),'#111111');draw=ImageDraw.Draw(sheet)
 for row,pose in enumerate(['shoulder','elbow','pelvis']):
  stem=f'scene-{number}-{pose}';video=out/'ae-rigid'/f'{stem}.mp4';ae=out/f'{stem}-ae-rigid.png'
  subprocess.run([ffmpeg,'-v','error','-y','-i',str(video),'-frames:v','1',str(ae)],check=True)
  images=[Image.open(out/f'{stem}-legacy.png').convert('RGB'),Image.open(ae).convert('RGB'),Image.open(out/f'{stem}-after.png').convert('RGB')]
  for col,(image,label) in enumerate(zip(images,['Previous fitted web rig','AE rigid cutout FK (same matrices)','Corrected web skin'])):
   sheet.paste(image.resize((640,360)),(col*640,row*390+30));draw.text((col*640+8,row*390+8),f'{pose}: {label}',fill='white')
  a,b=np.asarray(images[1]).astype(float),np.asarray(images[2]).astype(float)
  metrics.append({'scene':number,'pose':pose,'ae_video_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'rgb_mae':float(np.abs(a-b).mean()),'meaning':'Different skin solvers; compositor/reference difference, NOT a quality score'})
 sheet.save(out/f'ae-comparison-{number}.png')
(out/'ae-comparison-qa.json').write_text(json.dumps({'reference':'Actual AE native layer rotation/translation; dominant-weight cutout parts, matched global bone matrices and depth order','not_verified':'AE Puppet solver parity, hidden artwork, all poses, all PSDs','metrics':metrics},indent=2),encoding='utf-8')
print(json.dumps(metrics))
