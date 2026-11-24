"""Executable preparation/review contract. It validates evidence, not visual truth.
Never invokes an image model or promotes a failed image through textual compliance.
"""
import copy,hashlib,json,os,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SEED=ROOT/'docs/wuxia-generation-rules.json'
STATE=ROOT/'output/codex-local-console/wuxia-rule-updates'
LOCK=threading.RLock()

def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def write(path,v):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2));os.replace(tmp,path)
def policy():
 seed=json.loads(SEED.read_text());p=copy.deepcopy(seed)
 if (STATE/'active.json').exists():
  update=json.loads((STATE/'active.json').read_text())
  merged={r['id']:r for r in p['rules']}
  merged.update({r['id']:r for r in update['rules']})
  p['rules']=list(merged.values());p['update_revision']=update['revision']
 assert p['rules'] and len({r['id'] for r in p['rules']})==len(p['rules'])
 p['guidance_documents']={}
 for name in ('SCRIPT_WORKER_PRODUCTION_GUIDE.md','wuxia-webtoon-production-defaults.md','WUXIA_SERIES_DELIVERY.md','WUXIA_SERIES_PLAN_03_50.md','wuxia-props/PROP_BIBLE.md'):
  file=ROOT/'docs'/name
  if file.exists():p['guidance_documents'][name]=hashlib.sha256(file.read_bytes()).hexdigest()
 p['sha256']=digest(p);return p

def instruction():
 p=policy();return '[실행 지침 '+p['contract']+' / SHA '+p['sha256']+']\n'+'\n'.join(r['id']+' · '+r['instruction'] for r in p['rules'])+'\n지침을 읽은 것과 실제 입력/픽셀 검수 완료는 구분한다. 누락 증거는 생성 전 준비 필요로 보고하고 승인 사실을 만들지 않는다.'

def update_rule(expected,identity,title,text,reason):
 import re
 with LOCK:
  p=policy()
  if expected!=p['sha256']:raise ValueError('지침 버전이 변경됐습니다. 다시 확인하세요.')
  if not re.fullmatch('[a-z][a-z0-9_]{2,79}',identity) or identity in {r['id'] for r in p['rules']}:raise ValueError('새 개선 항목의 고유 ID가 필요합니다.')
  if not all(isinstance(v,str) and v.strip() for v in (title,text,reason)) or len(text)>4000:raise ValueError('문제 근거와 적용할 개선 지침을 입력하세요.')
  current=json.loads((STATE/'active.json').read_text()) if (STATE/'active.json').exists() else {'revision':0,'rules':[]}
  write(STATE/'history'/f'{p["sha256"]}.json',p)
  current['revision']+=1;current['rules'].append({'id':identity,'title':title,'instruction':text,'reason':reason,'updated_at':time.time(),'authority':'explicit_local_operator_update'})
  write(STATE/'active.json',current);return policy()

def verified_file(ref):
 from PIL import Image
 path=Path(ref.get('path','')).resolve()
 if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError('프로젝트 안의 실제 참조 파일이 필요합니다.')
 sha=hashlib.sha256(path.read_bytes()).hexdigest()
 if sha!=ref.get('sha256'):raise ValueError('참조 원화가 변경됐습니다. 다시 검토하세요.')
 with Image.open(path) as im:im.verify()
 return str(path)

def review_issues(review,sha,p=None):
 p=p or policy();errors=[]
 if not isinstance(review,dict):return ['현재 원화의 실제 픽셀 검수 기록 필요']
 if review.get('source_sha256')!=sha:errors.append('검수 대상 원화 SHA 불일치')
 if review.get('policy_sha256')!=p['sha256']:errors.append('최신 개선 지침으로 재검수 필요')
 for rule in p['rules']:
  check=review.get('checks',{}).get(rule['id'],{})
  if check.get('verdict') not in ('pass','not_applicable') or not str(check.get('evidence','')).strip():errors.append(rule['title']+' 확인 필요')
  if check.get('verdict')=='not_applicable' and rule['id']!='causal_contact':errors.append(rule['title']+' 검사를 생략할 수 없음')
  if check.get('verdict')=='pass':
   regions=check.get('regions')
   if not isinstance(regions,list) or not regions:errors.append(rule['title']+' 관찰 위치 필요')
   elif any(not isinstance(box,list) or len(box)!=4 or any(type(x) not in (int,float) or not 0<=x<=1 for x in box) or box[0]>=box[2] or box[1]>=box[3] for box in regions):errors.append(rule['title']+' 관찰 좌표 오류')
 return errors

