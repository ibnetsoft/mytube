import copy,json,time
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from worker import script_manual_workflow as m
from worker import codex_local_console as console

SCRIPT={'scenes':[{'scene_id':'S1','title':'탈출','visual_action':'두 사람이 열린 통로를 확인한다.','spoken_blocks':[{'kind':'dialogue','speaker':'서진','text':'같이 나가자.'}]}],'quality_notes':[]}
OUTPUTS=[SCRIPT,{'cuts':[{'cut_id':'C1','scene_id':'S1','image_prompt':'같은 복장과 부상 상태, 열린 통로를 보는 두 사람의 2D 중경.','references':['기존 서진 참조 · 확인 필요']}],'quality_notes':[]},{'selections':[{'cut_id':'C1','selected':False,'reason':'정지 반응 컷으로 충분하다.','video_prompt':''}],'quality_notes':[]},{'directions':[{'cut_id':'C1','ae_instruction':'고정 화면. 전환은 하드 컷. 얼굴과 문자는 보호한다.','timing_note':'실제 음성 저장 후 대사 앵커에 연결한다.'}],'quality_notes':[]},{'cues':[{'id':'hit','cut_id':'C1','prompt':'Dry stone impact, no human speech or music','duration_seconds':1,'offset_seconds':0,'volume_db':-18,'reason':'단발 접촉'}],'quality_notes':[]}]
class Runner:
 def __init__(self):self.calls=[]
 def _stage(self,identity,name,context,task):
  self.calls.append(name)
  if name.endswith('_review'):return {'passed':True,'issues':[],'evidence':'제공된 씬과 대사 계획을 검토했다. 실제 원화 검토는 아니다.'}
  return copy.deepcopy(OUTPUTS[int(name.split('_')[1])-1])

def seed(tmp_path):
 j=console.Jobs(tmp_path);identity='a'*32;candidate=m.initial(identity,{'mode':'new','manual_stages':True},lambda _:None,runner=Runner())
 j.rows[identity]={'id':identity,'title':'QA','mode':'new','status':'awaiting_approval','worker_id':j.worker_id,'candidate_hash':m.digest(candidate),'created_at':time.time(),'auto_delivery_requested':False}
 m.write(tmp_path/identity/'candidate.json',candidate);m.write(tmp_path/identity/'request.json',{'mode':'new','manual_stages':True})
 app=FastAPI();m.register(app,j);return j,identity,TestClient(app)

def call(j,identity,c,step,action,**extra):
 return c.post(f'/api/jobs/{identity}/manual-stage',json={'step':step,'action':action,'expected_hash':j.rows[identity]['candidate_hash'],**extra})
def wait(j):
 end=time.monotonic()+3
 while j.inflight and time.monotonic()<end:time.sleep(.01)
 assert not j.inflight

def test_script_only_runs_script_and_its_review():
 r=Runner();p=m.initial('qa',{'mode':'new'},lambda _:None,runner=r)
 assert r.calls==['manual_1_1','manual_1_1_review']
 assert [s['status'] for s in p['manual_workflow']['stages']]==['review','pending','pending','pending','pending']
 assert '화면 설명' in p['script'] and '대사 · 서진' in p['script']
 assert console.digest(p)==m.digest(p)

def test_explicit_steps_edits_invalidation_and_stale_requests(tmp_path,monkeypatch):
 j,i,c=seed(tmp_path);calls=[]
 def gen(index,*args,**kw):calls.append(index);return copy.deepcopy(OUTPUTS[index])
 monkeypatch.setattr(m,'generate',gen)
 assert call(j,i,c,2,'generate').status_code==409
 for step in range(1,6):
  if step>1:
   assert call(j,i,c,step,'generate').status_code==200;wait(j)
  before=len(calls);assert call(j,i,c,step,'approve').status_code==200;assert len(calls)==before
 assert calls==[1,2,3,4] and j.rows[i]['status']=='completed'
 old_hash=j.rows[i]['candidate_hash'];out=copy.deepcopy(SCRIPT);out['scenes'][0]['spoken_blocks'][0]['text']='먼저 길을 확인하자.'
 assert call(j,i,c,1,'save',output=out).status_code==200
 w=j.bundle(i)['candidate']['manual_workflow'];assert [s['status'] for s in w['stages']]==['review','stale','stale','stale','stale']
 assert c.post(f'/api/jobs/{i}/manual-stage',json={'step':1,'action':'approve','expected_hash':old_hash}).status_code==409
 assert call(j,i,c,3,'generate').status_code==409
 assert j.rows[i]['auto_delivery_requested'] is False
 j.pool.shutdown()

