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
 def locate(runner,*args):
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
 def broken(*args):raise ValueError('Original mouth source checksum mismatch')
 monkeypatch.setattr(ae_mouth,'locate_speakers',broken)
 with pytest.raises(ValueError,match='checksum'):locate_selective_speakers(Runner(),'id',{},source,[{'speaker':'hero'}],{})

def test_successful_repair_uses_the_actual_locator_result_without_relabelling(tmp_path,monkeypatch):
 source=tmp_path/'source.png';source.write_bytes(b'source');attempts=[];expected=[{'speaker':'hero','status':'visible','actual_review_passed':True}]
 def locate(runner,*args):
  attempts.append(1)
  if len(attempts)==2:return expected
  runner._stage('job','03_ae_mouth_geometry_review',{'_local_image_paths':[str(source)],'speakers':[{'speaker':'hero'}]},'review')
  raise ValueError('Original face crop must pass independent geometry review')
 monkeypatch.setattr(ae_mouth,'locate_speakers',locate)
 assert locate_selective_speakers(Runner(),'id',{},source,[{'speaker':'hero'}],{}) is expected