def exclude_source(sha,reason):
 with LOCK:
  path=STATE/'excluded-sources.json';items=json.loads(path.read_text()) if path.exists() else {}
  items[sha]={'reason':reason,'at':time.time()};write(path,items)

def assert_sources_usable(states):
 path=STATE/'excluded-sources.json';items=json.loads(path.read_text()) if path.exists() else {}
 for s in states:
  if s.get('sha256') in items:raise ValueError('사용 제외된 원화입니다. 수정한 새 원화의 실제 검수가 필요합니다.')

def preflight(scene,plan):
 p=policy();errors=[];refs=[]
 if not isinstance(plan,dict):plan={}
 for key,label in [('scene_id','씬'),('source_hash','대본 버전'),('policy_sha256','개선 지침 버전')]:
  expected={'scene_id':scene['scene_id'],'source_hash':digest(scene),'policy_sha256':p['sha256']}[key]
  if plan.get(key)!=expected:errors.append(label+' 연결 필요')
 for k,label in [('prior_state','직전 상태'),('current_state','이번 상태'),('result_state','다음 결과'),('reuse_plan','고정 영역과 새로 그리는 영역'),('pose_plan','팔·손·다리의 좌우와 접촉 자세'),('camera_plan','카메라와 공간 배치')]:
  if not str(plan.get(k,'')).strip():errors.append(label+' 필요')
 applications=plan.get('rule_applications',{})
 for rule in p['rules']:
  entry=applications.get(rule['id'],{}) if isinstance(applications,dict) else {}
  if not isinstance(entry,dict) or not all(isinstance(entry.get(k),str) and entry[k].strip() for k in ('observation','input_action','verify_after_generation')):
   errors.append(rule['title']+'：생성 전 관찰·입력 반영·생성 후 확인 계획 필요')
 previous=plan.get('previous_art') or {}
 try:
  verified_file(previous);assert_sources_usable([previous])
 except (ValueError,OSError):errors.append('사용 가능한 직전 실제 원화·SHA 필요 (반려 원화의 다음 컷 참조 금지)')
 if not str(previous.get('observed_detail','')).strip() or not previous.get('regions'):errors.append('직전 원화에서 확인한 부위·관찰 위치 필요')
 if type(plan.get('contact_required')) is not bool:errors.append('접촉 동작 여부 확인 필요')
 if plan.get('contact_required'):
  contact=plan.get('contact',{})
  for k in ('target_region','visible_structure','mechanism','consequence','setup_cut'):
   if not str(contact.get(k,'')).strip():errors.append('접촉의 부위·구조·작동·결과·선행 컷 확인 필요');break
 for ref in plan.get('assets',[]):
  try:
   refs.append(verified_file(ref))
   if not (plan.get('repair_required') is True and ref.get('role')=='repair_target'):assert_sources_usable([{'sha256':ref.get('sha256')}])
  except (ValueError,OSError):errors.append('고정 자산 원본·SHA 불일치')
  if not ref.get('asset_id') or not ref.get('state') or ref.get('reviewed') is not True:errors.append('실제 검토한 고정 자산 ID·상태 필요')
 if not refs:errors.append('고정 인물·소품·공간 자산 필요')
 if len(set(refs))>5:errors.append('이미지 도구의 참조 첨부는 최대 5개입니다. 필요한 자산 구성을 정리하세요.')
 roles={r.get('role') for r in plan.get('assets',[])}
 if not {'style','structure'}.issubset(roles):errors.append('화풍과 공간/자세 구조 자료를 각각 연결하세요.')
 for need in plan.get('required_asset_states',[]):
  if not any(r.get('asset_id')==need.get('asset_id') and r.get('state')==need.get('state') for r in plan.get('assets',[])):errors.append('필요한 사건 상태 자산 누락: '+str(need))
 if not isinstance(plan.get('actor_states'),list) or not plan.get('actor_states'):errors.append('화면 밖 인물을 포함한 위치·동작 상태표 필요')
 else:
  for actor in plan['actor_states']:
   if any(not actor.get(k) for k in ('id','position','facing','action_phase')):errors.append('인물/석상의 위치·방향·동작 단계 누락')
 return {'ready':not errors,'issues':list(dict.fromkeys(errors)),'policy_sha256':p['sha256'],'reference_paths':list(dict.fromkeys(refs)) if not errors else []}

