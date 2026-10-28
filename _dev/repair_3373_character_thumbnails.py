import sys,json,copy,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.codex_character_assets import CharacterAssetStore
store=ScriptStore();gcs=CharacterAssetStore();pid='e9233112-f0d7-4b35-91bf-2f892844eb30';out=ROOT/'_dev/artifacts/image_repair_3373'
def read(t,p):return store.request('GET',t,params={'select':'*',**p})[0]
project=read('std_projects',{'id':f'eq.{pid}'})[0];topic=read('topics_queue',{'id':'eq.3373'})[0];refs=read('topic_character_assets',{'topic_queue_id':'eq.3373'})
(out/'thumbnail-repair.before.json').write_text(json.dumps({'project':project,'topic':topic,'references':refs},ensure_ascii=False,indent=2),encoding='utf8')
for name,key in [('仙太郎','sentaro'),('次郎','jiro')]:
 ref=next(c for c in refs if c['name']==name);data=(ROOT/f'output/codex-local-console/image-repair-3373/reference-{key}.png').read_bytes();sha=hashlib.sha256(data).hexdigest();bucket,path,url=gcs._upload_gcs_bytes(f'topics/3373/characters/repair-{key}-{sha}.png',data,'image/png')
 ref.update({'image_url':url,'storage_bucket':bucket,'storage_object_path':path});usage=copy.deepcopy(ref.get('usage_context') or {});usage.setdefault('character_design',{}).update({'image_url':url,'gcs_bucket':bucket,'gcs_path':path});ref['usage_context']=usage
 store.request('PATCH','topic_character_assets',params={'id':f"eq.{ref['id']}"},body={'image_url':url,'storage_bucket':bucket,'storage_object_path':path,'usage_context':usage},prefer='return=representation')
byname={c['name']:c for c in refs};changed=0
def fix(node):
 global changed
 if isinstance(node,list):
  for c in node:fix(c)
 elif isinstance(node,dict):
  ref=byname.get(node.get('name'))
  if ref and ('image_url' in node or 'character_key' in node):
   node.update({'image_url':ref['image_url'],'character_key':ref['character_key']});changed+=1
   if 'gcs_path' in node:node['gcs_path']=ref['storage_object_path']
   if 'gcs_bucket' in node:node['gcs_bucket']=ref['storage_bucket']
  for c in list(node.values()):fix(c)
payload=copy.deepcopy(project['project_payload']);progress=copy.deepcopy(project['progress_payload']);structure=copy.deepcopy(topic['pregenerated_structure'])
fix(payload);fix(progress);fix(structure)
saved,_=store.request('PATCH','std_projects',params={'id':f'eq.{pid}','updated_at':f"eq.{project['updated_at']}"},body={'project_payload':payload,'progress_payload':progress,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation');assert len(saved)==1
store.request('PATCH','topics_queue',params={'id':'eq.3373'},body={'pregenerated_structure':structure},prefer='return=representation')
(out/'thumbnail-repair.receipt.json').write_text(json.dumps({'restored_character_count':len(refs),'fixed_reference_objects':changed,'scene_images_unchanged':True},indent=2),encoding='utf8');print('RESTORED',len(refs),'characters',changed,'reference objects')
