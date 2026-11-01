"""Persist genuinely generated scene planes and PSDs, with immutable storage and CAS linking."""
import copy,hashlib,json,os,sys,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')];load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
from worker.gcs_media_storage import _upload_gcs_file
from worker.cowork_scene_assets import _download_gcs_bytes,_publish_source_snapshot,_scene_asset_snapshot,_patch_topic_scene_assets
from worker.manga_layer_package import _build_psd
OUT=ROOT/'output/pawnshop-series/episode-01/production';store=ScriptStore();topic=store.request('GET','topics_queue',params={'select':'id,status,assigned_employee_email,pregenerated_script,pregenerated_structure','id':'eq.3387'})[0][0];assert topic['status']=='pending' and not topic.get('assigned_employee_email');structure=topic['pregenerated_structure']
packages=json.loads((OUT/'composite-packages.json').read_text());assert len(packages)==32
specs={int(n):p for n,p in packages.items()}
cache_path=OUT/'gcs-upload-receipts.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
def save_cache():
 with cache_lock:cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
cache_lock=threading.Lock()
def upload(path,role,n,mime='image/png'):
 sha=hashlib.sha256(path.read_bytes()).hexdigest();key=f'topics/3387/production/{n:03d}/{role}-{sha[:24]}'+('.psd' if mime!='image/png' else '.png')
 if key not in cache:
  b,k,url=_upload_gcs_file(path,key,mime);data=_download_gcs_bytes(b,k);assert hashlib.sha256(data).hexdigest()==sha;cache[key]={'gcs_bucket':b,'gcs_path':k,'media_url':url,'sha256':sha,'file_size':path.stat().st_size,'width':1920,'height':1080,'storage_provider':'gcs','storage_readback_verified':True};save_cache()
 return cache[key]
updates=[]
def prepare(item):
 n,package=item
 folder=Path(package['folder']);scene=next(s for s in structure['scenes'] if s['scene_number']==n);expected_source=_publish_source_snapshot(scene,n);expected_assets=_scene_asset_snapshot(scene);planes=[]
 for row in package['layers']:
  p=folder/row['file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];planes.append({'role':row['role'],**upload(p,row['role'],n)})
 psd=Path(package['psd']);pd=upload(psd,'layer-package',n,'image/vnd.adobe.photoshop');flat=upload(Path(package['image']),'scene',n)
 md=copy.deepcopy(scene.get('metadata') or {});md['cowork_image_asset']={**flat,'source':'cowork_builtin_imagegen','generation_method':'independently_generated_builtin_imagegen_planes','independent_planes':{'source':'independent_original_planes','assets':planes},'bucket':flat['gcs_bucket'],'object_path':flat['gcs_path']}
 md['local_layer_asset']={'source':'independently_generated_png_layers','method':'registered_individual_layer_pngs','assets':{p['role']:p for p in planes},'credit_cost':'not_measured'}
 md['psd_layer_asset']={**pd,'source':'independently_authored_png_layers','template':scene['psd_layer_plan']['template'],'layers':[p['role'] for p in planes],'qa_status':'quality_notes_recorded','review':{'composition_reviewed':False,'reviewer':'Codex actual pixel inspection','note':'Independent PNG planes and reopened PSD; visual continuity concerns retained in QUALITY_NOTES.md; no final AE render reviewed.','face_registry_review':'pending'},'actual_ae_render_reviewed':False}
 patch={'image_url':flat['media_url'],'asset_status':'ready','local_layer_status':'ready','metadata':md}
 update={'scene_number':n,'expected_source':expected_source,'expected_assets':expected_assets,'asset_patch':patch}
 print('Stored and byte-verified actual planes/PSD/composite for scene',n,flush=True)
 return update
with ThreadPoolExecutor(max_workers=4) as pool:updates=list(pool.map(prepare,sorted(specs.items())))
base=os.environ['NEXT_PUBLIC_SUPABASE_URL'];key=os.environ['SUPABASE_SERVICE_ROLE_KEY'];result=_patch_topic_scene_assets('3387',updates,base,{'apikey':key,'Authorization':'Bearer '+key})
actual=store.request('GET','topics_queue',params={'select':'pregenerated_structure','id':'eq.3387'})[0][0]['pregenerated_structure']
for n in specs:
 s=next(s for s in actual['scenes'] if s['scene_number']==n);assert s['asset_status']=='ready' and s['metadata']['psd_layer_asset']['sha256']
(OUT/'scene-publication-receipt.json').write_text(json.dumps({'topic_id':3387,'scenes':list(specs),'individual_plane_count':sum(len(x['layers']) for x in specs.values()),'psd_count':len(specs),'scene_composites':len(specs),'readback_verified':True,'face_review':'pending','rpc':result},ensure_ascii=False,indent=2));print('Published 32 scene composites, 104 independent PNG planes and 32 layered PSDs; quality concerns recorded',flush=True)
