"""Register native generated lip pixels to verified source corners; retain source elsewhere."""
from pathlib import Path
import sys,json,shutil,dataclasses
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'worker'),str(ROOT)]
import prepare_two_topic_mouth_previews as pipeline
from prepared_mouth_layers import ROOT as CACHE,cache_key,prepare_scene
from ae_mouth import digest,normalize_patch
from PIL import Image,ImageDraw,ImageFilter
import cv2,numpy as np

topic,number=map(int,sys.argv[1:3]);folder=pipeline.BASE/str(topic);image=folder/f'scene-{number:03d}.png';receipt=folder/f'scene-{number:03d}-speaker-coordinates.json';saved=json.loads(receipt.read_text(encoding='utf8'));directory=CACHE/cache_key(image,saved['speakers'][0]);backup=directory/'rejected-before-registration';backup.mkdir(exist_ok=True)
base=Image.open(directory/'mouth-reference.png').convert('RGB');w,h=base.size
for pose in ['closed','half','open']:
 for suffix in ['.png','.receipt.json']:
  p=directory/(pose+suffix)
  if not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
 provenance={'operation':'source-corner-registration-and-local-composite','source_sha256':digest(image),'pose':pose}
 if topic==3376:
  if pose=='closed':result=base.copy();provenance['art_origin']='original closed-mouth source pixels'
  else:
   filename='exec-2cb28dba-ebe8-4bae-8cff-087260875269.png' if pose=='open' else 'exec-f7cbbc79-0f9b-4a85-bc4b-a8439a38d433.png'
   raw=Path('C:/Users/kimse/.codex/generated_images/01a137e3-b1ae-78f3-8d3f-82c2ed2dae39')/filename
   shutil.copy2(raw,directory/f'native-{pose}-registration-source.png')
   art=Image.open(raw).convert('RGB').resize((1000,890))
   points=((512,367),(628,347)) if pose=='open' else ((512,367),(628,352))
   target=((7.8,13.6),(15.5,14.4));polygon=[(5.8,10.5),(16.7,11.2),(17,18.6),(14.3,20),(6.0,17.7)]
   provenance['art_origin']='native imagegen';provenance['native_file']=filename
 else:
  art=Image.open(backup/f'{pose}.png').convert('RGB')
  points={'closed':((12,5.7),(29,2.6)),'half':((12.8,7.4),(29.2,3.6)),'open':((11.5,6.9),(24.8,3.9))}[pose]
  target=((15.2,10.0),(30.1,6.0));polygon=[(12,7),(30.4,3.3),(33,8),(28,14),(13,15)]
  provenance['art_origin']='previous native imagegen pose; source outline restored outside lip ROI'
 if not (topic==3376 and pose=='closed'):
  a,b=np.array(points[0],float),np.array(points[1],float);c,d=np.array(target[0],float),np.array(target[1],float);u=b-a;v=d-c
  alpha=np.dot(u,v)/np.dot(u,u);beta=np.cross(u,v)/np.dot(u,u)
  linear=np.array([[alpha,-beta],[beta,alpha]]);translation=c-linear@a;matrix=np.column_stack([linear,translation])
  if topic==3376:
   # Retain both verified corners while differentiating the interior opening.
   factor=.48 if pose=='half' else 1.55
   slope=(target[1][1]-target[0][1])/(target[1][0]-target[0][0]);intercept=target[0][1]-slope*target[0][0]
   matrix[1]=factor*matrix[1]+(1-factor)*slope*matrix[0];matrix[1,2]+=(1-factor)*intercept
   provenance['opening_depth_factor']=factor
  # Render at 40x resolution so subpixel lip geometry is registered before antialiasing.
  scale=40;matrix*=scale
  aligned=cv2.warpAffine(np.array(art),matrix,(w*scale,h*scale),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
  mask=Image.new('L',(w*scale,h*scale));ImageDraw.Draw(mask).polygon([(round(x*scale),round(y*scale)) for x,y in polygon],fill=255);mask=mask.filter(ImageFilter.GaussianBlur(scale*.55))
  result=Image.composite(Image.fromarray(aligned),base.resize((w*scale,h*scale),Image.Resampling.LANCZOS),mask).resize((w,h),Image.Resampling.LANCZOS)
  provenance.update({'generated_lip_corners':points,'verified_source_lip_corners_in_patch':target,'source_retained_outside_lip_polygon':polygon})
 rawout=directory/f'registered-{pose}-opaque.png';result.resize((w*40,h*40),Image.Resampling.NEAREST).save(rawout)
 old=json.loads((backup/f'{pose}.receipt.json').read_text());normalize_patch(rawout,directory/f'{pose}.png',image,old['mouth_box']);old['sha256']=digest(directory/f'{pose}.png');pipeline.write(directory/f'{pose}.receipt.json',old);pipeline.write(directory/f'{pose}-registration.json',provenance)
class CropEvidenceRunner(pipeline.EvidenceRunner):
 def _stage(self,identity,name,context,task):
  if name=='03_ae_mouth_layer_qa' and topic==3376:
   paths=[]
   with Image.open(image) as original:
    face=saved['speakers'][0]['face_box'];rect=tuple(round(v*(original.width if i%2==0 else original.height)) for i,v in enumerate(face))
   for i,path in enumerate(context['_local_image_paths']):
    crop=Image.open(path).crop(rect);crop=crop.resize((crop.width*4,crop.height*4));out=directory/f'qa-face-{i}.png';crop.save(out);paths.append(str(out.resolve()))
   context={**context,'_local_image_paths':context['_local_image_paths']+paths}
   task+=' The final four attachments are 4x crops of the SAME source face in original/closed/half/open order. Inspect these actual pixels as well as full-scene composites to judge the tiny profile lip opening and contour. All rejection criteria remain required.'
  return super()._stage(identity,name,context,task)
runner=CropEvidenceRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
saved['mouth_preparation']=prepare_scene(image,saved,runner=runner);pipeline.write(receipt,saved)
print(json.dumps({'topic':topic,'scene':number,'images':saved['mouth_preparation']['state']}),flush=True)
