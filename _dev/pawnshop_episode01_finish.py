"""Finish and idempotently register the explicitly requested pawnshop episode.
Does not generate TTS, render video, claim a user account, or publish to YouTube.
"""
import copy,hashlib,json,os,re,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.generation_validation import validated_stage, validate_story_review, validate_registration_update, validate_registration_readback
from worker.script_worker_store import ScriptStore
from worker.codex_content_runner import CodexStagedContentRunner,_plan_image_generation_efficiency
from services.image_grid_prompts import build_compact_image_grid_prompts,validate_scene_image_prompt_readiness,validate_image_grid_prompt_readiness,grid_windows
OUT=ROOT/'output/pawnshop-series/episode-01';OUT.mkdir(parents=True,exist_ok=True)
JOB='9a74a481741948aaa8bf4cf8bd27734b'
BASE=ROOT/'output/codex-local-console'/JOB
STYLE='Near-photorealistic cinematic Japanese noir, modern Japan, realistic human anatomy and materials, warm amber practical light, muted petroleum-teal shadows, fine 35mm grain. Not anime or a historical period setting. No baked text, subtitles, logos or watermarks.'
store=ScriptStore();runner=CodexStagedContentRunner()
def save(name,value):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
def status(stage,**data):
 save('finish-status.json',{'stage':stage,'updated_at':datetime.now(timezone.utc).isoformat(),**data});print(stage,flush=True)
def stage(name,context,task,validate):
 return validated_stage(lambda n,c,t:runner._stage('pawnshop-'+JOB,n,c,t),name,context,task,validate,attempts=4)

