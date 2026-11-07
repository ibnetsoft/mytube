import copy,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from worker.wuxia_motion_policy import plan_new_package
from wuxia_motion_review import evidence,CHECKS,review_source

def package():
 return {'script':'대사는 그대로','structure':{'image_style':'wuxia_webtoon','scenes':[
  {'scene_number':1,'visual_action':'검객이 오른쪽 문으로 들어가고 상대가 길을 막는다.','scene_text':'멈춰라.'},
  {'scene_number':2,'visual_action':'불길이 뜰의 나무 기둥을 태우며 뜨거운 공기가 일렁인다.','scene_text':'비켜.'}]}}

def stage(job,name,context,task):
 return {'scenes':[{'scene_number':s['scene_number'],'pan':'pan_right' if s['scene_number']==1 else 'none','zoom':'zoom_in' if s['scene_number']==1 else 'none','heat':s['scene_number']==2,'reason':'진입 방향을 따라감' if s['scene_number']==1 else '실제 불길과 고온','evidence_quote':s['planned_visuals'],'heat_reason':'타오르는 나무 기둥' if s['scene_number']==2 else ''} for s in context['scenes']]}

def test_semantic_new_scene_choices_are_stored_without_changing_script_or_manual_choices():
 p=package();result=plan_new_package(stage,'id',p,{'mode':'new','image_style':'wuxia_webtoon'})
 assert result['script']==p['script'] and 'image_effect' not in p['structure']['scenes'][0]
 assert [s['image_effect'] for s in result['structure']['scenes']]==['pan_right_zoom_in','none+heat']
 assert result['structure']['scenes'][0]['wuxia_motion_selection']['basis']=='planned_visuals'
 assert result['structure']['wuxia_motion_policy']['actual_output_review_required'] is True
 result['structure']['scenes'][0]['image_effect']='none';result['structure']['scenes'][0]['metadata']['image_effect']='none'
 assert plan_new_package(lambda *a:pytest.fail('must preserve existing choices'),'id',result,{'mode':'new','image_style':'wuxia_webtoon'})['structure']['scenes'][0]['image_effect']=='none'
 assert plan_new_package(stage,'id',p,{'mode':'repair','image_style':'wuxia_webtoon'}) is p

def test_bad_evidence_retries_with_feedback_instead_of_keyword_guessing_or_silent_fixed_fallback():
 calls=[]
 def bad(*args):
  calls.append(args);r=stage(*args);r['scenes'][0]['evidence_quote']='그림에 없는 행동';return r
 with pytest.raises(ValueError,match='validation failed'):plan_new_package(bad,'id',package(),{'mode':'new','image_style':'wuxia_webtoon'})
 assert len(calls)==3 and 'validation_retry' in calls[1][2]

def test_actual_output_sampling_includes_move_middle_end_hold_and_distinct_heat_phases():
 samples=[]
 for i in range(72):
  at=i/24;progress=min(1,at/.9)
  samples.append({'at':at,'state':'a','motion':{'dx':progress*.03,'dy':0,'scale':1+progress*.1,'heat':[0 if i==0 else i%5]*48}})
 t={'auto_motion_policy':{'actual_output_review_required':True},'samples':samples,'states':[{'asset_id':'a','sha256':'a'*64}]}
 result=evidence({'wuxia_timeline':t},3,24)
 assert result['required_checks']==CHECKS
 assert any(0<at<.9 for at in result['sample_times']) and any(.9<=at<=1.2 for at in result['sample_times'])
 assert len({tuple(s['motion']['heat']) for s in result['frozen_samples']})>1
 assert evidence({'wuxia_timeline':{}},3,24) is None

