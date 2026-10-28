import sys,json,copy,uuid,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker'),str(ROOT/'_dev')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.codex_character_assets import CharacterAssetStore
from regenerate_3373_images import fixed,style
from urllib.parse import quote
out=ROOT/'output/codex-local-console/image-repair-3373';backup=ROOT/'_dev/artifacts/image_repair_3373'
store=ScriptStore();gcs=CharacterAssetStore();project_id='e9233112-f0d7-4b35-91bf-2f892844eb30'
def read(table,params):return store.request('GET',table,params={'select':'*',**params})[0]
audit=json.loads((out/'audit.json').read_text(encoding='utf8'))['scenes'];selected=[r for r in audit if r['regenerate']]
assert (out/'root-visual-review.json').exists(),'Root visual review must finish first'
approved=json.loads((out/'root-visual-review.json').read_text(encoding='utf8'))
assert set(approved['approved_scenes'])=={r['number'] for r in selected},'Unreviewed regenerated images remain'
before_scenes=json.loads((backup/'scenes.before.json').read_text(encoding='utf8'))
live_scenes=read('std_project_scenes',{'project_id':f'eq.{project_id}','order':'scene_number.asc'})
live_assets=read('std_project_assets',{'project_id':f'eq.{project_id}','status':'in.(assigned,uploaded)','order':'created_at.desc'})
for s in live_scenes:assert s['scene_text']==next(x['scene_text'] for x in before_scenes if x['scene_number']==s['scene_number'])
snapshot={'project':read('std_projects',{'id':f'eq.{project_id}'})[0],'topic':read('topics_queue',{'id':'eq.3373'})[0],'scenes':live_scenes,'assets':live_assets}
(backup/'batch-publish.before.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')

def upload(row):
 n=row['number'];w=out/'generated'/f'scene-{n:03}';r=json.loads((w/'generation.json').read_text(encoding='utf8'));p=Path(r['path']);data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();assert sha==r['sha256']
 assert r['status']=='ready' and r['generator']=='builtin_image_gen','Unvalidated generation source'
 assert approved['hashes'][str(n)]==sha,'Reviewed image changed'
 existing=next(a for a in live_assets if a['scene_number']==n and a['asset_type']=='image')
 if existing['metadata'].get('image_repair_sha256')==sha:
  m=existing['metadata'];return {'number':n,'asset_id':existing['id'],'bucket':m['gcs_bucket'],'object_path':m['gcs_path'],'sha256':sha,'local_path':str(p),'existing':True,'previous_asset_id':m['replaces_asset_id']}
 original_assets=json.loads((backup/'assets.before.json').read_text(encoding='utf8'))
 expected=next(a for a in original_assets if a['scene_number']==n and a['asset_type']=='image' and a['status'] in ['assigned','uploaded'])
 assert existing['id']==expected['id'],f'Scene {n}: user uploaded another image'
 bucket,path,url=gcs._upload_gcs_bytes(f'topics/3373/image-repair-20261005/scene-{n:03}-{sha}.png',data,'image/png')
 return {'number':n,'asset_id':str(uuid.uuid4()),'bucket':bucket,'object_path':path,'sha256':sha,'local_path':str(p),'bytes':len(data),'url':url,'previous_asset_id':existing['id']}
with ThreadPoolExecutor(max_workers=5) as pool:media=list(pool.map(upload,selected))
(backup/'batch-upload.json').write_text(json.dumps(media,ensure_ascii=False,indent=2),encoding='utf8')
now=datetime.now(timezone.utc).isoformat();assets=[]
for m in media:
 if m.get('existing'):continue
 n=m['number'];s=next(x for x in live_scenes if x['scene_number']==n)
 assets.append({'id':m['asset_id'],'project_id':project_id,'scene_id':s['id'],'scene_number':n,'asset_type':'image','file_name':f'scene_{n:03}_cast_hair_v2.png','mime_type':'image/png','file_size':m['bytes'],'checksum':m['sha256'],'status':'assigned','metadata':{'storage_provider':'gcs','gcs_bucket':m['bucket'],'gcs_path':m['object_path'],'storage_bucket':m['bucket'],'storage_path':m['object_path'],'source':'builtin_image_gen','image_repair_sha256':m['sha256'],'image_repair_revision':'3373-cast-hair-20261005','replaces_asset_id':m['previous_asset_id'],'issues':next(r['issues'] for r in selected if r['number']==n)}})
