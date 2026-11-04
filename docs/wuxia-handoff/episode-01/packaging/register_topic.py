"""Register the complete manual Codex package, preserving all existing user work."""
import sys,json,hashlib,copy,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
P=Path(os.environ.get('WUXIA_EPISODE_DIR') or Path(__file__).resolve().parent.parent).resolve();ROOT=P.parents[2];OUT=P/'packaging'
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import topic_row
from services.image_grid_prompts import grid_windows,build_compact_image_grid_prompts
from prepare_registration import read,write
from worker.cowork_scene_assets import _upload_gcs_file,_gcs_credentials
from urllib.parse import quote
import requests
S=ScriptStore()
def upload(p):
 rows,_=S.request('GET','global_settings',params={'select':'key,value','key':'in.(sys_api_gcs_bucket_name,sys_api_gcs_project_id,sys_api_gcs_client_email,sys_api_gcs_private_key)'})
 keys={'sys_api_gcs_bucket_name':'GCS_BUCKET_NAME','sys_api_gcs_project_id':'GCS_PROJECT_ID','sys_api_gcs_client_email':'GCS_CLIENT_EMAIL','sys_api_gcs_private_key':'GCS_PRIVATE_KEY'}
 for r in rows:
  if r['value']:os.environ[keys[r['key']]]=str(r['value'])
 data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();obj=f'codex-productions/{P.parent.name}/{P.name}/{p.stem}-{sha}{p.suffix}'
 receipts=read(OUT/'asset-upload-receipts.json');rel=p.relative_to(P).as_posix()
 if rel in receipts and receipts[rel]['sha256']==sha:return receipts[rel]
 b,o,url=_upload_gcs_file(p,obj,'image/png' if p.suffix=='.png' else 'application/json')
 creds,_=_gcs_credentials()
 res=requests.get(f'https://storage.googleapis.com/storage/v1/b/{quote(b,safe="")}/o/{quote(o,safe="")}',params={'alt':'media'},headers={'Authorization':f'Bearer {creds.token}'},timeout=90)
 res.raise_for_status();assert hashlib.sha256(res.content).hexdigest()==sha
 receipt={'media_url':url,'gcs_bucket':b,'gcs_path':o,'sha256':sha,'bytes':len(data),'verified_download_sha256':True}
 receipts[rel]=receipt;write(OUT/'asset-upload-receipts.json',receipts);return receipt