def prepare_scene_imagegen_arguments(scene,prompt,plan):
 result=preflight(scene,plan)
 if not result['ready']:raise ValueError('생성 입력 준비 필요: '+' / '.join(result['issues']))
 return {'prompt':prompt+'\n\n'+instruction()+'\n\n실제 준비 상태표: '+json.dumps(plan,ensure_ascii=False),'referenced_image_paths':result['reference_paths']}, {'contract':policy()['contract'],'policy_sha256':result['policy_sha256'],'plan_sha256':digest(plan),'source_hash':digest(scene),'review_required':True}

def register(app,jobs,persist):
 from fastapi import HTTPException
 from pydantic import BaseModel,Field
 class QualityAction(BaseModel):
  action:str
  expected_hash:str=Field(min_length=64,max_length=64)
  scene_id:str=Field(min_length=1,max_length=80)
  data:dict=Field(default_factory=dict)
 class RuleUpdate(BaseModel):
  expected_hash:str
  rule_id:str
  title:str
  instruction:str=Field(max_length=4000)
  reason:str=Field(max_length=4000)
 globals()['WuxiaQualityAction']=QualityAction;globals()['WuxiaRuleUpdate']=RuleUpdate
 @app.get('/api/jobs/{identity}/assets/file/{cut_id}')
 def reviewed_image(identity:str,cut_id:str):
  from fastapi.responses import FileResponse
  try:
   b=jobs.load(identity)
   for q in b.get('candidate',{}).get('manual_workflow',{}).get('quality_control',{}).values():
    for candidate in reversed(q.get('candidates',[])):
     asset=candidate.get('asset',{})
     if asset.get('cut_id')!=cut_id:continue
     if candidate.get('use_status')!='reviewed' or review_issues(candidate.get('review'),asset.get('sha256')):raise ValueError('해당 원화는 실제 재검수가 필요합니다.')
     assert_sources_usable([asset]);path=verified_file(asset);return FileResponse(path)
   raise ValueError('검수된 컷 원화가 없습니다.')
  except (ValueError,OSError) as e:raise HTTPException(409,str(e)) from e
 @app.get('/api/wuxia-generation-policy')
 def get_policy():return policy()
 @app.post('/api/wuxia-generation-policy')
 def change_policy(body:RuleUpdate):
  try:return update_rule(body.expected_hash,body.rule_id,body.title,body.instruction,body.reason)
  except ValueError as e:raise HTTPException(409,str(e)) from e
 @app.post('/api/jobs/{identity}/scene-quality')
 def quality(identity:str,body:QualityAction):
  try:
   with jobs.lock:
    b=jobs.load(identity);j=b['job'];c=copy.deepcopy(b['candidate']);w=c.get('manual_workflow')
    if not w or j.get('worker_id')!=jobs.worker_id or j.get('published') or j['status'] in ('canceled','cancelled'):raise ValueError('이 컴퓨터의 편집 가능한 수동 작업을 선택하세요.')
    if jobs.busy() or digest(c)!=body.expected_hash:raise ValueError('진행 중이거나 결과가 변경됐습니다. 다시 확인하세요.')
    scene=next((s for s in w['stages'][0].get('output',{}).get('scenes',[]) if s['scene_id']==body.scene_id),None)
    if not scene:raise ValueError('현재 대본의 씬을 선택하세요.')
    if len(json.dumps(body.data))>150000:raise ValueError('검토 기록이 너무 큽니다.')
    q=w.setdefault('quality_control',{}).setdefault(body.scene_id,{'findings':[]})
    if body.action in ('preflight','prepare_arguments'):
     result=preflight(scene,q.get('plan'))
     repair_shas={a.get('sha256') for a in q.get('plan',{}).get('assets',[]) if a.get('role')=='repair_target'} if q.get('plan',{}).get('repair_required') is True else set()
     if any(f.get('status')=='open' and f.get('asset',{}).get('sha256') not in repair_shas for f in q.get('findings',[])):
      result['ready']=False;result['reference_paths']=[];result['issues'].append('미해결 문제를 근거와 함께 해결하고 생성 계획을 다시 확인하세요.')
     if body.action=='preflight':return result
     if not result['ready']:raise ValueError('생성 입력 준비 필요: '+' / '.join(result['issues']))
     entry=w.get('scene_image_prompts',{}).get(body.scene_id,{})
     if entry.get('source_hash')!=digest(scene) or not entry.get('image_prompt'):raise ValueError('현재 대본에 맞는 이미지 프롬프트가 필요합니다.')
     selected=q['plan'].get('cuts',{}).get(body.data.get('cut_id')) if body.data.get('cut_id') else None
     if body.data.get('cut_id') and not selected:raise ValueError('저장된 컷별 계획을 선택하세요.')
     selected_plan={**q['plan'],**selected.get('plan_overrides',{})} if selected else q['plan']
     selected_plan={k:v for k,v in selected_plan.items() if k!='cuts'}
     args,receipt=prepare_scene_imagegen_arguments(scene,selected['image_prompt'] if selected else entry['image_prompt'],selected_plan)
     q['prepared_input_receipt']=receipt
     q.setdefault('prepared_cut_receipts',{})[body.data.get('cut_id','scene')]=receipt
     w['revision']+=1
     from worker.script_manual_workflow import package
     persist(identity,package(w,b['request'],c.get('applied_guidelines')),status='awaiting_approval',stage='이미지 생성 입력 준비 · 실제 원화 검수는 별도',error='')
     return {'arguments':args,'receipt':receipt}
    if body.action=='save_plan':q['plan']=body.data;q['preflight']=preflight(scene,body.data)
    elif body.action=='finding':
     if body.data.get('rule_id') not in {r['id'] for r in policy()['rules']} or not str(body.data.get('evidence','')).strip():raise ValueError('검사 항목과 실제 발견한 문제를 입력하세요.')
     if body.data.get('asset'):
      verified_file(body.data['asset']);exclude_source(body.data['asset']['sha256'],body.data['evidence']);q.setdefault('candidates',[]).append({'asset':body.data['asset'],'use_status':'excluded'})
     finding={**body.data,'source_hash':digest(scene),'policy_sha256':policy()['sha256'],'recorded_at':time.time(),'status':'open'}
     q['findings'].append(finding)
     # A report never approves an image; all existing candidates are held until separately re-reviewed.
     for asset in q.get('candidates',[]):asset['use_status']='excluded';asset.pop('review',None)
     q['image_use_status']='excluded'
    elif body.action=='record_review':
     ref=body.data.get('asset',{});verified_file(ref);review=body.data.get('review');issues=review_issues(review,ref.get('sha256'))
     if any(f.get('status')=='open' for f in q.get('findings',[])):issues.append('미해결 문제 기록 있음 · 근거와 함께 해결 처리 필요')
     q.setdefault('candidates',[]).append({'asset':ref,'review':review,'review_issues':issues,'use_status':'excluded' if issues else 'reviewed'})
     q['image_use_status']='excluded' if issues else 'reviewed'
    elif body.action=='resolve_finding':
     n=body.data.get('index');evidence=body.data.get('evidence','')
     if not isinstance(n,int) or n<0 or n>=len(q.get('findings',[])) or not str(evidence).strip():raise ValueError('수정 전후의 실제 검토 근거가 필요합니다.')
     q['findings'][n].update(status='resolved',resolution=evidence)
     # Resolving text does not approve pixels.
     q['image_use_status']='review_required'
    else:raise ValueError('지원하지 않는 검토 작업입니다.')
    w['revision']+=1
    from worker.script_manual_workflow import package
    result=package(w,b['request'],c.get('applied_guidelines'))
    persist(identity,result,status='awaiting_approval',stage='생성 준비·원화 재검토 대기',error='')
    return {'saved':True,'preflight':q.get('preflight'),'image_use_status':q.get('image_use_status','review_required')}
  except (ValueError,KeyError,OSError) as e:raise HTTPException(409,str(e)) from e
