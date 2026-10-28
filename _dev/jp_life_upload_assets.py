"""Crop visually accepted grids and upload immutable, byte-verified GCS assets."""
import hashlib,json,sys,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from worker.cowork_scene_assets import crop_grids,_upload_gcs_file,_download_gcs_bytes
OUT=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package'
GRIDS=OUT/'scene-grids';CROPS=OUT/'images';CROPS.mkdir(exist_ok=True)
PREFIX='topics/local-6ae46b7afca84070b36e9e13d7de0a6e'
def read(name,default):
 p=OUT/name
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def save(name,value):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
def upload(path,kind,key):
 data=path.read_bytes();sha=hashlib.sha256(data).hexdigest();object_path=f'{PREFIX}/{kind}/{key}-{sha[:20]}.png'
 bucket,gcs_path,url=_upload_gcs_file(path,object_path,'image/png')
 assert hashlib.sha256(_download_gcs_bytes(bucket,gcs_path)).hexdigest()==sha,'Uploaded bytes differ'
 return {'image_url':url,'gcs_bucket':bucket,'gcs_path':gcs_path,'storage_bucket':bucket,'storage_object_path':gcs_path,'sha256':sha,'local_file':str(path),'verified':True}
def main():
 refs=read('character-references.json',[]);old=read('uploaded-characters.json',[]);bykey={c['character_key']:c for c in old}
 for c in refs:
  key=c['character_key']
  if key not in bykey:
   bykey[key]={**c,**upload(Path(c['local_image_path']),'characters',key),'image_generation_status':'ready','generation_model':'codex_builtin_image_gen'}
   save('uploaded-characters.json',list(bykey.values()));print('character verified',key,flush=True)
 known=read('uploaded-scenes.json',[]);by_scene={r['scene_number']:r for r in known};manifest=json.loads((GRIDS/'manifest.json').read_text(encoding='utf-8'))
 while len(by_scene)<136:
  for g in manifest['grids']:
   nums=g['scene_numbers']
   if all(n in by_scene for n in nums):continue
   receipt=GRIDS/f"grid-{g['grid_number']:03d}.review.json"
   if not receipt.exists():continue
   review=json.loads(receipt.read_text(encoding='utf-8'));raw=GRIDS/g['raw_file']
   assert review['visual_review']=='pass' and review['scene_numbers']==nums
   assert review['sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
   part=GRIDS/f"crop-{g['grid_number']:03d}.json";part.write_text(json.dumps({'schema':'cowork_scene_assets/v1','topic_id':'local-6ae46b7','grids':[g]}),encoding='utf-8')
   crop_grids(part,GRIDS,CROPS)
   missing=[n for n in nums if n not in by_scene]
   def process(n):return {'scene_number':n,**upload(CROPS/f'scene-{n:03d}.png','images',f'scene-{n:03d}'),'width':1920,'height':1080}
   with ThreadPoolExecutor(max_workers=3) as pool:
    for item in pool.map(process,missing):by_scene[item['scene_number']]=item
   save('uploaded-scenes.json',sorted(by_scene.values(),key=lambda x:x['scene_number']));print('scenes verified',len(by_scene),flush=True)
  save('upload-status.json',{'stage':'uploading_scenes','characters':len(bykey),'scenes':len(by_scene),'total_scenes':136})
  if len(by_scene)<136:time.sleep(10)
 save('upload-status.json',{'stage':'scenes_complete','characters':len(bykey),'scenes':len(by_scene),'total_scenes':136})
if __name__=='__main__':
 try:main()
 except Exception as exc:
  save('upload-status.json',{'stage':'failed','error_type':type(exc).__name__,'error':str(exc)[:400]});traceback.print_exc();raise
