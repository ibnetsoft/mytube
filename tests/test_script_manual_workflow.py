import copy,json,time
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from worker import script_manual_workflow as m
from worker import codex_local_console as console

SCRIPT={'scenes':[{'scene_id':'S1','title':'탈출','visual_action':'두 사람이 열린 통로를 확인한다.','spoken_blocks':[{'kind':'dialogue','speaker':'서진','text':'같이 나가자.'}]}],'quality_notes':[]}
OUTPUTS=[SCRIPT,{'cuts':[{'cut_id':'C1','scene_id':'S1','image_prompt':'같은 복장과 부상 상태, 열린 통로를 보는 두 사람의 2D 중경.','references':['기존 서진 참조 · 확인 필요']}],'quality_notes':[]},{'selections':[{'cut_id':'C1','selected':False,'reason':'정지 반응 컷으로 충분하다.','video_prompt':''}],'quality_notes':[]},{'directions':[{'cut_id':'C1','ae_instruction':'고정 화면. 전환은 하드 컷. 얼굴과 문자는 보호한다.','timing_note':'실제 음성 저장 후 대사 앵커에 연결한다.'}],'quality_notes':[]}]
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
 assert [s['status'] for s in p['manual_workflow']['stages']]==['review','pending','pending','pending']
 assert '화면 상황' in p['script'] and '대사 · 서진' in p['script']
 assert console.digest(p)==m.digest(p)

def test_explicit_steps_edits_invalidation_and_stale_requests(tmp_path,monkeypatch):
 j,i,c=seed(tmp_path);calls=[]
 def gen(index,*args,**kw):calls.append(index);return copy.deepcopy(OUTPUTS[index])
 monkeypatch.setattr(m,'generate',gen)
 assert call(j,i,c,2,'generate').status_code==409
 for step in range(1,5):
  if step>1:
   assert call(j,i,c,step,'generate').status_code==200;wait(j)
  before=len(calls);assert call(j,i,c,step,'approve').status_code==200;assert len(calls)==before
 assert calls==[1,2,3] and j.rows[i]['status']=='completed'
 old_hash=j.rows[i]['candidate_hash'];out=copy.deepcopy(SCRIPT);out['scenes'][0]['spoken_blocks'][0]['text']='먼저 길을 확인하자.'
 assert call(j,i,c,1,'save',output=out).status_code==200
 w=j.bundle(i)['candidate']['manual_workflow'];assert [s['status'] for s in w['stages']]==['review','stale','stale','stale']
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
 assert [s['status'] for s in b['candidate']['manual_workflow']['stages']]==['review','pending','pending','pending']
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
