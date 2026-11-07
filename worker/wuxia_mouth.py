"""Only reviewed large, unobstructed speaking mouths; zero selected mouths is valid."""
from pathlib import Path
import math
from PIL import Image
from ambient_loop import digest
CONTRACT='wuxia_dialogue_mouth/v1'
POSES=('closed','half','open')

def prepare(source,mouths,directory,fresh,download,audio):
 if not mouths:return []
 if not isinstance(mouths,list) or len(mouths)>4:raise ValueError('Invalid selected mouth count')
 with Image.open(source) as image:size=image.size
 source_hash=digest(source);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);result=[]
 def rect(r):return isinstance(r,list) and len(r)==4 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in r) and r[0]<r[2] and r[1]<r[3]
 for m in mouths:
  face=m.get('face_box');box=m.get('mouth_box');review=m.get('review') or {}
  if (m.get('contract')!=CONTRACT or m.get('source_sha256')!=source_hash or (m.get('width'),m.get('height'))!=size
   or not audio or m.get('audio_asset_id')!=audio.get('id') or m.get('audio_sha256')!=(audio.get('metadata') or {}).get('sha256')
   or not rect(face) or not rect(box) or face[3]-face[1]<.20 or box[2]-box[0]<.014
   or any(box[i]<face[i] if i<2 else box[i]>face[i] for i in range(4))
   or review.get('mouth_fully_visible') is not True or review.get('face_large_enough') is not True or review.get('occluded') is not False or review.get('identity_preserved') is not True):
   raise ValueError('Selected mouth source, recording or visual conditions changed')
  pixel=(round(box[0]*size[0]),round(box[1]*size[1]),round(box[2]*size[0]),round(box[3]*size[1]));files={}
  for pose in POSES:
   fresh();f=m['poses'][pose];sha=f['sha256']
   if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid mouth frame checksum')
   path=directory/(sha+'.png')
   if not path.exists() or digest(path)!=sha:download(f,path)
   if digest(path)!=sha:raise ValueError('Mouth frame checksum mismatch')
   with Image.open(path) as patch:
    if patch.format!='PNG' or getattr(patch,'n_frames',1)!=1 or patch.mode!='RGBA' or patch.size!=size:raise ValueError('Mouth patch canvas mismatch')
    bounds=patch.getchannel('A').getbbox()
    if not bounds or bounds[0]<pixel[0] or bounds[1]<pixel[1] or bounds[2]>pixel[2] or bounds[3]>pixel[3]:raise ValueError('Mouth pixels escaped their reviewed box')
   files[pose]=str(path.resolve())
  result.append({**m,'files':files})
 return result