if assets:
 saved,_=store.request('POST','std_project_assets',body=assets,prefer='return=representation');assert len(saved)==len(assets)

# Persist the previously missing brother identities using immutable crops from original scene39.
new_characters=[]
for name,key,cid,age,role in [('仙太郎','sentaro','sentaro',42,'本妻の長男。身代に執着する。'),('次郎','jiro','jiro',38,'本妻の次男。兄と共に父を追い詰める。')]:
 local=out/f'reference-{key}.png';data=local.read_bytes();sha=hashlib.sha256(data).hexdigest();bucket,path,url=gcs._upload_gcs_bytes(f'topics/3373/characters/repair-{key}-{sha}.png',data,'image/png')
 design={'id':cid,'name':name,'age':age,'age_group':'adult','gender':'male','role':role,'character_key':f'repair3373-{key}-20261005','image_url':url,'gcs_bucket':bucket,'gcs_path':path,'visual_dna_en':fixed[name][1],'hair_design_en':'Full black swept-back hair, unshaved scalp with unchanged forehead hairline, compact upright black topknot with pale tie; preserve exact scene39 crop in every applicable present-day scene. Explicit earlier flashbacks preserve period hairstyle with stated younger age.','wardrobe_en':'Muted maroon kimono and dark-brown haori, grey hakama' if key=='sentaro' else 'Muted ochre kimono and dark-olive haori, grey hakama','continuity_instruction':fixed[name][1],'source':'existing_scene39_reference_crop','scene_numbers':[r['number'] for r in audit if name in r['visible_characters']]}
 new_characters.append(design)
 record={'topic_queue_id':3373,'character_key':design['character_key'],'name':name,'role':role,'gender':'male','age_group':'adult','category':'日本昔話','image_style':'jidaigeki_cel','visual_dna_en':design['visual_dna_en'],'wardrobe_en':design['wardrobe_en'],'continuity_instruction':design['continuity_instruction'],'image_prompt':design['visual_dna_en'],'image_url':url,'storage_bucket':bucket,'storage_object_path':path,'source':'existing_scene39_reference_crop','generation_model':'existing_scene_reference_crop','usage_context':{'sha256':sha,'reference_scene_number':39,'character_design':design,'scope':'image_repair_19_onward'}}
 store.request('POST','topic_character_assets',params={'on_conflict':'topic_queue_id,character_key'},body=record,prefer='resolution=merge-duplicates,return=representation')

reference_designs={c["name"]:c for c in new_characters}
for c in json.loads((backup/"characters.before.json").read_text(encoding="utf8")):
 reference_designs[c["name"]]=c

def modify(scene,n,m):
 row=next(r for r in audit if r['number']==n);prompt=(out/'generated'/f'scene-{n:03}'/'prompt.txt').read_text(encoding='utf8')
 url=f"/api/std/assets/gcs-file?bucket={quote(m['bucket'],safe='')}&path={quote(m['object_path'],safe='')}"
 scene['image_prompt']=prompt
 for key in ['panel_prompt','visual_prompt']:
  if key in scene:scene[key]=prompt
 scene.update({'image_url':url,'characters_present':row['visible_characters'],'image_repair_revision':'3373-cast-hair-20261005','asset_status':'ready'})
 scene['character_reference_keys']=[{'仙太郎':'repair3373-sentaro-20261005','次郎':'repair3373-jiro-20261005'}.get(name,name) for name in row['visible_characters']]
 scene['character_references']=[{'name':name,'character_key':reference_designs[name]['character_key'],'image_url':reference_designs[name]['image_url']} for name in row['visible_characters'] if name in reference_designs]
 nested=scene.setdefault('metadata',{});nested['cowork_image_asset']={'source':'builtin_image_gen','storage_provider':'gcs','bucket':m['bucket'],'gcs_bucket':m['bucket'],'object_path':m['object_path'],'gcs_path':m['object_path'],'width':1920,'height':1080,'sha256':m['sha256']}
 for key in ['ae_motion_plan','ae_effect_plan']:
  if isinstance(scene.get(key),dict):scene[key].update({'local_source_path':m['local_path'],'local_source_sha256':m['sha256'],'source_revision':'3373-cast-hair-20261005','source_status':'source_changed_requires_review','target_positions_require_review':True})
 scene['ae_motion_status']='source_changed_requires_review';scene['ae_effect_status']='source_changed_requires_review'
 return scene