def main():
 script=read(P/'script-final.json');meta=read(OUT/'publish-metadata.json');design=read(OUT/'thumbnail-design.json')
 translation=read(OUT/'review-translation-th.json');jobs=read(P/'image-generation-jobs.json');bible=read(P/'visual-bible.json')
 assets=read(OUT/'asset-upload-receipts.json')
 expected={f"images/{j['asset_id']}.png" for j in jobs}
 expected.update(f"character-sheets/{c['id']}-v1.png" for c in script['cast'])
 assert expected.issubset(assets) and all(assets[k].get('verified_download_sha256') for k in expected)
 final=upload(OUT/'thumbnail-final.png');assets=read(OUT/'asset-upload-receipts.json')
 bg=assets['packaging/thumbnail-bg-v1.png']['media_url']
 design.update(editor_bg_url=bg,bg_url=bg,thumbnail_url=final['media_url'],render_status='completed',renderer='auth-web/lib/stdThumbnailRender.ts:drawThumbnail',thumbnail_completed=True)
 write(OUT/'thumbnail-design.json',design)
 direction=read(P/'direction/ae-scene-package.json')
 for scene in direction['scenes']:
  for state in scene['states']:state.update(assets[state['file']])
 write(OUT/'ae-scene-package-web.json',direction);web_direction=upload(OUT/'ae-scene-package-web.json')
 chars=[]
 for char in script['cast']:
  key=char['id'];ref=assets[f'character-sheets/{key}-v1.png']
  chars.append({**char,'character_key':key,'name':char['name'],'visual_dna_en':bible['cast'][key],'image_prompt':bible['cast'][key],
   'image_url':ref['media_url'],'reference_image_url':ref['media_url'],'reference_type':'detailed_character_sheet','image_generation_status':'ready',**ref})
 anchors={'main_character':chars[0],'supporting_characters':chars[1:],'version':1}
 scenes=[]
 for n,(s,d) in enumerate(zip(script['scenes'],direction['scenes']),1):
  js=[j for j in jobs if j['scene_id']==s['id']];text='\n'.join(b['text'] for b in s['blocks'])
  first=d['states'][0];ref=assets[first['file']]
  scenes.append({'id':s['id'],'scene_id':s['id'],'scene_order':n,'scene_number':n,'scene_title':s['location'],
   'script_excerpt':text,'scene_text':text,'narration':text,'blocks':s['blocks'],
   'image_prompt':'Selected image style: wuxia_webtoon. '+js[0]['prompt'],'grid_panel_prompt':f'Scene {n}. '+js[0]['prompt'],
   'media_prompt_status':'ready','video_prompt_required':False,'visual_type':'image','video_generation_mode':'image',
   'image_url':ref['media_url'],'asset_status':'ready','image_generation_status':'ready',
   'duration_seconds':d['preview_duration_seconds'],'timing_basis':'provisional_edit_preview_not_recorded_voice',
   'state_images':[{'description':s['visual_states'][st['asset_id'].endswith('04') and 3 or int(st['asset_id'][-2:])-1],**st} for st in d['states']],
   'scene_direction_plan':{'intent':s['ae'],'camera':'hold','transition':'cut','narration_captions':False,
    'all_text_editable':True,'states':d['states'],'graphics':d['graphics'],'effects':d['effects'],
    'timing_basis':'normalized_preview_not_recorded_speech','voice_binding':'exact block and quote anchors; bind actual recording later'},
   'metadata':{'cowork_image_asset':{'source':'cowork_builtin_imagegen','storage_provider':'gcs',**ref,
    'width':first['width'],'height':first['height']},'wuxia_state_images':d['states']}})
 grids=[]
 for i,(start,end) in enumerate(grid_windows(len(scenes)),1):
  group=scenes[start:end]
  grids.append({'grid_number':i,'scene_numbers':[s['scene_number'] for s in group],'shared_style':bible['style'],
   'negative_prompt':'No text, letters, watermarks, captions, extra panels or frames.',
   'panels':[{'scene_number':s['scene_number'],'scene_id':s['id'],'panel_prompt':s['grid_panel_prompt']} for s in group]})
 full_script='\n\n'.join(s['scene_text'] for s in scenes);sha=hashlib.sha256(full_script.encode()).hexdigest()
 identity=hashlib.sha256((P.parent.name+'/'+P.name+'/'+sha).encode()).hexdigest()[:32]
 sound=read(P/'direction/sound-and-music-direction.json');quality=read(P/'direction/visual-reviews.json')
 scene_translations=[]
 for s in script['scenes']:
  rows=[b for b in translation['blocks'] if b['scene_id']==s['id']]
  assert [b['source_text'] for b in rows]==[b['text'] for b in s['blocks']]
  scene_translations.append({'scene_number':int(s['id'][-2:]),'source_text':'\n'.join(b['source_text'] for b in rows),'translated_text':'\n'.join(b['translated_text'] for b in rows)})
 structure={'scenes':scenes,'image_style':'wuxia_webtoon','production_mode':'standard',
  'series_title':script['series_title'],'episode':script['episode'],'episode_title':script['episode_title'],
  'content_setting':{'language':'ko','country':'fictional_china','era':'fictional_premodern','image_style':'wuxia_webtoon'},
  'effective_user_settings':script['settings'],'world_bible':bible,'required_video_scene_count':0,'video_scene_count':0,
  'image_grid_prompts':build_compact_image_grid_prompts(grids),'image_grid_prompt_status':'ready',
  'image_generation_status':'ready','actual_state_image_count':len(jobs),'character_reference_status':'ready',
  'character_anchors':anchors,'main_character':chars[0],'supporting_characters':chars[1:],
  'ae_scene_delivery':'gcs','wuxia_ae_package':direction,'wuxia_ae_package_asset':web_direction,
  'sound_direction':sound,'bgm_prompt':sound['music'],'sound_effect_plan_status':'direction_only_no_library_files_claimed',
  'render_settings':{'subtitles_enabled':False,'narration_verbatim_captions':False},'thumbnail_design':design}
 package={'script':full_script,'generated_title':meta['selected_title'],'structure':structure,'publish_metadata':meta,
  'character_anchors':anchors,'script_quality_report':{'independent_review':read(P/'independent-review-v1.json'),'visual_review':quality},
  'script_translations':{'th':{'status':'ready','source':'local_codex_cli_worker','blocks':translation['blocks'],'scenes':scene_translations}},
  'thumbnail_hook_texts':read(OUT/'packaging-review.json')['hook_alternatives'],
  'thumbnail_image_prompt':(OUT/'thumbnail-prompt.txt').read_text(encoding='utf-8'),'thumbnail_text_layers':design['text_layers']}
 request={'title':meta['selected_title'],'category_id':18,'language':'ko','script_style':'story','image_style':'wuxia_webtoon','duration_minutes':10,'required_video_scene_count':0}
 row=topic_row(identity,package,request);progress=row['progress_payload'];progress.pop('source_script_job_id',None)
 progress.update(source_kind='manual_codex_delivery',source_package_id=identity,source_script_sha256=sha,
  image_generation_status='ready',actual_state_image_count=len(jobs),character_reference_status='ready',
  thumbnail_bg_url=bg,thumbnail_url=final['media_url'],thumbnail_completed=True,thumbnail_design=design,
  actual_character_sheet_count=len(script['cast']),asset_upload_verified_count=len(read(OUT/'asset-upload-receipts.json')),
  ae_scene_delivery='gcs',quality_notes=quality,render_settings={'subtitles_enabled':False,'narration_verbatim_captions':False},
  actual_audio_sync_finalized=False,web_registration_scope='reviewed script, original art, editable thumbnail, metadata and saved directions')
 write(OUT/'delivery-package.json',package);write(OUT/'web-topic.json',row)
 check=json.loads(subprocess.check_output(['node',str(OUT/'web_contract.cjs'),'ready',str(OUT/'web-topic.json')],cwd=ROOT,text=True,encoding='utf-8'))
 assert check['ready'] and check['prompts_ready'],check
 write(OUT/'web-readiness.json',check)
 if '--register' not in sys.argv:print(json.dumps({'prepared':True,'identity':identity,'web_readiness':check}));return
 query={'select':'*','progress_payload->>source_package_id':'eq.'+identity,'limit':2}
 existing,_=S.request('GET','topics_queue',params=query)
 assert len(existing)<2,'duplicate package topics require explicit repair'
 if existing:
  result=existing[0]
  assert result['pregenerated_script']==full_script and result['pregenerated_structure']==structure,'registered package changed; never overwrite'
 else:
  # Compare exact final title too, preserving unrelated or independently owned topics.
  collision,_=S.request('GET','topics_queue',params={'select':'id,topic,status','generated_title':'eq.'+meta['selected_title'],'limit':2})
  assert not collision,'same title already registered; inspect before any write'
  try:
   rows,_=S.request('POST','topics_queue',body=row,prefer='return=representation');result=rows[0]
  except Exception:
   rows,_=S.request('GET','topics_queue',params=query)
   if len(rows)!=1:raise
   result=rows[0]
 actual,_=S.request('GET','topics_queue',params={'select':'*','id':'eq.'+str(result['id']),'limit':1});actual=actual[0]
 for field in ['pregenerated_script','pregenerated_structure','publish_metadata','progress_payload']:
  assert actual[field]==row[field],f'readback mismatch: {field}'
 write(OUT/'registered-topic-readback.json',actual)
 verify=json.loads(subprocess.check_output(['node',str(OUT/'web_contract.cjs'),'ready',str(OUT/'registered-topic-readback.json')],cwd=ROOT,text=True,encoding='utf-8'))
 assert verify['ready'] and verify['prompts_ready']
 receipt={'topic_id':actual['id'],'source_package_id':identity,'script_sha256':sha,'scene_count':len(scenes),'state_images':len(jobs),'character_sheets':len(script['cast']),
  'thumbnail_completed':True,'thumbnail_layers':len(design['text_layers']),'review_translation_blocks':len(translation['blocks']),
  'web_readiness':verify,'database_readback':'exact_match','existing_topics_modified':False,'registered_at':datetime.now(timezone.utc).isoformat(),
  'url':'https://studio.airing.work/std?tab=topics','youtube_published':False}
 write(OUT/'registration-receipt.json',receipt)
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
