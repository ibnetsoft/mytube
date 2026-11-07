import sys
from pathlib import Path
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'worker')]
import ae_mouth
from wuxia_mouth_preparation import locate_selective_speakers

class Runner:
 def __init__(self):self.contexts=[]
 def _stage(self,job,name,context,task):
  self.contexts.append(context)
  return {'speakers':[{'speaker':'hero','passed':False,'reason':'Marker is below actual lower lip'}]}

def test_rejected_geometry_gets_one_feedback_repair_and_never_becomes_an_approval(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'actual-source-proof')
 calls=[]
 def locate(runner,*args,**kwargs):
  calls.append(runner)
  runner._stage('job','03_ae_mouth_geometry_review',{'_local_image_paths':[str(source)],'speakers':[{'speaker':'hero','status':'visible','mouth_geometry':{}}]},'review')
  raise ValueError('Original face crop must pass independent geometry review')
 monkeypatch.setattr(ae_mouth,'locate_speakers',locate)
 runner=Runner();result=locate_selective_speakers(runner,'id',{},source,[{'speaker':'hero'}],{})
 assert len(calls)==2 and 'previous_geometry_rejection' not in runner.contexts[0]
 assert runner.contexts[1]['previous_geometry_rejection']['reviews'][0]['passed'] is False
 assert result[0]['status']=='uncertain' and result[0]['confidence']==0 and result[0]['geometry_review_excluded'] is True
 assert len(list((tmp_path/'rejected-geometry').glob('*/review.json')))==2

def test_missing_art_or_unrelated_validation_failures_are_not_reported_as_zero_eligible(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'source')
 def broken(*args,**kwargs):raise ValueError('Original mouth source checksum mismatch')
 monkeypatch.setattr(ae_mouth,'locate_speakers',broken)
 with pytest.raises(ValueError,match='checksum'):locate_selective_speakers(Runner(),'id',{},source,[{'speaker':'hero'}],{})

def test_successful_repair_uses_the_actual_locator_result_without_relabelling(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'source');attempts=[];expected=[{'speaker':'hero','status':'visible','actual_review_passed':True}]
 def locate(runner,*args,**kwargs):
  attempts.append(1)
  if len(attempts)==2:return expected
  runner._stage('job','03_ae_mouth_geometry_review',{'_local_image_paths':[str(source)],'speakers':[{'speaker':'hero'}]},'review')
  raise ValueError('Original face crop must pass independent geometry review')
 monkeypatch.setattr(ae_mouth,'locate_speakers',locate)
 assert locate_selective_speakers(Runner(),'id',{},source,[{'speaker':'hero'}],{}) is expected

def test_invalid_lip_contour_retries_once_then_preserves_source(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'source');calls=[]
 class NumericRunner(Runner):
  def _stage(self,job,name,context,task):
   self.contexts.append(context)
   return {'speaker':'hero','status':'visible','mouth_geometry':{}}
 def locate(proxy,*args,**kwargs):
  calls.append(1)
  proxy._stage('job','03_ae_mouth_crop_localization',{'_local_image_paths':[str(source)]},'locate')
  raise ValueError('Lip landmarks must lie inside actual face contour and mouth patch')
 monkeypatch.setattr(ae_mouth,'locate_speakers',locate)
 runner=NumericRunner();result=locate_selective_speakers(runner,'id',{},source,[{'speaker':'hero'}],{})
 assert len(calls)==2 and runner.contexts[1]['previous_geometry_rejection']['validation_error'].startswith('Lip landmarks')
 assert result[0]['status']=='uncertain' and result[0]['mouth_geometry']['render_policy']=='preserve_original'
 assert result[0]['mouth_geometry']['review']['passed'] is False

def test_malformed_review_is_an_error_not_a_visibility_exclusion(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'source')
 class BadRunner(Runner):
  def _stage(self,*args):return {'speakers':[{'speaker':'hero','passed':None,'reason':'no verdict'}]}
 def locate(proxy,*args,**kwargs):
  proxy._stage('job','03_ae_mouth_geometry_review',{'speakers':[{'speaker':'hero'}]},'review')
  raise ValueError('Original face crop must pass independent geometry review')
 monkeypatch.setattr(ae_mouth,'locate_speakers',locate)
 with pytest.raises(ValueError,match='independent geometry review'):
  locate_selective_speakers(BadRunner(),'id',{},source,[{'speaker':'hero'}],{})

@pytest.mark.parametrize('status,confidence',[('visible',.72),('uncertain',.95)])
def test_selective_uncertainty_preserves_pixels_without_changing_generic_review(status,confidence):
 response={'speakers':[{'speaker':'hero','status':status,'confidence':confidence,
  'reason':'Mouth contour partly obscured','mouth_geometry':{'render_policy':'animate'}}]}
 with pytest.raises(ValueError):ae_mouth.visible_speakers(response,['hero'])
 selected=ae_mouth.visible_speakers(response,['hero'],allow_uncertain=True)
 assert selected[0]['status']=='uncertain' and selected[0]['mouth_geometry']['render_policy']=='preserve_original'
 assert response['speakers'][0]['mouth_geometry']['render_policy']=='animate'
