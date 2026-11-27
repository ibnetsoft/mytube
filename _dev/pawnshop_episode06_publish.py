"""Crop reviewed native grids and CAS-publish each scene; never invent missing output."""
import copy,hashlib,json,sys,time,argparse
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.cowork_scene_assets import _topic,_upload_gcs_file,_download_gcs_bytes,_upscale_panel,_publish_source_snapshot,_scene_asset_snapshot,_scene_asset_patch,_patch_topic_scene_assets
from worker.content_identity import content_hash,speech_text,visual_hash
parser=argparse.ArgumentParser();parser.add_argument('--episode',required=True,choices=['06']);args=parser.parse_args()
OUT=ROOT/('output/pawnshop-series/episode-'+args.episode)/'image-production';RAW=OUT/'raw';IMAGES=OUT/'scenes';IMAGES.mkdir(parents=True,exist_ok=True)
INITIAL=json.loads((OUT/'source-topic.json').read_text());JOB=str(INITIAL.get('progress_payload',{}).get('source_script_job_id') or INITIAL.get('progress_payload',{}).get('local_script_job_id') or 'pawnshop-'+str(INITIAL['id']))
SCRIPT_SHA=hashlib.sha256(INITIAL['pregenerated_script'].encode()).hexdigest()
SCENE_COUNT=len(INITIAL['pregenerated_structure']['scenes'])
GRID_COUNT=(SCENE_COUNT+3)//4
def save(name,data):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(data,ensure_ascii=False,indent=2));t.replace(p)
def status(stage,**kw):save('scene-production-status.json',{'stage':stage,'updated_at':time.time(),**kw})
def main():
 status('waiting for registered topic and reviewed image grids')
 topic_id=str(INITIAL['id']);done={}
 while len(done)<GRID_COUNT:
  for grid in range(1,GRID_COUNT+1):
   if grid in done:continue
   receipt=OUT/f'grid-{grid:03d}-publication.json'
   if receipt.exists():done[grid]=json.loads(receipt.read_text());continue
   raw=RAW/f'grid-{grid:03d}.png';review=RAW/f'grid-{grid:03d}-review.json'
   if not raw.exists() or not review.exists():continue
   qa=json.loads(review.read_text());raw=Path(qa.get('source_file') or raw);assert qa.get('visual_inspected') is True
   assert qa['sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
   row,structure,base,headers=_topic(topic_id)
   assert hashlib.sha256(row['pregenerated_script'].encode()).hexdigest()==SCRIPT_SHA
   assert row.get('status') not in ('canceled','cancelled','submitted','review_requested','paid'), 'Topic ownership or submission changed'
   numbers=list(range((grid-1)*4+1,min(grid*4,SCENE_COUNT)+1));by={int(s.get('scene_number') or s.get('scene_order')):s for s in structure['scenes']}
   status('cropping and uploading',topic_id=topic_id,grid=grid,completed_grids=len(done),published_scenes=len(done)*4)
   with Image.open(raw) as source:
    source.load();w,h=source.size;boxes=[(0,0,w//2,h//2),(w//2,0,w,h//2),(0,h//2,w//2,h),(w//2,h//2,w,h)]
    for n,box in zip(numbers,boxes):
     file=IMAGES/f'scene-{n:03d}.png';pixels=_upscale_panel(source.crop(box),1920,1080)
     if file.exists():
      with Image.open(file) as old:assert old.convert('RGB').tobytes()==pixels.convert('RGB').tobytes()
     else:pixels.save(file)
   updates=[];assets=[]
   for n in numbers:
    file=IMAGES/f'scene-{n:03d}.png';sha=hashlib.sha256(file.read_bytes()).hexdigest();b,k,url=_upload_gcs_file(file,f'topics/{topic_id}/images/scene-{n:03d}-{sha}.png','image/png')
    assert hashlib.sha256(_download_gcs_bytes(b,k)).hexdigest()==sha
    scene=by[n];assert not scene.get('image_url') or scene['image_url']==url, 'Concurrent image must be preserved';source_snapshot=_publish_source_snapshot(scene,n);old_assets=_scene_asset_snapshot(scene);changed=copy.deepcopy(scene)
    changed.update(image_url=url,asset_status='ready');changed.setdefault('metadata',{})['cowork_image_asset']={'source':'cowork_builtin_imagegen','storage_provider':'gcs','gcs_bucket':b,'gcs_path':k,'bucket':b,'object_path':k,'width':1920,'height':1080,'sha256':sha,'generation_job_id':JOB,'source_grid_sha256':qa['sha256'],'visual_review':qa,'origin_content_identity':{'schema_version':1,'origin_topic_queue_id':int(topic_id),'script_sha256':content_hash(speech_text(row['pregenerated_script'])),'generation_job_id':JOB,'scene_number':n,'visual_sha256':visual_hash(scene,'image')}}
    updates.append({'scene_number':n,'expected_source':source_snapshot,'expected_assets':old_assets,'asset_patch':_scene_asset_patch(changed)})
    assets.append({'scene_number':n,'sha256':sha,'url':url,'bucket':b,'path':k,'storage_readback_verified':True})
   result=_patch_topic_scene_assets(topic_id,updates,base,headers)
   _,verified,_,_=_topic(topic_id)
   for asset in assets:assert next(x for x in verified['scenes'] if int(x.get('scene_number') or x.get('scene_order'))==asset['scene_number'])['image_url']==asset['url']
   data={'grid':grid,'topic_id':topic_id,'scenes':assets,'rpc_result':result,'database_readback_verified':True,'completed_at':time.time()}
   receipt.write_text(json.dumps(data,ensure_ascii=False,indent=2));done[grid]=data
   status('scene images in progress',topic_id=topic_id,completed_grids=len(done),published_scenes=len(done)*4)
  if len(done)<GRID_COUNT:time.sleep(15)
 save('scene-image-publication.json',{'topic_id':topic_id,'scene_count':SCENE_COUNT,'grids':list(done.values()),'all_storage_and_database_readbacks_verified':True})
 status('all basic scene images published',topic_id=topic_id,published_scenes=SCENE_COUNT,ae_layers_generated=False,tts_generated=False,render_completed=False)
if __name__=='__main__':
 for attempt in range(1000):
  try:
   main();break
  except Exception as exc:
   status('execution recovery queued',error_type=type(exc).__name__,retry=attempt+1)
   (OUT/'last-publication-error.txt').write_text(str(exc))
   if isinstance(exc,AssertionError):raise
   time.sleep(min(60,10*(attempt+1)))
