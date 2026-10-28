"""Prepare/insert one fully populated user-web topic, with idempotent readback."""
import copy,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
import requests
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from worker.cowork_scene_assets import _upload_gcs_file,_download_gcs_bytes
from worker.codex_character_assets import CharacterAssetStore,digest
from worker.thumbnail_contract import thumbnail_draft,background_ready
BASE=ROOT/'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e';OUT=BASE/'web-package'
JOB='6ae46b7afca84070b36e9e13d7de0a6e'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def save(name,value):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
def prepare():
 c=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'));s=copy.deepcopy(c['structure']);media=read('media-prompts.json')['scenes'];assets=read('uploaded-scenes.json');refs=read('uploaded-characters.json');subs=read('subtitles.json')
 assert len(assets)==len(media)==len(s['scenes'])==136 and len(refs)==4
 assert all(a['verified'] for a in assets+refs)
 assert len(list((OUT/'scene-grids').glob('grid-*.review.json')))==34
 translations={}
 for language in ['ko','th']:
  tr=read(f'translations-{language}.json');assert tr['status']=='completed' and len(tr['blocks'])==len(subs)==721
  for i,(r,t) in enumerate(zip(subs,tr['blocks'])):assert t['index']==i and t['source_text']==r['text'] and t['translated_text'].strip()
  translations[language]={'version':1,'source_language':'ja','status':'completed','updated_at':datetime.now(timezone.utc).isoformat(),'blocks':tr['blocks']}
 anchors={'main_character':refs[0],'supporting_characters':refs[1:],'recurring_characters':refs[1:],'character_image_generation':{'enabled':True,'status':'ready','count':4,'required_count':4}}
 s.update(character_anchors=anchors,main_character=refs[0],supporting_characters=refs[1:],character_reference_status='ready',image_generation_status='completed',image_grid_prompt_status='ready',media_prompt_status='ready',required_video_scene_count=18)
 s['scene_cast']={**(s.get('scene_cast') or {})} if isinstance(s.get('scene_cast'),dict) else s.get('scene_cast',[])
 bymedia={r['scene_number']:r for r in media};byasset={r['scene_number']:r for r in assets};cursor=0
 for scene in s['scenes']:
  n=scene['scene_number'];m=bymedia[n];a=byasset[n];scene.update(image_prompt=m['image_prompt'],video_prompt=m['video_prompt'],image_url=a['image_url'],gcs_bucket=a['gcs_bucket'],gcs_path=a['gcs_path'],image_generation_status='completed',media_prompt_status='ready',image_sha256=a['sha256'],asset_status='image_ready',start_time=cursor,end_time=cursor+scene['duration_seconds'],video_prompt_required=n<=18,visual_type='video' if n<=18 else 'image',video_generation_mode='user_upload' if n<=18 else 'image')
  scene['metadata']={**(scene.get('metadata') or {}),'image_url':a['image_url'],'gcs_bucket':a['gcs_bucket'],'gcs_path':a['gcs_path'],'image_generation_status':'completed','image_sha256':a['sha256']};cursor+=scene['duration_seconds']
 assert cursor==1961
 for row in subs:row.update(image_url=byasset[row['scene_number']]['image_url'])
 grids=[]
 for offset in range(0,136,4):
  items=media[offset:offset+4];prompt='Strict 2x2 grid, no panel labels or text. Approved warm contemporary Japanese anime.\n'+'\n'.join(f"Position: {pos}\nScene {x['scene_number']}: {x['image_prompt']}" for pos,x in zip(['Top-Left','Top-Right','Bottom-Left','Bottom-Right'],items));grids.append({'grid_number':offset//4+1,'scene_numbers':[x['scene_number'] for x in items],'template':'strict_2x2_compact_v1','prompt':prompt,'panels':[{'scene_number':x['scene_number'],'panel_prompt':x['image_prompt']} for x in items]})
 s['image_grid_prompts']=grids
 meta=read('metadata-thumbnail-brief.json');thumbfile=OUT/'thumbnail-background-1920.png'
 if not thumbfile.exists():
  with Image.open(OUT/'thumbnail-background.png') as im:ImageOps.fit(im.convert('RGB'),(1920,1080),method=Image.Resampling.LANCZOS).save(thumbfile)
 if (OUT/'uploaded-thumbnail.json').exists():thumb=read('uploaded-thumbnail.json')
 else:
  data=thumbfile.read_bytes();sha=hashlib.sha256(data).hexdigest();b,p,u=_upload_gcs_file(thumbfile,f'topics/local-{JOB}/thumbnail/background-{sha[:20]}.png','image/png');assert hashlib.sha256(_download_gcs_bytes(b,p)).hexdigest()==sha;thumb={'image_url':u,'gcs_bucket':b,'gcs_path':p,'sha256':sha,'verified':True};save('uploaded-thumbnail.json',thumb)
 layers=[{'text':'友人だと'},{'text':'信じていた'}];design=thumbnail_draft(meta['thumbnail']['copy_candidates'],layers,title=c.get('generated_title') or '戻ってきた妻を、もう一度信じられますか')
 for i,layer in enumerate(design['text_layers']):layer.update(fontFamily='Noto Sans JP',fontSize=26 if i==0 else 24,x=12,y=104+i*38,strokeWidth=2)
 design.update(style='jp_domestic_watercolor')
 progress=background_ready({'thumbnail_design':design,'thumbnail_hook_texts':meta['thumbnail']['copy_candidates']},thumb['image_url'])
 progress.update(local_script_job_id=JOB,script_sha256=hashlib.sha256(c['script'].encode()).hexdigest(),main_character=refs[0],supporting_characters=refs[1:],character_anchors=anchors,subtitles=subs,subtitles_saved=True,subtitle_translations=translations,subtitle_timing_status='planned_requires_tts',subtitles_completed=False,has_tts_audio=False,tts_completed=False,scene_count=136,scene_image_count=136,image_generation_status='completed',image_style='jp_domestic_watercolor',required_video_scene_count=18,publish_metadata=meta['publish_metadata'],thumbnail_image_prompt=meta['thumbnail']['background_prompt'],sfx_plan=c.get('sfx_plan'),sfx_cues=c.get('sfx_cues'),bgm_prompt=c.get('bgm_prompt'),source_video_url='https://www.youtube.com/watch?v=_9sLCqgNkJA',source_duration_seconds=1961,registration_source='codex_supervised_local_script_worker')
 s.update(subtitle_translations=translations,subtitles=subs,source_script_sha256=progress['script_sha256'])
 payload={'topic':'戻ってきた妻を、もう一度信じられますか','generated_title':'戻ってきた妻を、もう一度信じられますか','category_id':15,'language':'ja','status':'pending','assigned_employee_email':'','assigned_at':None,'assigned_script_style':'japanese_domestic_drama','assigned_image_style':'jp_domestic_watercolor','assigned_duration_minutes':33,'recommended_duration_minutes':33,'total_scenes':136,'video_scenes':18,'image_scenes':118,'pregenerated_script':c['script'],'pregenerated_script_status':'ready','pregenerated_structure':s,'pregenerated_structure_status':'ready','publish_metadata':meta['publish_metadata'],'narrative_blueprint':c['narrative_blueprint'],'script_quality_report':c['script_quality_report'],'progress_payload':progress}
 save('topic-registration-payload.json',payload);print('Prepared payload: 136 images, 4 references, 721 subtitles and two complete translations.',flush=True);return payload,refs
def apply(payload,refs):
 verification=read('web-eligibility-check.json');assert verification['eligible'] and verification['scene_count']==136
 base=os.environ['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SERVICE_ROLE_KEY'];headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':'return=representation'}
 params={'select':'*','progress_payload->>local_script_job_id':'eq.'+JOB}
 r=requests.get(base+'/rest/v1/topics_queue',headers=headers,params=params,timeout=60);r.raise_for_status();rows=r.json();assert len(rows)<=1
 if not rows:
  r=requests.post(base+'/rest/v1/topics_queue',headers=headers,json=payload,timeout=120);r.raise_for_status();rows=r.json();assert len(rows)==1;save('topic-registration-receipt.json',{'topic_id':rows[0]['id'],'local_script_job_id':JOB,'created_at':datetime.now(timezone.utc).isoformat()})
 topic=rows[0];identity=topic['id'];assert topic['pregenerated_script']==payload['pregenerated_script'];assert topic['progress_payload']['local_script_job_id']==JOB
 for language in ['ko','th']:
  prior=topic['progress_payload']['subtitle_translations'][language]
  expected=payload['progress_payload']['subtitle_translations'][language]
  assert prior['blocks']==expected['blocks']
  expected['updated_at']=prior['updated_at']
  payload['pregenerated_structure']['subtitle_translations'][language]['updated_at']=prior['updated_at']
 store=CharacterAssetStore()
 for ref in refs:
  design={k:ref[k] for k in ['name','gender','age_group','visual_dna_en','hair_design_en','wardrobe_en','continuity_instruction','scene_numbers'] if k in ref}
  record={k:ref.get(k) for k in ['character_key','name','role','gender','age_group','visual_dna_en','wardrobe_en','continuity_instruction','image_url','storage_bucket','storage_object_path','generation_model']}
  record.update(topic_queue_id=identity,category='일본사건',script_style='japanese_domestic_drama',image_style='jp_domestic_watercolor',source='codex-character-images-v2',dna=design,usage_context={'reference_fingerprint':digest(design),'sha256':ref['sha256'],'character_design':design,'stage':'after_script_before_media_prompts'})
  store.request('POST','/rest/v1/topic_character_assets',params={'on_conflict':'topic_queue_id,character_key'},headers={'Prefer':'resolution=merge-duplicates,return=representation'},json=record)
  actual_ref=store.request('GET','/rest/v1/topic_character_assets',params={'topic_queue_id':f'eq.{identity}','character_key':'eq.'+ref['character_key'],'select':'image_url,usage_context,dna'}).json()
  assert len(actual_ref)==1 and actual_ref[0]['image_url']==ref['image_url'] and actual_ref[0]['usage_context']==record['usage_context'] and actual_ref[0]['dna']==design
 r=requests.get(base+'/rest/v1/topics_queue',headers=headers,params={'id':f'eq.{identity}','select':'*'},timeout=90);r.raise_for_status();actual=r.json()[0]
 for field in ['pregenerated_script','pregenerated_structure','progress_payload','publish_metadata','category_id','assigned_script_style']:assert actual[field]==payload[field],field+' readback differs'
 save('registered-topic.json',actual);save('registration-status.json',{'status':'registered','topic_id':identity,'scene_images':136,'character_images':4,'subtitle_blocks':721,'ko_blocks':721,'th_blocks':721,'duration_seconds':1961,'db_readback_verified':True,'thumbnail_status':'awaiting_user_save','tts_status':'not_generated','first_18_video_clips':'user_upload_required'})
 print('REGISTERED topic',identity,flush=True)
if __name__=='__main__':
 payload,refs=prepare()
 if '--apply' in sys.argv:apply(payload,refs)
