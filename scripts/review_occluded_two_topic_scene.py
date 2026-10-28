import copy,dataclasses,json,math,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'worker'),str(ROOT)]
import prepare_two_topic_mouth_previews as pipeline
from PIL import Image,ImageDraw
from datetime import datetime,timezone
from ae_mouth import digest,visible_speakers
from mouth_geometry import validate
from worker_config import OUTPUT_DIR
for number in [23,24,25]:
 folder=pipeline.BASE/'3377';receipt=folder/f'scene-{number:03d}-speaker-coordinates.json';saved=json.loads(receipt.read_text(encoding='utf8'))
 files=sorted((OUTPUT_DIR/'codex_stage_requests').glob('*'+saved['fingerprint']+'*crop_localization*.response.json'),key=lambda p:p.stat().st_mtime,reverse=True)
 if not files:raise ValueError('No actual crop assessment available')
 raw=files[0];context_file=raw.with_name(raw.name.split('.attempt-')[0]+'.input.json');context=json.loads(context_file.read_text(encoding='utf8'));row=json.loads(raw.read_text(encoding='utf8'));g=row['mouth_geometry'];source=folder/f'scene-{number:03d}.png'
 if g.get('mouth_visibility') not in ('partial','hidden'):raise ValueError('Only explicitly observed occlusion may preserve original in this repair')
 with Image.open(source) as original:
  w,h=original.size;l,t,r,b=context['crop_rect_pixels']
  def mapped(p):return [(l+p[0]*(r-l))/w,(t+p[1]*(b-t))/h]
  box=row['face_box'];row['face_box']=mapped(box[:2])+mapped(box[2:]);g['face_outline']=[mapped(p) for p in g.get('face_outline',[])];g.update(source_sha256=digest(source),render_policy='preserve_original',landmarks={});g.pop('review',None);row.update(status='occluded',mouth_box=None)
  validate(row,digest(source),require_review=False)
  directory=folder/f'scene-{number:03d}-occlusion-review';directory.mkdir(exist_ok=True)
  rect=[round(v*(w if i%2==0 else h)) for i,v in enumerate(row['face_box'])];crop=original.crop(rect);plain=directory/'original.png';crop.save(plain);marked=crop.convert('RGB');draw=ImageDraw.Draw(marked);draw.rectangle((1,1,marked.width-2,marked.height-2),outline='lime',width=2);draw.text((3,3),'PRESERVE ORIGINAL',fill='yellow');annotated=directory/'annotated.png';marked.save(annotated)
 runner=pipeline.EvidenceRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
 result=runner._stage('occlusion-3377-'+str(number)+'-'+uuid.uuid4().hex,'03_ae_mouth_geometry_review',{'_local_image_paths':[str(source.resolve()),str(plain.resolve()),str(annotated.resolve())],'speaker':row,'source_sha256':digest(source)},'Inspect the actual original and enlarged face. Determine whether the identified gray-haired Genzo has a partially/fully covered mouth because of his moustache or pose. This proposal adds NO mouth overlay and preserves every original pixel. Independently verify character identity, orientation, pitch and partial/hidden mouth assessment. Do NOT infer hidden lip points. Return {speakers:[{speaker:exact_name,passed:true|false,confidence:0..1,reason:visual_evidence}]}. Confidence is in identity/visibility assessment, not guessed lip anatomy. Reject if identity/occlusion is uncertain.')
 pipeline.write(directory/'review.json',result);check=result.get('speakers',[{}])[0]
 if check.get('speaker')!=row['speaker'] or check.get('passed') is not True or not isinstance(check.get('confidence'),(int,float)) or check['confidence']<.9:raise ValueError(str(check))
 row['previous_localization_confidence']=row['confidence'];row['confidence']=check['confidence'];g['review']={'passed':True,'reason':check['reason'],'proof':'annotated-face-crop-v4'};visible_speakers({'speakers':[row]},[row['speaker']]);validate(row,digest(source))
 saved.update(state='ready',speakers=[row],updated_at=datetime.now(timezone.utc).isoformat());saved.pop('error',None);pipeline.write(receipt,saved);print(json.dumps({'topic':3377,'scene':number,'state':'ready','policy':'preserve_original','reason':check['reason']},ensure_ascii=False),flush=True)
