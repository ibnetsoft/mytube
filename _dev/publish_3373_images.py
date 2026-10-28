import sys,json,copy,uuid,hashlib
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker'),str(ROOT/'_dev')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.codex_character_assets import CharacterAssetStore
from regenerate_3373_images import fixed,style
out=ROOT/'output/codex-local-console/image-repair-3373';backup=ROOT/'_dev/artifacts/image_repair_3373'
project_id='e9233112-f0d7-4b35-91bf-2f892844eb30';store=ScriptStore();gcs=CharacterAssetStore()
audit=json.loads((out/'audit.json').read_text(encoding='utf8'))['scenes'];before=json.loads((backup/'scenes.before.json').read_text(encoding='utf8'))
only=set(map(int,sys.argv[sys.argv.index('--only')+1].split(','))) if '--only' in sys.argv else {r['number'] for r in audit if r['regenerate']}
receipts=[]
def read(table,params):return store.request('GET',table,params={'select':'*',**params})[0]
def image_update(scene,n,url,path,bucket,prompt,new_hash,local_path):
 scene['image_prompt']=prompt
 if 'panel_prompt' in scene:scene['panel_prompt']=prompt
 if 'visual_prompt' in scene:scene['visual_prompt']=prompt
 scene['image_url']=url
 scene['characters_present']=next(x['visible_characters'] for x in audit if x['number']==n)
 scene['character_references']=[{'name':name,'reference_file':fixed[name][0],'continuity_instruction':fixed[name][1]} for name in scene['characters_present'] if name in fixed]
 scene['image_repair_revision']='3373-cast-hair-20261005'
 scene['metadata']=scene.get('metadata') or {}
 scene['metadata']['cowork_image_asset']={'source':'builtin_image_gen','storage_provider':'gcs','bucket':bucket,'gcs_bucket':bucket,'object_path':path,'gcs_path':path,'width':1920,'height':1080,'sha256':new_hash}
 for k in ['ae_motion_plan','ae_effect_plan']:
  if isinstance(scene.get(k),dict):
   scene[k]['local_source_path']=local_path;scene[k]['local_source_sha256']=new_hash
   scene[k]['source_revision']='3373-cast-hair-20261005'
 scene['ae_motion_status']='source_changed_requires_review'
 scene['ae_effect_status']='source_changed_requires_review'
 scene['asset_status']='ready'
 return scene

for row in audit:
 n=row['number']
 if n not in only:continue
 work=out/'generated'/f'scene-{n:03}'
 receipt=json.loads((work/'generation.json').read_text(encoding='utf8'))
 assert receipt.get('status')=='ready' and receipt.get('generator')=='builtin_image_gen'
 local=Path(receipt['path']);data=local.read_bytes();sha=hashlib.sha256(data).hexdigest();assert sha==receipt['sha256']
 scene=read('std_project_scenes',{'project_id':f'eq.{project_id}','scene_number':f'eq.{n}'})[0]
 original=next(x for x in before if x['scene_number']==n);assert scene['scene_text']==original['scene_text'],'Script edited during regeneration'
 existing=read('std_project_assets',{'project_id':f'eq.{project_id}','scene_number':f'eq.{n}','asset_type':'eq.image','status':'in.(assigned,uploaded)','order':'created_at.desc'})
 if existing and existing[0]['metadata'].get('image_repair_sha256')==sha:
  receipts.append({'number':n,'asset_id':existing[0]['id'],'sha256':sha,'already_published':True});continue
 original_assets=json.loads((backup/'assets.before.json').read_text(encoding='utf8'))
 expected=next(x for x in original_assets if x['scene_number']==n and x['asset_type']=='image' and x['status'] in ['assigned','uploaded'])
 assert existing and existing[0]['id']==expected['id'],'Newer image uploaded during regeneration'
 prompt=(work/'prompt.txt').read_text(encoding='utf8')
 bucket,path,url=gcs._upload_gcs_bytes(f'topics/3373/image-repair-20261005/scene-{n:03}-{sha}.png',data,'image/png')
 aid=str(uuid.uuid4());now=datetime.now(timezone.utc).isoformat()
 asset={'id':aid,'project_id':project_id,'scene_id':scene['id'],'scene_number':n,'asset_type':'image','file_name':f'scene_{n:03}_cast_hair_v2.png','mime_type':'image/png','file_size':len(data),'checksum':sha,'status':'assigned','metadata':{'storage_provider':'gcs','gcs_bucket':bucket,'gcs_path':path,'storage_bucket':bucket,'storage_path':path,'source':'builtin_image_gen','image_repair_sha256':sha,'image_repair_revision':'3373-cast-hair-20261005','replaces_asset_id':existing[0]['id'],'issues':row['issues']}}
 saved,_=store.request('POST','std_project_assets',body=asset,prefer='return=representation');assert len(saved)==1
 meta=image_update(copy.deepcopy(scene['metadata']),n,url,path,bucket,prompt,sha,str(local))
 patched,_=store.request('PATCH','std_project_scenes',params={'id':f"eq.{scene['id']}",'updated_at':f"eq.{scene['updated_at']}"},body={'image_prompt':prompt,'metadata':meta,'asset_status':'ready','updated_at':now},prefer='return=representation');assert len(patched)==1
 topic=read('topics_queue',{'id':'eq.3373'})[0];structure=copy.deepcopy(topic['pregenerated_structure'])
 ts=next(x for x in structure['scenes'] if int(x['scene_number'])==n);image_update(ts,n,url,path,bucket,prompt,sha,str(local))
 old_prompt=topic['pregenerated_structure']['scenes'][n-1]['image_prompt']
 patched,_=store.request('PATCH','topics_queue',params={'id':'eq.3373','created_at':f"eq.{topic['created_at']}",f'pregenerated_structure->scenes->{n-1}->>image_prompt':'eq.'+old_prompt},body={'pregenerated_structure':structure},prefer='return=representation');assert len(patched)==1
 project=read('std_projects',{'id':f'eq.{project_id}'})[0];payload=copy.deepcopy(project['project_payload']);progress=copy.deepcopy(project['progress_payload'])
 candidates=[payload.get('structure',{}),payload.get('pregenerated_structure',{}),payload]
 for c in candidates:
  for ps in c.get('scenes',[]):
   if int(ps.get('scene_number') or ps.get('scene_order') or 0)==n:image_update(ps,n,url,path,bucket,prompt,sha,str(local))
 progress['image_repair_revision']='3373-cast-hair-20261005';progress['image_repaired_scenes']=sorted(set([*progress.get('image_repaired_scenes',[]),n]));progress['ae_source_changed_scenes']=sorted(set([*progress.get('ae_source_changed_scenes',[]),n]));progress['rerender_draft']=True
 patched,_=store.request('PATCH','std_projects',params={'id':f'eq.{project_id}','updated_at':f"eq.{project['updated_at']}"},body={'project_payload':payload,'progress_payload':progress,'updated_at':now},prefer='return=representation');assert len(patched)==1
 for old in existing:
  updated,_=store.request('PATCH','std_project_assets',params={'id':f"eq.{old['id']}",'updated_at':f"eq.{old['updated_at']}"},body={'status':'replaced','metadata':{**old['metadata'],'replaced_by_asset_id':aid,'replacement_revision':'3373-cast-hair-20261005'}},prefer='return=representation');assert len(updated)==1
 receipts.append({'number':n,'asset_id':aid,'sha256':sha,'url':url,'path':str(local),'replaced_asset_id':existing[0]['id']})
 (backup/f'publish-{min(only)}-{max(only)}.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
 print('PUBLISHED',n,flush=True)
