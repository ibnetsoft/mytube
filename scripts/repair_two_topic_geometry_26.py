import copy,dataclasses,json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'worker'),str(ROOT)]
import prepare_two_topic_mouth_previews as pipeline
from PIL import Image,ImageDraw
from datetime import datetime,timezone
from ae_mouth import digest
from mouth_geometry import validate,validate_image_evidence
from worker_config import OUTPUT_DIR
TOPIC=3377;NUMBER=26
folder=pipeline.BASE/str(TOPIC);receipt=folder/f'scene-{NUMBER:03d}-speaker-coordinates.json';saved=json.loads(receipt.read_text(encoding='utf8'))
files=sorted((OUTPUT_DIR/'codex_stage_requests').glob('*'+saved['fingerprint']+'*geometry_review*.input.json'),key=lambda p:p.stat().st_mtime,reverse=True)
context=json.loads(files[0].read_text(encoding='utf8'));speakers=copy.deepcopy(context['speakers']);source=folder/f'scene-{NUMBER:03d}.png'
with Image.open(source) as original:
 width,height=original.size
 target=next(s for s in speakers if s['speaker']=='佐平');box=target['face_box'];rect=[round(v*(width if i%2==0 else height)) for i,v in enumerate(box)]
 target['mouth_geometry']['landmarks']['chin']=[(rect[0]+124)/width,(rect[1]+222)/height]
 target['mouth_geometry']['evidence']+=' Corrected chin against the actual lower jaw contour at x124,y222 of the unmarked face crop; do not use the left neck point.'
 directory=folder/'scene-026-corrected-evidence';directory.mkdir(exist_ok=True)
 attachments=[str(source.resolve())]
 for i,row in enumerate(speakers):
  g=row['mouth_geometry'];g.pop('review',None);validate(row,digest(source),require_review=False)
  if g['render_policy']=='animate':validate_image_evidence(row,original)
  box=row['face_box'];rect=[round(v*(width if j%2==0 else height)) for j,v in enumerate(box)];crop=original.crop(rect);plain=directory/f'original-{i}.png';crop.save(plain);attachments.append(str(plain.resolve()))
  marked=crop.convert('RGB');draw=ImageDraw.Draw(marked);mb=row['mouth_box'];draw.rectangle([mb[0]*width-rect[0],mb[1]*height-rect[1],mb[2]*width-rect[0],mb[3]*height-rect[1]],outline='lime',width=2)
  for name,point in g['landmarks'].items():
   x,y=point[0]*width-rect[0],point[1]*height-rect[1];draw.ellipse([x-2,y-2,x+2,y+2],fill='red');draw.text((x+3,y+3),name,fill='yellow')
  out=directory/f'annotated-{i}.png';marked.save(out);attachments.append(str(out.resolve()))
runner=pipeline.EvidenceRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
review=runner._stage('corrected-source-3377-26-'+uuid.uuid4().hex,'03_ae_mouth_geometry_review',{'_local_image_paths':attachments,'source_sha256':digest(source),'speakers':speakers},'Independently inspect the ORIGINAL and paired unmarked/ANNOTATED face crops. Verify red lip endpoints/center and nose/chin markers against real ink contours, green mouth patches, head direction and occlusion. The previous Sahai chin point was left of the chin on the neck and has been moved onto the actual lower jaw contour. Reject if still wrong; do not rubber stamp. Return {speakers:[{speaker:exact_name,passed:true|false,reason:visual_evidence}]} in supplied order.')
pipeline.write(directory/'review.json',review)
if len(review.get('speakers',[]))!=len(speakers):raise ValueError('Incomplete geometry review')
for row,result in zip(speakers,review['speakers']):
 if result.get('speaker')!=row['speaker'] or result.get('passed') is not True:raise ValueError(str(result))
 row['mouth_geometry']['review']={'passed':True,'reason':result['reason'],'proof':'annotated-face-crop-v4'}
 validate(row,digest(source))
saved.update(state='ready',speakers=speakers,updated_at=datetime.now(timezone.utc).isoformat());saved.pop('error',None);pipeline.write(receipt,saved)
print(json.dumps({'topic':TOPIC,'scene':NUMBER,'state':'ready','corrected':'actual chin contour; independently re-reviewed'}),flush=True)