def test_failure_preserves_approved_input_and_can_retry_just_that_step(tmp_path,monkeypatch):
 j,i,c=seed(tmp_path);assert call(j,i,c,1,'approve').status_code==200
 def fail(*a,**k):raise RuntimeError('PRIVATE SECRET')
 monkeypatch.setattr(m,'generate',fail);assert call(j,i,c,2,'generate').status_code==200;wait(j)
 w=j.bundle(i)['candidate']['manual_workflow'];assert w['stages'][0]['status']=='approved' and w['stages'][1]['status']=='failed'
 assert 'PRIVATE' not in j.rows[i]['error']
 monkeypatch.setattr(m,'generate',lambda index,*args:copy.deepcopy(OUTPUTS[index]));assert call(j,i,c,2,'generate').status_code==200;wait(j)
 assert j.bundle(i)['candidate']['manual_workflow']['stages'][1]['status']=='review'
 j.pool.shutdown()

def test_ownership_and_legacy_approval_cannot_bypass_stage_review(tmp_path):
 j,i,c=seed(tmp_path)
 with pytest.raises(ValueError,match='단계별'):j.approve(i,j.rows[i]['candidate_hash'])
 j.rows[i]['worker_id']='another-machine';assert call(j,i,c,1,'approve').status_code==409
 j.pool.shutdown()

def test_video_zero_selection_and_unknown_cut_rejection():
 w={'stages':[{'output':SCRIPT},{'output':OUTPUTS[1]}]};m.validate(2,OUTPUTS[2],w)
 bad=copy.deepcopy(OUTPUTS[2]);bad['selections'][0]['cut_id']='different'
 with pytest.raises(ValueError):m.validate(2,bad,w)

def test_manual_never_enters_delivery_even_if_old_flag_is_set():
 from worker.script_delivery_supervisor import eligible
 job={'worker_id':'here','auto_delivery_requested':True,'status':'awaiting_approval'};request={'mode':'new','settings_confirmed':True,'category_id':'18','manual_stages':True}
 assert not eligible(job,request,'here')

def test_new_default_stops_after_script_and_legacy_retry_keeps_saved_policy(tmp_path,monkeypatch):
 from worker import codex_local_workflow
 monkeypatch.setattr(codex_local_workflow,'produce',lambda identity,request,*args,**kw:m.initial(identity,request,lambda _:None,runner=Runner()))
 j=console.Jobs(tmp_path);r=console.StartRequest(mode='new',settings_confirmed=True,title='QA fixture',category='직접 입력')
 job=j.start(r,None);wait(j)
 b=j.bundle(job['id']);assert b['request']['manual_stages'] is True
 assert b['job']['auto_delivery_requested'] is False and b['job']['status']=='awaiting_approval'
 assert [s['status'] for s in b['candidate']['manual_workflow']['stages']]==['review','pending','pending','pending','pending']
 j.pool.shutdown()

def test_review_failure_is_kept_as_notes_instead_of_a_false_pass():
 class FailedReview(Runner):
  def _stage(self,identity,name,context,task):
   if name.endswith('_review'):return {'passed':False,'issues':['반응 장면 반복'],'evidence':'제공된 계획에서 반응이 반복된다.'}
   return super()._stage(identity,name,context,task)
 p=m.initial('qa',{'mode':'new'},lambda _:None,runner=FailedReview())
 out=p['manual_workflow']['stages'][0]['output'];assert out['review']['passed'] is False and out['quality_notes']

def test_durable_reservation_failure_launches_no_generation(tmp_path,monkeypatch):
 from worker.script_worker_store import StoreUnavailable
 j,i,c=seed(tmp_path);assert call(j,i,c,1,'approve').status_code==200
 j.store=object();monkeypatch.setattr(j,'load',lambda identity:j.bundle(identity))
 monkeypatch.setattr(j,'sync',lambda *a,**k:(_ for _ in ()).throw(StoreUnavailable('Database 保存遅延')))
 calls=[];monkeypatch.setattr(m,'generate',lambda *a,**k:calls.append(a))
 assert call(j,i,c,2,'generate').status_code==502
 assert not calls and not j.inflight and j.rows[i]['status']=='failed'
 j.pool.shutdown()

