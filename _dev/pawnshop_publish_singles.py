"""Link immutable, genuinely generated stills without claiming direction/render approval."""
import hashlib,json,os,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
from worker.gcs_media_storage import _upload_gcs_file
from worker.cowork_scene_assets import _download_gcs_bytes,_publish_source_snapshot,_scene_asset_snapshot,_patch_topic_scene_assets
OUT=ROOT/'output/pawnshop-series/episode-01/production'
store=ScriptStore()
topic=store.request('GET','topics_queue',params={'id':'eq.3387','select':'id,status,assigned_employee_email,pregenerated_structure'})[0][0]
assert topic['status']=='pending' and not topic.get('assigned_employee_email')
scenes=topic['pregenerated_structure']['scenes']
cache_path=OUT/'gcs-upload-receipts.json'
cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
updates=[];receipts=[]
for folder in sorted((OUT/'singles').iterdir()):
 records=[json.loads(p.read_text()) for p in folder.glob('*.json')]
 if not records:continue
 record=max(records,key=lambda x:x['generated_at']);n=int(folder.name)
 assert not 19<=n<=50
 path=Path(record['path']);sha=hashlib.sha256(path.read_bytes()).hexdigest()
 assert sha==record['sha256'] and record['generator']=='builtin_image_gen'
 key=f'topics/3387/production/{n:03d}/scene-{sha[:24]}.png'
 if key not in cache:
  bucket,obj,url=_upload_gcs_file(path,key,'image/png')
  assert hashlib.sha256(_download_gcs_bytes(bucket,obj)).hexdigest()==sha
  cache[key]={'gcs_bucket':bucket,'gcs_path':obj,'media_url':url,'sha256':sha,'width':record['width'],'height':record['height'],'file_size':path.stat().st_size,'storage_provider':'gcs','storage_readback_verified':True}
  cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
 asset={**cache[key],'source':'cowork_builtin_imagegen','generation_method':'one_individually_generated_scene_still','quality_review':'pending_final_continuity_review','actual_ae_render_reviewed':False}
 scene=next(s for s in scenes if s['scene_number']==n)
 if scene.get('metadata',{}).get('cowork_image_asset',{}).get('sha256')==sha:continue
 updates.append({'scene_number':n,'expected_source':_publish_source_snapshot(scene,n),'expected_assets':_scene_asset_snapshot(scene),'asset_patch':{'image_url':asset['media_url'],'asset_status':'ready','metadata':{'cowork_image_asset':asset}}})
 receipts.append({'scene_number':n,**asset});print('Stored and byte-verified scene',n,flush=True)
if updates:
 key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
 result=_patch_topic_scene_assets('3387',updates,os.environ['NEXT_PUBLIC_SUPABASE_URL'],{'apikey':key,'Authorization':'Bearer '+key})
 actual=store.request('GET','topics_queue',params={'id':'eq.3387','select':'pregenerated_structure'})[0][0]['pregenerated_structure']['scenes']
 for row in receipts:
  scene=next(s for s in actual if s['scene_number']==row['scene_number'])
  assert scene['metadata']['cowork_image_asset']['sha256']==row['sha256'] and scene['image_url']==row['media_url']
 (OUT/'single-publication-receipt.json').write_text(json.dumps({'topic_id':3387,'linked_scenes':receipts,'storage_and_db_readback_verified':True,'quality_review':'pending_final_continuity_review','rpc':result},ensure_ascii=False,indent=2))
 print('Linked and re-read',len(receipts),'actual stills; final continuity/render approval remains pending.',flush=True)
else:print('No new stills to link.',flush=True)
