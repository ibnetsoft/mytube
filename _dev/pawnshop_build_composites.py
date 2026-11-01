"""Immutable normalization and PSD packaging of selected independently generated planes."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from worker.manga_layer_generation import _normalize
from worker.layered_scene_composite import composite_scene
from worker.manga_layer_package import _build_psd
OUT=ROOT/'output/pawnshop-series/episode-01/production';selected=json.loads((OUT/'selected-planes.json').read_text());result={}
for number,rows in selected.items():
 n=int(number);folder=OUT/'packages'/f'{n:03d}';folder.mkdir(parents=True,exist_ok=True);layers=[]
 for row in rows:
  source=Path(row['source']);sha=hashlib.sha256(source.read_bytes()).hexdigest();role=row['role'];target=folder/(role+'-'+sha[:16]+'.png')
  if not target.exists():
   if source.name=='024-foreground-paper-registered.png':
    # A correctly scaled distant sheet occupies less than generic cutout 1% coverage.
    # Validate actual alpha pixels while retaining its authored canvas registration.
    with Image.open(source) as im:
     assert im.mode=='RGBA' and im.getchannel('A').getextrema()==(0,255)
     hist=im.getchannel('A').histogram();assert hist[0]>im.width*im.height*.5 and sum(hist[180:])>1000
     ImageOps.fit(im,(1920,1080),method=Image.Resampling.LANCZOS).save(target)
   else:_normalize(source,target,'background' if role=='background' else 'character' if 'character' in role else 'foreground')
  layers.append({'role':role,'file':target.name,'source':str(source),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
 fingerprint=hashlib.sha256(json.dumps(layers,sort_keys=True).encode()).hexdigest();image=folder/('scene-'+fingerprint[:16]+'.png');psd=folder/('scene-'+fingerprint[:16]+'.psd');preview=folder/('psd-preview-'+fingerprint[:16]+'.png')
 if not image.exists():composite_scene(folder/layers[0]['file'],[folder/x['file'] for x in layers[1:]],image)
 if not psd.exists():_build_psd(folder,layers,psd,preview)
 result[number]={'scene_number':n,'fingerprint':fingerprint,'folder':str(folder),'layers':layers,'image':str(image),'psd':str(psd),'psd_preview':str(preview),'visual_review':'pending'}
 print(n,image,flush=True)
(OUT/'composite-packages.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