def patch_scene(m):
 n=m['number'];s=next(x for x in live_scenes if x['scene_number']==n);metadata=modify(copy.deepcopy(s['metadata']),n,m)
 saved,_=store.request('PATCH','std_project_scenes',params={'id':f"eq.{s['id']}",'updated_at':f"eq.{s['updated_at']}"},body={'image_prompt':metadata['image_prompt'],'metadata':metadata,'asset_status':'ready','updated_at':now},prefer='return=representation');assert len(saved)==1
 return n
with ThreadPoolExecutor(max_workers=4) as pool:changed=list(pool.map(patch_scene,media))

# Scope future generation instructions even when an existing image already passed review.
retained=[r for r in audit if not r['regenerate']]
def retained_prompt(row):
 names=row['visible_characters'];definitions=[name+': '+fixed[name][1].split('Usual')[0] for name in names if name in fixed]
 return style+'\nScene-specific shot: '+row['shot_en']+'\nOnly the following people are physically present: '+', '.join(names)+'.\n'+'\n'.join(definitions)+'\nUse the approved portrait identity and this scene\'s explicitly stated age and clothing. People only mentioned in narration or quoted writing remain absent. Single16:9cel frame, no text, no modern objects.'
def prompt_only(scene,row):
 scene['image_prompt']=retained_prompt(row)
 for key in ['panel_prompt','visual_prompt']:
  if key in scene:scene[key]=scene['image_prompt']
 scene['characters_present']=row['visible_characters']
 scene['character_references']=[{'name':name,'character_key':reference_designs[name]['character_key'],'image_url':reference_designs[name]['image_url']} for name in row['visible_characters'] if name in reference_designs]
 return scene
def patch_retained(row):
 s=next(x for x in live_scenes if x['scene_number']==row['number']);metadata=prompt_only(copy.deepcopy(s['metadata']),row)
 saved,_=store.request('PATCH','std_project_scenes',params={'id':f"eq.{s['id']}",'updated_at':f"eq.{s['updated_at']}"},body={'image_prompt':metadata['image_prompt'],'metadata':metadata,'updated_at':now},prefer='return=representation');assert len(saved)==1
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(patch_retained,retained))

topic=read('topics_queue',{'id':'eq.3373'})[0];project=read('std_projects',{'id':f'eq.{project_id}'})[0]
for row in audit:
 old=next(x for x in snapshot['topic']['pregenerated_structure']['scenes'] if int(x['scene_number'])==row['number']);live=next(x for x in topic['pregenerated_structure']['scenes'] if int(x['scene_number'])==row['number']);assert old['image_prompt']==live['image_prompt'],'Concurrent topic prompt edit'
topic_structure=copy.deepcopy(topic['pregenerated_structure']);payload=copy.deepcopy(project['project_payload']);progress=copy.deepcopy(project['progress_payload'])
for m in media:
 n=m['number'];modify(next(x for x in topic_structure['scenes'] if int(x['scene_number'])==n),n,m)
 for c in [payload.get('structure',{}),payload.get('pregenerated_structure',{}),payload]:
  for scene in c.get('scenes',[]):
   if int(scene.get('scene_number') or scene.get('scene_order') or 0)==n:modify(scene,n,m)
for row in retained:
 prompt_only(next(s for s in topic_structure['scenes'] if int(s['scene_number'])==row['number']),row)
 for c in [payload.get('structure',{}),payload.get('pregenerated_structure',{}),payload]:
  for s in c.get('scenes',[]):
   if int(s.get('scene_number') or s.get('scene_order') or 0)==row['number']:prompt_only(s,row)