def test_retry_of_saved_legacy_job_does_not_switch_to_manual(tmp_path,monkeypatch):
 from worker import codex_local_workflow
 seen=[]
 def old_produce(identity,request,*args,**kwargs):seen.append(request);return {'script':'기존 방식 검증용 결과'}
 monkeypatch.setattr(codex_local_workflow,'produce',old_produce)
 j=console.Jobs(tmp_path);i='b'*32;j.rows[i]={'id':i,'title':'legacy','status':'failed','mode':'new','worker_id':j.worker_id,'created_at':time.time()}
 req=console.StartRequest(mode='new',title='legacy',category='직접 입력')
 j.start(req,None,retry_of=i,identity=i);wait(j)
 assert seen[0]['manual_stages'] is False and 'manual_workflow' not in j.rows[i]
 j.pool.shutdown()

def test_per_scene_prompt_refs_isolated_and_source_edit_invalidation(tmp_path,monkeypatch):
 from worker import script_scene_prompts as sp
 j,i,c=seed(tmp_path)
 monkeypatch.setattr(sp,'catalog',lambda:[{'id':'hero','label':'1화 서진','path':'/verified/ref.png','sha256':'a'*64}])
 captured=[]
 def generate(identity,scene,neighbors,request,refs,feedback,revision):
  captured.append((scene,refs));return '참조 인물의 얼굴과 복장 유지. 부러진 단도 상태는 별도 필요.'
 monkeypatch.setattr(sp,'generate_scene',generate)
 def scene(action,**extra):return c.post(f'/api/jobs/{i}/scene-image-prompt',json={'action':action,'scene_id':'S1','expected_hash':j.rows[i]['candidate_hash'],'reference_ids':['hero'],**extra})
 assert scene('generate').status_code==200;wait(j)
 w=j.bundle(i)['candidate']['manual_workflow'];assert w['stages'][0]['status']=='review'
 assert all(s['status']=='pending' for s in w['stages'][1:])
 assert w['scene_image_prompts']['S1']['references'][0]['sha256']=='a'*64
 assert captured[0][0]['scene_id']=='S1'
 assert scene('save',image_prompt='편집한 프롬프트').status_code==200
 output=copy.deepcopy(SCRIPT);output['scenes'][0]['visual_action']='다른 행동'
 assert call(j,i,c,1,'save',output=output).status_code==200
 assert j.bundle(i)['candidate']['manual_workflow']['scene_image_prompts']['S1']['status']=='stale'
 assert c.post(f'/api/jobs/{i}/scene-image-prompt',json={'action':'generate','scene_id':'../bad','expected_hash':j.rows[i]['candidate_hash']}).status_code==409
 assert c.get('/api/manual-reference-images/unknown/file').status_code==404
 j.pool.shutdown()

def test_scene_prompt_failure_preserves_text_and_rejects_unlisted_assets(tmp_path,monkeypatch):
 from worker import script_scene_prompts as sp
 j,i,c=seed(tmp_path);monkeypatch.setattr(sp,'catalog',lambda:[])
 def action(**kw):return c.post(f'/api/jobs/{i}/scene-image-prompt',json={'action':'save','scene_id':'S1','expected_hash':j.rows[i]['candidate_hash'],**kw})
 assert action(reference_ids=['not-an-asset']).status_code==409
 assert action(image_prompt='이전 사용자 프롬프트').status_code==200
 def fail(*a):raise RuntimeError('SECRET')
 monkeypatch.setattr(sp,'generate_scene',fail)
 assert action(action='generate').status_code==200;wait(j)
 e=j.bundle(i)['candidate']['manual_workflow']['scene_image_prompts']['S1']
 assert e['image_prompt']=='이전 사용자 프롬프트' and e['status']=='failed'
 assert 'SECRET' not in json.dumps(e)
 j.pool.shutdown()