def number(scene,index):return int(scene.get('scene_number') or scene.get('scene_order') or index)
def main():
 candidate=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
 request=json.loads((OUT/'generation-request.json').read_text(encoding='utf-8'))
 structure=copy.deepcopy(candidate['structure']);scenes=structure['scenes']
 assert candidate['script'].strip() and len(scenes)>50
 assert abs(sum(float(s['duration_seconds']) for s in scenes)-2100)<.1
 assert candidate['language']=='ja'
 assert not any(re.search(r'[가-힣]',s.get('scene_text') or s.get('narration') or '') for s in scenes)
 for i,scene in enumerate(scenes,1):scene['scene_number']=i
 script='\n\n'.join(str(s.get('scene_text') or s.get('narration') or '').strip() for s in scenes)
 assert script==candidate['script'].strip()
 status('independent story review',scene_count=len(scenes),script_chars=len(script))
 review=stage('02p_pawnshop_story_review',{'script':script,'scenes':scenes,'series_requirements':request['notes']},'Independently review this FINAL Japanese story, not the planning synopsis. Do not rewrite. Return JSON {verdict:"pass|repair",critical_issues:[{issue:"specific contradiction or explicit user requirement violation",scene_numbers:[n],quote:"verbatim script evidence",repair:"minimal repair"}],quality_notes:["honest minor observations"],checks:{modern_japan:{passed:true,evidence_quote:"verbatim"},transaction_rules:{passed:true,evidence_quote:"verbatim"},watch_custody:{passed:true,evidence_quote:"verbatim"},daughter_identity_and_timeline:{passed:true,evidence_quote:"verbatim"},indirect_narration:{passed:true,evidence_quote:"verbatim"},concrete_ending_without_sermon:{passed:true,evidence_quote:"verbatim"},alien_owner_and_cat_continuity:{passed:true,evidence_quote:"verbatim"}}}. Evidence must be from the actual final script. Do not demand that every character reveal alien identity or force the antagonist into episode 1; subtle hints are allowed. Treat genre fantasy as fantasy, not a factual-world error. Report actual contradictions in the established supernatural rules and object handoffs; no invented objections. Distinguish minor prose taste from critical factual continuity. No false approval.',lambda raw:validate_story_review(raw,script,('modern_japan','transaction_rules','watch_custody','daughter_identity_and_timeline','indirect_narration','concrete_ending_without_sermon','alien_owner_and_cat_continuity')))
 save('independent-story-review.json',review)
 if review.get('verdict')!='pass' or review.get('critical_issues') or not all(c.get('passed') is True for c in review['checks'].values()):
  status('story repair required',review=review);raise ValueError('Independent story review requires repair; see independent-story-review.json')
 status('visual prompts',scene_count=len(scenes),script_chars=len(script))
 cast=structure.get('character_anchors') or candidate.get('character_anchors') or {}
 references=BASE/'series-references';references.mkdir(exist_ok=True)
 attached=[]
 for source in [ROOT/'output/pawnshop-series/character-sheets-v1/owner_character_sheet.png',ROOT/'output/pawnshop-series/character-sheets-v1/cat_character_sheet.png',ROOT/'output/pawnshop-series/visual-bible-v2/01_barred_counter_empty.png']:
  target=references/source.name;shutil.copy2(source,target);attached.append(str(target.resolve()))
 for start in range(0,len(scenes),12):
  selected=scenes[start:start+12];ids=[number(s,i) for i,s in enumerate(selected,start+1)]
  filename=f'media-{ids[0]:03d}-{ids[-1]:03d}.json'
  def validate(raw):
   assert isinstance(raw,dict),'Media must be an object'
   rows=raw.get('scenes');assert isinstance(rows,list) and all(isinstance(r,dict) for r in rows) and [r['scene_number'] for r in rows]==ids,'Exact scene numbers required'
   for row in rows:
    assert isinstance(row.get('image_prompt'),str) and len(row['image_prompt'])>=160,'Detailed visual prompt missing'
    assert isinstance(row.get('shot_design'),dict) and row['shot_design'].get('composition'),'Composition missing'
    layers=row.get('layer_image_prompts',[])
    assert isinstance(layers,list) and all(isinstance(x,dict) for x in layers),'Layers must be objects'
    assert all(isinstance(x.get('id'),str) and x['id'].strip() for x in layers) and len({x['id'] for x in layers})==len(layers),'Layer IDs must be nonempty and unique'
    if 19<=row['scene_number']<=50:
     assert len(layers)>=2 and any(x.get('role')=='background' for x in layers),'Independent layered scene requires clean background and subject/prop layers'
     assert all(isinstance(x.get('prompt'),str) and len(x['prompt'])>=100 for x in layers),'Layer prompt too short'
     original=next(s for s in selected if s['scene_number']==row['scene_number'])
     required=(original.get('ae_effect_plan') or {}).get('asset_requirements',{}).get('required_layers') or []
     assert set(required).issubset({x.get('id') for x in layers}),'Missing required execution-layer IDs: '+str(required)
    else:assert not layers,'Only scenes 19-50 may request independently generated layers'
  media=None
  if (OUT/filename).exists():
   try:
    media=json.loads((OUT/filename).read_text());validate(media)
   except (ValueError,AssertionError,KeyError,TypeError):
    shutil.copy2(OUT/filename,OUT/(filename+'.invalid-'+str(time.time_ns())))
    media=None
  if media is None:
   context={'_local_image_paths':attached,'reference_image_roles':['Image 1: fixed female pawnshop proprietor; NOT the male guest or daughter','Image 2: fixed alien-created cat in ordinary cat form','Image 3: exact enclosed barred service window architecture'],'setting':request,'style':STYLE,'character_anchors':cast,'scenes':selected,'scope':{'single_image_ranges':['1-18','51-end'],'layered_range':[19,50]}}
   task='Author image production prompts from the supplied FINAL Japanese narration; do not rewrite narration. Return JSON {scenes:[{scene_number:n,image_prompt:"detailed unique English prompt",shot_design:{shot_size:"wide|medium|close_up|detail",camera_angle:"eye_level|high_angle|low_angle|overhead|oblique",subject_presence:"character_required|character_optional|environment_only|object_insert",subject_scale:"none|small|medium|large|detail",composition:"precise English framing",repetition_reason:""},layer_image_prompts:[{id:"exact execution layer ID",role:"background|character|foreground|prop|effect",prompt:"English independently authored full-canvas layer instruction"}]}]}. Include exactly the supplied scene numbers in order. Preserve exact established character faces/hair/costume and cat markings from the context. Only include visible participants; absent people mentioned by narration must not appear by default. Keep pawnshop architecture as the secured metal-bar service window, lower sliding transaction hatch, cat ledge and proprietor workspace INSIDE the booth. For scenes 19-50 include one separately authored layer prompt for EVERY asset_requirements.required_layers ID in the supplied AE plan, copying each ID exactly into id; preserve compatible role semantics. Author independently generated clean-background and aligned subject/prop layer prompts (plus motivated foreground/effect layers), preserving same canvas/perspective/light, transparent subject cutouts and no baked motion. For every other scene layer_image_prompts must be empty: exactly one flattened scene image. No video_prompt anywhere. Every image_prompt must be at least 160 characters, specific to the supplied situation, shot and era; no generic placeholder prompts. No slow zooms in artwork; camera movement is a later AE operation. Do not generate media or claim media exists.'
   media=stage('03p_media_'+str(ids[0]),context,task,validate);save(filename,media)
  for scene,row in zip(selected,media['scenes']):
   scene.update(image_prompt=row['image_prompt'],shot_design=row['shot_design'],layer_image_prompts=row['layer_image_prompts'],media_prompt_status='ready',video_prompt_required=False,visual_type='image',video_generation_mode='image')
   scene.pop('video_prompt',None)
  status('visual prompts',completed_scenes=ids[-1],total_scenes=len(scenes))
 policy=_plan_image_generation_efficiency(scenes,request,structure.get('ae_effect_plans') or [])
 assert {p['scene_number'] for p in policy['psd_layer_prompts']}==set(range(19,51)), 'Layer range must be exactly 19-50'
 # Keep legacy descriptive defaults consistent with the reviewed execution design.
 for scene in scenes:
  plan=scene.get('ae_effect_plan') or {}
  camera=(plan.get('execution_design') or {}).get('camera') or {}
  if camera.get('kind'):
   plan['camera']=camera['kind'];plan['fallback']='original_visual'
  if 19<=scene['scene_number']<=50:
   layers=scene['layer_image_prompts'];ids=[x['id'] for x in layers]
   scene['psd_layer_plan'].update(source='separately_authored_layer_generation',method='registered_individual_layer_pngs',required_layers=ids,optional_layers=[],layer_image_prompts=layers,prompt='\n\n'.join(x['id']+': '+x['prompt'] for x in layers))
   scene['image_generation_policy'].update(local_layer_separation=False,local_layer_source='none',psd_layer_generation_unit='registered_individual_layer_pngs',preferred_motion_source='reviewed_individual_layers_then_ae')
 for package in policy['psd_layer_prompts']:
  scene=scenes[package['scene_number']-1]
  package.update(method='registered_individual_layer_pngs',layer_image_prompts=scene['layer_image_prompts'],prompt=scene['psd_layer_plan']['prompt'])
 structure['ae_effect_plans']=[dict(s['ae_effect_plan'],scene_number=s['scene_number']) for s in scenes if (s.get('ae_effect_plan') or {}).get('enabled')]
 grids=[]
 for index,(first,last) in enumerate(grid_windows(len(scenes)),1):
  panels=[]
  for scene in scenes[first:last]:
   n=number(scene,1)
   panels.append({'position':['Top-Left','Top-Right','Bottom-Left','Bottom-Right'][len(panels)],'scene_number':n,'scene_id':scene.get('scene_id') or f'scene{n:03d}','panel_prompt':scene['image_prompt'],'shot_design':scene['shot_design']})
  grids.append({'grid_number':index,'scene_numbers':[p['scene_number'] for p in panels],'shared_style':STYLE,'negative_prompt':'No text, no captions, no watermarks, no borders, no grid lines, no dividers, correct anatomy.','panels':panels})
 grids=build_compact_image_grid_prompts(grids)
 validate_scene_image_prompt_readiness(scenes)
 validate_image_grid_prompt_readiness(scenes,grids,status='ready',require_status='ready',require_compact_template=True)
 metadata_file=OUT/'publish-metadata.json'
 def validate_meta(raw):
  assert isinstance(raw,dict),'Metadata must be an object'
  assert raw.get('title')==request['title'],'Keep exact title'
  assert isinstance(raw.get('description'),str) and len(raw['description'])>=250
  assert isinstance(raw.get('tags'),list) and len(raw['tags'])>=5 and all(isinstance(t,str) and t.strip() for t in raw['tags'])
 metadata=None
 if metadata_file.exists():
  try:
   metadata=json.loads(metadata_file.read_text());validate_meta(metadata)
  except (ValueError,AssertionError,KeyError,TypeError):
   shutil.copy2(metadata_file,OUT/('publish-metadata.invalid-'+str(time.time_ns())+'.json'));metadata=None
 if metadata is None:
  metadata=stage('04p_publish_metadata',{'title':request['title'],'script':script,'narrative_blueprint':candidate.get('narrative_blueprint')},'Write Japanese YouTube/user-web description metadata for this ORIGINAL fictional adult supernatural pawnshop tale, not a factual story. Return JSON {title:the exact supplied title,description:"250+ characters in Japanese, open with a clear fictional-story statement, intriguing premise without full ending spoilers",tags:[at least 5 Japanese topic tags],hashtags:[3 Japanese hashtags]}. No claims of actual footage, completed audio, video render or upload.',validate_meta);save('publish-metadata.json',metadata)
 structure.update(required_video_scene_count=0,video_scenes=0,image_layer_mode='hybrid',image_layer_scene_range={'start':19,'end':50},effect_scene_range={'start':19,'end':50},image_generation_policy=policy,psd_layer_prompts=policy['psd_layer_prompts'],psd_layer_scene_count=32,psd_layer_prompt_status='planned',image_grid_prompt_status='ready',image_grid_prompt_mode='direct_2x2_only',image_grid_prompts=grids,media_prompt_status='ready',scene_count=len(scenes),ae_scene_delivery='gcs',series_profile='modern_japanese_alien_pawnshop/v1')
 progress={'local_script_job_id':JOB,'registration_source':'codex_supervised_local_script_worker','script_sha256':hashlib.sha256(script.encode()).hexdigest(),'scene_count':len(scenes),'required_video_scene_count':0,'image_layer_scene_range':{'start':19,'end':50},'publish_metadata':metadata,'character_anchors':cast,'image_style':'실사','scene_image_count':0,'image_generation_status':'pending','has_tts_audio':False,'tts_completed':False,'subtitles_completed':False,'quality_notes':list(candidate.get('remaining') or [])+list(review.get('quality_notes') or []),'independent_story_review':review,'series_bible':'docs/pawnshop-series/SERIES_BIBLE_AND_TOPICS_2026-11-01.md','character_sheet_local_paths':['output/pawnshop-series/character-sheets-v1/owner_character_sheet.png','output/pawnshop-series/character-sheets-v1/cat_character_sheet.png'],'scene_assets_ready':False}
 payload={'topic':request['title'],'generated_title':request['title'],'category_id':2,'language':'ja','status':'pending','assigned_employee_email':'','assigned_at':None,'assigned_script_style':'story','assigned_image_style':'실사','assigned_duration_minutes':35,'recommended_duration_minutes':35,'total_scenes':len(scenes),'video_scenes':0,'image_scenes':len(scenes),'pregenerated_script':script,'pregenerated_script_status':'ready','pregenerated_structure':structure,'pregenerated_structure_status':'ready','publish_metadata':metadata,'narrative_blueprint':candidate.get('narrative_blueprint') or {},'script_quality_report':candidate.get('script_quality_report') or {},'progress_payload':progress}
 save('topic-registration-payload.json',payload)
 check="const fs=require('fs');const {load}=require('./scripts/std_web_runtime.cjs');const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));if(!load('preparedTopic').isPreparedUserTopic(p))throw Error('User-web eligibility failed');console.log('user-web eligibility passed')"
 subprocess.run(['node','-e',check,str(OUT/'topic-registration-payload.json')],cwd=ROOT,check=True)
 (OUT/'EPISODE_01_JA.md').write_text('# '+request['title']+'\n\n'+script+'\n',encoding='utf-8')
 notes=['# 1화 대본 검수와 제작 상태','',f"- 제목: {request['title']}",f"- 최종 씬: {len(scenes)}",f"- 일본어 본문: {len(script)}자",'- 계획 분량: 35분. 실제 음성 길이는 아직 측정하지 않음.','- 씬 1~18: 단일 이미지, 19~50: AE용 레이어, 51~마지막: 단일 이미지.','- 원본 동영상 요구 수: 0.','- 대본·씬별 이미지 프롬프트·레이어 프롬프트·소개문을 준비했으며 씬 이미지, TTS, 영상 렌더는 미완료.','', '## 독립 검수', '',f"- 판정: {review['verdict']}",f"- 미해결 핵심 문제: {len(review.get('critical_issues') or [])}"]
 for key,value in review['checks'].items():notes.append(f"- {key}: {value.get('passed')} — {value['evidence_quote']}")
 notes+=['','## 품질 메모','']+[f'- {item}' for item in (review.get('quality_notes') or ['별도 경미한 품질 메모 없음'])]
 notes+=['','## 수정 이력','','- 첫 초안 62씬의 글자 수 부족을 최소 보정.','- 청취 검수에서 지적한 기억의 변화 시점, 노트에 기록하는 시점, 반복되는 설명을 보완.','- 계약 만기일 계산과 신청/최종 수락 서명, 원본/사본 전달을 구분.','- 각 수정 전 원본과 이전 검수 결과는 별도 JSON/단계 캐시에 보존.']
 (OUT/'QUALITY_NOTES.md').write_text('\n'.join(notes)+'\n',encoding='utf-8')
 status('registering user web')
 params={'select':'id,topic,pregenerated_script,pregenerated_structure,progress_payload,status,language,assigned_employee_email','progress_payload->>local_script_job_id':'eq.'+JOB}
 rows,_=store.request('GET','topics_queue',params=params)
 assert len(rows)<=1,'Duplicate registration requires inspection'
 if not rows:
  # One POST attempt only; after an ambiguous response reconcile by durable marker.
  import requests
  base=os.environ['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
  try:
   response=requests.post(base+'/rest/v1/topics_queue',headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':'return=representation'},json=payload,timeout=90)
   response.raise_for_status();rows=response.json()
  except requests.RequestException:
   rows,_=store.request('GET','topics_queue',params=params)
   if not rows:raise
 topic=rows[0]
 # Re-running after a packaging repair updates this exact unassigned registration.
 if topic.get('pregenerated_structure')!=structure or topic.get('pregenerated_script')!=script:
  validate_registration_update(topic)
  store.request('PATCH','topics_queue',params={'id':'eq.'+str(topic['id']),'status':'eq.pending','assigned_employee_email':'eq.'},body=payload)
 rows,_=store.request('GET','topics_queue',params={'select':'id,pregenerated_script,pregenerated_structure,progress_payload,status,language','id':'eq.'+str(topic['id'])})
 if len(rows)!=1:raise ValueError('Registration readback requires exactly one topic')
 saved=rows[0];validate_registration_readback(saved,payload)
 save('registration-receipt.json',{'topic_id':topic['id'],'job_id':JOB,'title':request['title'],'script_chars':len(script),'scene_count':len(scenes),'planned_duration_seconds':2100,'script_sha256':progress['script_sha256'],'database_readback_verified':True,'user_web_eligibility':True,'registered_at':datetime.now(timezone.utc).isoformat()})
 # Link the completed request to the account verified in the authenticated user web.
 context_file=OUT/'web-registration-context.json'
 if context_file.exists():
  import uuid
  context=json.loads(context_file.read_text())
  submission_id=str(uuid.UUID(JOB))
  existing,_=store.request('GET','user_topic_submissions',params={'select':'id,owner_email,job_id','id':'eq.'+submission_id})
  submission={'id':submission_id,'owner_email':context['owner_email'],'title':request['title'],'status':'approved','request_data':request,'job_id':JOB,'review_note':'사용자 요청으로 대본 생성 및 검수 완료. 유저웹 주제 #'+str(topic['id']),'reviewed_at':datetime.now(timezone.utc).isoformat()}
  if not existing:store.request('POST','user_topic_submissions',body=submission)
  verified,_=store.request('GET','user_topic_submissions',params={'select':'id,owner_email,job_id,status','id':'eq.'+submission_id})
  assert verified and verified[0]['owner_email']==context['owner_email'] and verified[0]['job_id']==JOB
  save('user-submission-receipt.json',verified[0])
 # Record the explicit supervised publication only after database readback.
 bundle=store.get(JOB)
 final_candidate=copy.deepcopy(candidate)
 final_candidate.update(structure=structure,publish_metadata=metadata,user_web_topic_id=topic['id'],production_ready=False)
 if not (BASE/'candidate.script-only.json').exists():shutil.copy2(BASE/'candidate.json',BASE/'candidate.script-only.json')
 candidate_hash=hashlib.sha256(json.dumps(final_candidate,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 bundle['candidate']=final_candidate
 bundle['job'].update(status='completed',stage='일본어 대본 완성 · 유저 웹 등록 완료',published=True,published_topic_id=topic['id'],published_at=time.time(),updated_at=time.time(),candidate_hash=candidate_hash,supervised_publication_basis='Explicit user instruction in current chat; independent story and user-web readiness checks recorded')
 revision=store.save(bundle);bundle['job']['storage_revision']=revision;bundle['job'].update(sync_status='synced',sync_error='')
 (BASE/'candidate.json').write_text(json.dumps(final_candidate,ensure_ascii=False,indent=2),encoding='utf-8')
 (BASE/'job.json').write_text(json.dumps(bundle['job'],ensure_ascii=False,indent=2),encoding='utf-8')
 status('registered',topic_id=topic['id'],scene_count=len(scenes))
if __name__=='__main__':main()
