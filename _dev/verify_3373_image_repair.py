import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.ae_highlight_worker import _download_gcs_file,GcsRef
from concurrent.futures import ThreadPoolExecutor
store=ScriptStore();backup=ROOT/'_dev/artifacts/image_repair_3373';out=ROOT/'output/codex-local-console/image-repair-3373';pid='e9233112-f0d7-4b35-91bf-2f892844eb30'
def read(t,p):return store.request('GET',t,params={'select':'*',**p})[0]
project=read('std_projects',{'id':f'eq.{pid}'})[0];topic=read('topics_queue',{'id':'eq.3373'})[0]
scenes=read('std_project_scenes',{'project_id':f'eq.{pid}','order':'scene_number.asc'});assets=read('std_project_assets',{'project_id':f'eq.{pid}','order':'created_at.desc'})
before=json.loads((backup/'scenes.before.json').read_text(encoding='utf8'));bp=json.loads((backup/'project.before.json').read_text(encoding='utf8'))[0];ba=json.loads((backup/'assets.before.json').read_text(encoding='utf8'))
audit=json.loads((out/'audit.json').read_text(encoding='utf8'))['scenes'];selected={r['number'] for r in audit if r['regenerate']};retained={r['number'] for r in audit if not r['regenerate']}
assert len(scenes)==101
for s in scenes:
 n=s['scene_number'];original=next(x for x in before if x['scene_number']==n)
 if n<19:
  assert s==original,f'Early scene changed: {n}'
  for a in [a for a in ba if a['scene_number']==n]:assert next(x for x in assets if x['id']==a['id'])==a,f'Early asset changed: {n}'
  continue
 for k in ['scene_text','scene_number','scene_id','start_seconds','end_seconds','duration_seconds','narration','subtitles','tts_url','voice_segments','source_start','source_end']:
  if k in original:assert s.get(k)==original[k],f'Scene {n} {k} changed'
  if k in original['metadata']:assert s['metadata'].get(k)==original['metadata'][k],f'Scene {n} metadata {k} changed'
 current=next(a for a in assets if a['scene_number']==n and a['asset_type']=='image' and a['status'] in ['assigned','uploaded'])
 previous=next(a for a in ba if a['scene_number']==n and a['asset_type']=='image' and a['status'] in ['assigned','uploaded'])
 if n in selected:
  d=json.loads((out/'generated'/f'scene-{n:03}'/'generation.json').read_text(encoding='utf8'))
  assert current['metadata']['image_repair_sha256']==d['sha256']
  assert current['checksum']==hashlib.sha256(Path(d['path']).read_bytes()).hexdigest()
  assert current['id']!=previous['id'];assert next(a for a in assets if a['id']==previous['id'])['status']=='replaced'
  canonical=next(x for x in topic['pregenerated_structure']['scenes'] if int(x['scene_number'])==n)
  assert canonical['image_prompt']==s['image_prompt']==(out/'generated'/f'scene-{n:03}'/'prompt.txt').read_text(encoding='utf8')
  assert current['metadata']['gcs_path'] in canonical['metadata']['cowork_image_asset'].values()
  for c in [project['project_payload']['structure'],project['project_payload']]:
   ps=next(x for x in c['scenes'] if int(x.get('scene_number') or x.get('scene_order'))==n)
   assert ps['image_url']==canonical['image_url'] and ps['image_prompt']==canonical['image_prompt']
 else:assert current['id']==previous['id'],f'Retained image changed: {n}'
 if n>=19:assert s['image_prompt']!=original['image_prompt'],f'Prompt not revised: {n}'
for k in ['script','tts_url','voice_id','audio_url','subtitles','tts_speed','voice_map','multi_voice','tts_provider','voice_segments','render_settings','subtitle_translations','original_worker_script','speaker_name_translations']:
 assert project['project_payload'].get(k)==bp['project_payload'].get(k),f'Payload {k} changed'
for a in ba:
 if a['asset_type']!='image':assert next(x for x in assets if x['id']==a['id'])==a,f'Non-image asset changed: {a["id"]}'
for k in ['latest_render_version','editing_render_version','remote_render_queue_id','remote_asset_file_id','remote_asset_web_link','remote_asset_file_name','remote_render_queue_payload']:
 assert project['progress_payload'].get(k)==bp['progress_payload'].get(k),f'Render progress {k} changed'
characters=read('topic_character_assets',{'topic_queue_id':'eq.3373'})
assert {'repair3373-sentaro-20261005','repair3373-jiro-20261005'}<={c['character_key'] for c in characters}
def verify_remote(n):
 a=next(a for a in assets if a['scene_number']==n and a['asset_type']=='image' and a['status'] in ['assigned','uploaded']);m=a['metadata'];local=out/'remote-verification'/f'scene-{n:03}.png';_download_gcs_file(GcsRef(m['gcs_bucket'],m['gcs_path']),local);assert hashlib.sha256(local.read_bytes()).hexdigest()==m['image_repair_sha256'];return n
with ThreadPoolExecutor(max_workers=3) as pool:remote_verified=list(pool.map(verify_remote,[62,79,101]))
receipt={'status':'verified','reviewed_scene_count':83,'regenerated_scene_count':len(selected),'retained_scene_count':len(retained),'regenerated_scenes':sorted(selected),'scripts_tts_subtitles_timings_preserved':True,'first18_preserved':True,'non_image_assets_preserved':True,'previous_final_render_preserved':True,'brother_identity_references_saved':True}
receipt['gcs_download_hash_verified_scenes']=remote_verified
(backup/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
prompts=[{'scene_number':s['scene_number'],'regenerated':s['scene_number'] in selected,'visible_characters':next(r['visible_characters'] for r in audit if r['number']==s['scene_number']),'image_prompt':s['image_prompt'],'local_image_path':str(out/'generated'/f'scene-{s["scene_number"]:03}'/'normalized.png') if s['scene_number'] in selected else str(out/f'scene-{s["scene_number"]:03}.png')} for s in scenes if s['scene_number']>=19]
(out/'final-prompt-set.json').write_text(json.dumps({'topic_id':3373,'generation_mode':'builtin_image_gen','scenes':prompts},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False))