def test_problem_record_blocks_actual_arguments_and_survives_readback(tmp_path,monkeypatch):
 from worker import wuxia_generation_gate as g
 monkeypatch.setattr(g,'STATE',tmp_path/'policies')
 j,i,c=seed(tmp_path)
 def quality(action,data=None):return c.post(f'/api/jobs/{i}/scene-quality',json={'action':action,'scene_id':'S1','expected_hash':j.rows[i]['candidate_hash'],'data':data or {}})
 assert quality('finding',{'rule_id':'anatomical_side','evidence':'오른팔에 왼손 연결'}).status_code==200
 assert j.bundle(i)['candidate']['manual_workflow']['quality_control']['S1']['image_use_status']=='excluded'
 assert not quality('preflight').json()['ready']
 assert quality('prepare_arguments').status_code==409
 assert quality('resolve_finding',{'index':0,'evidence':'수정 후보 준비, 실제 픽셀 검수 대기'}).status_code==200
 assert j.bundle(i)['candidate']['manual_workflow']['quality_control']['S1']['image_use_status']=='review_required'
 assert quality('prepare_arguments').status_code==409
 j.pool.shutdown()

def test_pending_recovery_result_remains_readable_without_cloud_lock(tmp_path):
 j,i,c=seed(tmp_path);j.rows[i]['sync_status']='pending'
 class Unavailable:
  def get(self,*a):raise AssertionError('pending read must not request cloud')
 class BusyCloudLock:
  def __enter__(self):raise AssertionError('pending read must not wait on cloud I/O')
  def __exit__(self,*a):pass
 j.store=Unavailable();j.lock=BusyCloudLock()
 assert j.load(i)['candidate']['script']
 j.pool.shutdown()

def test_pending_manual_edit_retains_cloud_revision_without_network(tmp_path):
 j,i,c=seed(tmp_path);j.rows[i].update(sync_status='pending',storage_revision=32)
 class Offline:
  def save(self,*a):raise AssertionError('known offline edit must remain local')
 j.store=Offline();edited=copy.deepcopy(SCRIPT);edited['scenes'][0]['title']='수정된 씬'
 assert call(j,i,c,1,'save',output=edited).status_code==200
 assert j.rows[i]['storage_revision']==32 and j.rows[i]['sync_status']=='pending'
 j.pool.shutdown()

def test_legacy_four_step_job_can_explicitly_start_fifth_without_rewriting_prior_outputs(tmp_path,monkeypatch):
 j,i,c=seed(tmp_path);bundle=j.bundle(i);w=bundle['candidate']['manual_workflow'];w['stages']=w['stages'][:4]
 for n,s in enumerate(w['stages']):s.update(status='approved',output=copy.deepcopy(OUTPUTS[n]),approved_hash=m.digest(OUTPUTS[n]))
 old=copy.deepcopy(w['stages']);candidate=m.package(w,bundle['request']);m.write(tmp_path/i/'candidate.json',candidate);j.rows[i]['candidate_hash']=m.digest(candidate)
 monkeypatch.setattr(m,'generate',lambda index,*args:copy.deepcopy(OUTPUTS[index]))
 assert call(j,i,c,5,'generate').status_code==200;wait(j)
 result=j.bundle(i)['candidate'];assert result['manual_workflow']['stages'][:4]==old
 assert result['structure']['sfx_generation_plan']['status']=='review'
 assert call(j,i,c,5,'approve').status_code==200
 assert j.bundle(i)['candidate']['structure']['sfx_generation_plan']['status']=='approved'
 j.pool.shutdown()

def test_nonspoken_channels_preserved_but_excluded_from_voice():
 out=copy.deepcopy(SCRIPT)
 out['scenes'][0].update(sfx=['돌 파열음'],screen_text=['무혼록 각성'])
 m.validate(0,out)
 w={'stages':[{'output':out}]+[{} for _ in range(3)]}
 p=m.package(w,{})
 assert '[SFX: 돌 파열음]' in p['script']
 assert p['structure']['scenes'][0]['scene_text']=='같이 나가자.'
 assert p['structure']['scenes'][0]['screen_text']==['무혼록 각성']
 out['scenes'][0]['sfx']='돌 파열음'
 with pytest.raises(ValueError):m.validate(0,out)