def test_actual_source_review_inspects_sha_checked_images_and_keeps_failed_findings(tmp_path):
 import hashlib
 image=tmp_path/'source.png';image.write_bytes(b'actual fixture bytes')
 state={'asset_id':'a','file':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
 runtime={'states':[state],'auto_motion_policy':{'actual_source_review_required':True},'samples':[{'at':0},{'at':1/24}]}
 class Runner:
  def _stage(self,job,name,context,task):
   assert context['_local_image_paths']==[str(image)]
   return {'states':[{'asset_id':'a','passed':False,'evidence':'불길이 보이지 않는다','issues':['heat absent in artwork']}]}
 assert review_source(Runner(),{'number':1,'start':0,'end':2},runtime,lambda:None)['passed'] is False
 image.write_bytes(b'changed')
 with pytest.raises(ValueError,match='identity'):review_source(Runner(),{'number':1,'start':0,'end':2},runtime,lambda:None)

def test_real_new_script_workflow_invokes_the_motion_selector_and_repair_preserves_old_work(monkeypatch,tmp_path):
 from worker import codex_local_workflow as workflow,script_guidelines,script_worker_store,script_worker_guidance,elevenlabs_performance,codex_content_runner
 monkeypatch.setattr(script_guidelines,'approved_guidelines',lambda *a:([],''))
 monkeypatch.setattr(script_worker_store,'ScriptStore',lambda:object())
 monkeypatch.setattr(script_worker_guidance,'load_production_guidance',lambda:'guidance')
 monkeypatch.setattr(elevenlabs_performance,'annotate_new_package',lambda p,*a:p)
 monkeypatch.setattr(workflow,'_produce',lambda *a:package())
 class Runner:
  _stage=staticmethod(stage)
 monkeypatch.setattr(codex_content_runner,'CodexStagedContentRunner',Runner)
 new=workflow.produce('id',{'mode':'new','image_style':'wuxia_webtoon'},None,tmp_path,lambda _:None)
 assert new['structure']['wuxia_motion_policy']['enabled'] is True
 old=workflow.produce('id',{'mode':'repair'},None,tmp_path,lambda _:None)
 assert 'wuxia_motion_policy' not in old['structure']

def test_actual_decoder_review_cannot_skip_missing_effect_even_with_legacy_bypass(monkeypatch,tmp_path):
 import subprocess,imageio_ffmpeg,numpy as np
 from PIL import Image
 import motion_automation_worker as worker
 movie=tmp_path/'held-fixture-not-AE.mp4';source=tmp_path/'source.png'
 Image.new('RGB',(32,18),'red').save(source)
 import wave
 with wave.open(str(tmp_path/'voice.wav'),'wb') as wav:
  wav.setparams((1,2,8000,16000,'NONE','not compressed'));wav.writeframes(b'\0\0'*16000)
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-f','lavfi','-i','color=red:s=32x18:r=24','-t','2','-c:v','libx264',str(movie)],check=True)
 monkeypatch.setattr(worker,'pcm',lambda *a:np.ones(16000))
 samples=[{'at':i/24,'state':'a','motion':{'dx':min(1,i/20)*.03,'dy':0,'scale':1,'heat':[]}} for i in range(48)]
 scene={'number':1,'start':0,'end':2,'_skip_review':True,'wuxia_timeline':{
  'auto_motion_policy':{'actual_output_review_required':True},'samples':samples,'states':[{'asset_id':'a','sha256':worker.digest(source)}]},
  '_wuxia_review_sources':[{'asset_id':'a','file':str(source),'sha256':worker.digest(source)}]}
 class RejectingReviewer:
  calls=0
  def _stage(self,job,name,context,task):
   self.calls+=1
   assert set(CHECKS)<=set(context['required_checks'])
   assert context['wuxia_actual_sample_times'] and str(source) in context['_local_image_paths']
   assert all(Path(p).is_file() for p in context['_local_image_paths'])
   return {'passed':False,'repair_scope':'direction_only','critical_issues':['camera did not move in held test video'],
    'checks':[{'id':k,'passed':k!='wuxia_camera_execution','evidence':'held fixture pixels; requested motion absent'} for k in context['required_checks']]}
 runner=RejectingReviewer()
 with pytest.raises(worker.NeedsReview,match='Actual output needs repair'):
  worker.review_output(runner,movie,source,tmp_path/'voice.wav',scene,{'scene':{'keys':[],'effects':[]}},tmp_path,lambda:None)
 assert runner.calls==1

def test_auto_motion_requires_new_review_worker_and_rejects_unaudited_cache(monkeypatch):
 from wuxia_worker_contract import claim_acknowledgement
 from motion_automation_worker import native_cache_covers_frame_clock
 timeline={'contract':'wuxia_native_timeline/v5','auto_motion_policy':{'actual_output_review_required':True}}
 ack=claim_acknowledgement({'scenes':[{'wuxia_timeline':timeline}]},{'required_worker_contract':'wuxia_motion_auto/v1'},'new-lease')
 assert ack['worker_contract_ack']['contract']=='wuxia_motion_auto/v1'
 assert not native_cache_covers_frame_clock({}, {'wuxia_timeline':timeline},{'review':{'passed':True}})