def add_designs(structure):
 if not structure:return
 current=[c for c in structure.get('supporting_characters',[]) if c.get('name') not in ['仙太郎','次郎']];structure['supporting_characters']=[*current,*copy.deepcopy(new_characters)]
 anchors=structure.setdefault('character_anchors',{});anchors['supporting_characters']=copy.deepcopy(structure['supporting_characters'])
 structure['image_repair_revision']='3373-cast-hair-20261005'
 for grid in structure.get('image_grid_prompts',[]):
  updated=False
  for panel in grid.get('panels',[]):
   n=int(panel.get('scene_number') or 0)
   scene=next((s for s in structure.get('scenes',[]) if int(s.get('scene_number') or s.get('scene_order') or 0)==n),None)
   if n>=19 and scene:
    panel['panel_prompt']=scene['image_prompt'];updated=True
  if updated:
   grid['prompt']=style+'\nCreate a strict2x2 grid with equal panels and clean dividers. Each panel independently depicts ONLY its specified people, with their approved identity reference and stated scene age and wardrobe. No text or labels inside any panel.\n'+'\n'.join(str(panel.get('position') or '')+': '+panel['panel_prompt'] for panel in grid.get('panels',[]))
   grid['image_repair_revision']='3373-cast-hair-20261005'
 # Preserve the old manifest as an archive; its images and target coordinates
 # cannot be reused for the regenerated compositions without a fresh AE review.
 structure['ae_local_source_manifest_status']='source_changed_requires_review'
 structure['ae_image_source_replacements']=[{'scene_number':m['number'],'local_source_path':m['local_path'],'local_source_sha256':m['sha256'],'image_url':f"/api/std/assets/gcs-file?bucket={quote(m['bucket'],safe='')}&path={quote(m['object_path'],safe='')}"} for m in media]
 for plan in structure.get('ae_motion_plans',[]):
  match=next((m for m in media if m['number']==int(plan.get('scene_number') or 0)),None)
  if match:plan.update({'local_source_path':match['local_path'],'local_source_sha256':match['sha256'],'source_revision':'3373-cast-hair-20261005','source_status':'source_changed_requires_review','target_positions_require_review':True})
 for c in [structure.get('main_character'),*structure['supporting_characters'],*(structure.get('characters') or [])]:
  if not isinstance(c,dict):continue
  if c.get('name') in fixed:
   if c['name'] in reference_designs:c['image_url']=reference_designs[c['name']]['image_url']
   c['continuity_instruction']=fixed[c['name']][1]
   if c['name'] in ['仙太郎','次郎']:c.update(copy.deepcopy(reference_designs[c['name']]))
   if c['name'] in ['お鈴','お徳']:c['visual_dna_en']=fixed[c['name']][1]
   if c['name']=='お鈴':c['wardrobe_en']='Cream kimono with muted green floral obi, exact approved portrait.'
   if c['name']=='お徳':c['wardrobe_en']='Brown kimono with pale cream work apron, exact approved portrait.'
 if structure.get('main_character'):anchors['main_character']=copy.deepcopy(structure['main_character'])
 anchors['supporting_characters']=copy.deepcopy(structure['supporting_characters'])
add_designs(topic_structure)
for c in [payload.get('structure'),payload.get('pregenerated_structure'),payload]:add_designs(c)
progress.update({'image_repair_revision':'3373-cast-hair-20261005','image_repaired_scenes':sorted(changed),'ae_source_changed_scenes':sorted(changed),'rerender_draft':True})
topic_saved,_=store.request('PATCH','topics_queue',params={'id':'eq.3373','created_at':f"eq.{topic['created_at']}",'pregenerated_structure->scenes->61->>image_prompt':'eq.'+topic['pregenerated_structure']['scenes'][61]['image_prompt']},body={'pregenerated_structure':topic_structure},prefer='return=representation');assert len(topic_saved)==1
project_saved,_=store.request('PATCH','std_projects',params={'id':f'eq.{project_id}','updated_at':f"eq.{project['updated_at']}"},body={'project_payload':payload,'progress_payload':progress,'updated_at':datetime.now(timezone.utc).isoformat()},prefer='return=representation');assert len(project_saved)==1
old_ids=[m['previous_asset_id'] for m in media if not m.get('existing')]
if old_ids:store.request('PATCH','std_project_assets',params={'id':'in.('+','.join(old_ids)+')','status':'in.(assigned,uploaded)'},body={'status':'replaced'},prefer='return=representation')
(backup/'batch-publish.receipt.json').write_text(json.dumps({'scenes':changed,'media':media,'brother_references':new_characters,'preserved_final_video':True},ensure_ascii=False,indent=2),encoding='utf8')
print('PUBLISHED',len(changed),flush=True)
