"""Register prepared episode 3 privately, preserving original script and truthful asset state."""
import copy,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env',override=False)
from worker.script_worker_store import ScriptStore
from worker.gcs_media_storage import _upload_gcs_file
from worker.cowork_scene_assets import _download_gcs_bytes
from worker.generation_validation import validate_registration_update,validate_registration_readback
OUT=ROOT/'output/pawnshop-series/episode-03'; JOB='8b6c78f054e445148286e8ad0c661610';BASE=ROOT/'output/codex-local-console'/JOB
store=ScriptStore()
def save(name,obj):
 p=OUT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2));t.replace(p)
def status(stage,**kw):save('registration-status.json',{'stage':stage,'updated_at':time.time(),**kw});print(stage,flush=True)
def upload(path,kind):
 sha=hashlib.sha256(path.read_bytes()).hexdigest();b,k,u=_upload_gcs_file(path,f'content-assets/pawnshop-series/episode-03/{kind}/{sha}.png','image/png')
 assert hashlib.sha256(_download_gcs_bytes(b,k)).hexdigest()==sha
 return {'url':u,'bucket':b,'path':k,'sha256':sha,'storage_readback_verified':True}
def main():
 status('waiting for prepared prompts and thumbnail')
 while not all((OUT/n).is_file() for n in ('prepared-candidate.json','thumbnail-art.png','thumbnail-final.png','thumbnail-review.json')):
  time.sleep(15)
 c=json.loads((OUT/'prepared-candidate.json').read_text());s=c['structure'];script=c['script'];sha=hashlib.sha256(script.encode()).hexdigest()
 assert json.loads((BASE/'candidate.json').read_text())['script']==script
 assert json.loads((OUT/'thumbnail-review.json').read_text()).get('visual_inspected') is True
 s['content_setting']=c['content_setting'];s['image_style']=c['image_style']
 anchors=s['character_anchors'];chars=[anchors['main_character'],*anchors['supporting_characters']]
 files=['naoto','owner','cat','fumiko','ono','clerk'];statuses={}
 for character,name in zip(chars,files):
  status('publishing character reference',character=name)
  info=upload(OUT/'character-references'/f'{name}.png','character-references')
  character.update(character_key='pawnshop-series-'+name if name in ('owner','cat') else 'pawnshop-episode03-'+name,
                   image_url=info['url'],gcs_path=info['path'],gcs_bucket=info['bucket'],image_sha256=info['sha256'],
                   image_source='builtin_image_gen' if name not in ('owner','cat') else 'reused_existing_series_reference',
                   reference_visual_review='output/pawnshop-series/episode-03/character-reference-review.json')
  statuses[name]=info
 s.update(main_character=chars[0],supporting_characters=chars[1:],character_reference_status='generated_visual_inspected')
 anchors['character_image_generation']={'status':'generated_visual_inspected','formal_face_distinctness_review':'pending','actual_reference_count':len(chars)}
 c.update(main_character=chars[0],supporting_characters=chars[1:],character_anchors=anchors)
 save('character-reference-publication.json',statuses)
 status('publishing reviewed thumbnail')
 art=upload(OUT/'thumbnail-art.png','thumbnail-background');final=upload(OUT/'thumbnail-final.png','thumbnail-final-preview')
 metadata=copy.deepcopy(c['publish_metadata']);metadata['description']='この作品は創作の物語です。\n\n'+metadata['description']
 metadata.update(thumbnail_url=final['url'],thumbnail_bg_url=art['url'])
 design=c['thumbnail_design'];design.update(bg_url=art['url'],editor_bg_url=art['url'],thumbnail_url=None,render_status='awaiting_user_save')
 progress={'local_script_job_id':JOB,'registration_source':'codex_supervised_local_script_worker','script_sha256':sha,'scene_count':len(s['scenes']),
           'required_video_scene_count':0,'publish_metadata':metadata,'character_anchors':anchors,'scene_image_count':0,
           'image_generation_status':'in_progress','scene_assets_ready':False,'has_tts_audio':False,'tts_completed':False,'subtitles_completed':False,
           'thumbnail_bg_url':art['url'],'thumbnail_final_preview_url':final['url'],'thumbnail_design':design,'thumbnail_hook_texts':c['thumbnail_hook_texts'],
           'thumbnail_image_prompt':c['thumbnail_image_prompt'],'thumbnail_completed':False,'thumbnail_generation_status':'completed','thumbnail_render_status':'awaiting_user_save',
           'quality_notes':['Character reference images manually inspected; formal automated face-distinctness check pending.','Actual scene images, TTS and AE render remain incomplete.','Thumbnail artwork/final preview generated; editable user Save remains separate.'],
           'layer_production_stage':'post_submission','generation_defaults_profile':'efficient_v1'}
 payload={'topic':c['generated_title'],'generated_title':c['generated_title'],'category_id':2,'language':'ja','status':'pending','assigned_employee_email':'','assigned_at':None,
          'assigned_script_style':'story','assigned_image_style':'실사','assigned_duration_minutes':35,'recommended_duration_minutes':35,
          'total_scenes':len(s['scenes']),'video_scenes':0,'image_scenes':len(s['scenes']),'pregenerated_script':script,'pregenerated_script_status':'ready',
          'pregenerated_structure':s,'pregenerated_structure_status':'ready','publish_metadata':metadata,'narrative_blueprint':c.get('narrative_blueprint') or {},'script_quality_report':c['script_quality_report'],'progress_payload':progress}
 save('topic-registration-payload.json',payload)
 subprocess.run(['node','-e',"const fs=require('fs');const{load}=require('./scripts/std_web_runtime.cjs');const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));if(!load('preparedTopic').isPreparedUserTopic(p))throw Error('prepared-topic check failed')",str(OUT/'topic-registration-payload.json')],cwd=ROOT,check=True)
 status('registering user web')
 params={'select':'id,pregenerated_script,pregenerated_structure,progress_payload,status,language,assigned_employee_email,assigned_at','progress_payload->>local_script_job_id':'eq.'+JOB}
 rows,_=store.request('GET','topics_queue',params=params);assert len(rows)<=1
 if not rows:
  import requests
  base=os.environ['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
  try:
   r=requests.post(base+'/rest/v1/topics_queue',headers={'apikey':key,'Authorization':'Bearer '+key,'Prefer':'return=representation'},json=payload,timeout=90);r.raise_for_status();rows=r.json()
  except requests.RequestException:
   rows,_=store.request('GET','topics_queue',params=params)
   if not rows:raise
 topic=rows[0]
 if topic.get('pregenerated_structure')!=s or topic.get('pregenerated_script')!=script:
  validate_registration_update(topic)
  store.request('PATCH','topics_queue',params={'id':'eq.'+str(topic['id']),'status':'eq.pending','assigned_employee_email':'eq.'},body=payload)
 saved,_=store.request('GET','topics_queue',params={'select':'id,pregenerated_script,pregenerated_structure,progress_payload,status,language','id':'eq.'+str(topic['id'])})
 assert len(saved)==1;validate_registration_readback(saved[0],payload)
 save('registration-receipt.json',{'topic_id':topic['id'],'job_id':JOB,'script_sha256':sha,'database_readback_verified':True,'user_web_eligibility':True,'scene_count':144,'actual_scene_images':0,'thumbnail_background':art,'thumbnail_final_preview':final})
 context=ROOT/'output/pawnshop-series/episode-02/web-registration-context.json'
 if context.exists():
  import uuid
  owner=json.loads(context.read_text())['owner_email'];submission_id=str(uuid.UUID(JOB))
  existing,_=store.request('GET','user_topic_submissions',params={'select':'id,owner_email,job_id','id':'eq.'+submission_id})
  if not existing:
   store.request('POST','user_topic_submissions',body={'id':submission_id,'owner_email':owner,'title':c['generated_title'],'status':'approved','request_data':json.loads((BASE/'request.json').read_text()),'job_id':JOB,'review_note':'Codex-supervised continuation requested by user; topic #'+str(topic['id'])})
  else:assert existing[0]['owner_email']==owner and existing[0]['job_id']==JOB
 c.update(publish_metadata=metadata,user_web_topic_id=topic['id'],thumbnail_bg_url=art['url'],thumbnail_final_preview_url=final['url'],thumbnail_completed=False,production_ready=False)
 c['remaining']=['실제 전체 씬 이미지 제작·게시','캐릭터 정식 얼굴 구별 검사','썸네일 편집기 최종 저장','TTS 및 실제 음성 길이 확인','제출 후 AE 레이어·최종 렌더','관리자 게시·YouTube 업로드는 별도']
 save('registered-candidate.json',c)
 bundle=store.get(JOB);assert bundle['candidate']['script']==script
 shutil.copy2(BASE/'candidate.json',BASE/'candidate.script-only.json') if not (BASE/'candidate.script-only.json').exists() else None
 bundle['candidate']=c;bundle['job'].update(status='completed',stage='3화 대본·썸네일 기획 및 이미지 프롬프트 · 유저웹 등록 완료 · 씬 제작 중',published=True,published_topic_id=topic['id'],updated_at=time.time(),remaining=c['remaining'],candidate_hash=hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
 revision=store.save(bundle);bundle['job'].update(storage_revision=revision,sync_status='synced',sync_error='')
 (BASE/'candidate.json').write_text(json.dumps(c,ensure_ascii=False,indent=2));(BASE/'job.json').write_text(json.dumps(bundle['job'],ensure_ascii=False,indent=2))
 for name in ('EPISODE_03_JA.md','EPISODE_03_SCENES_JA.md','QUALITY_NOTES.md'):shutil.copy2(OUT/name,ROOT/'docs/pawnshop-series/episode-03'/name)
 status('registered',topic_id=topic['id'])
if __name__=='__main__':
 try:main()
 except Exception as exc:status('execution failure',error_type=type(exc).__name__);raise
