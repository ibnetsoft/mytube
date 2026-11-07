import sys
from pathlib import Path
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'worker')]
from worker.wuxia_mouth_worker import prepare_topic
from worker import wuxia_mouth_preparation

class Store:
 def __init__(self,change=False):self.reads=0;self.change=change;self.published=None
 def request(self,method,table,**kwargs):
  if method=='GET':
   self.reads+=1
   return [{'id':3433,'status':'pending','assigned_at':None,'assigned_employee_email':'other@example.com' if self.change and self.reads>1 else 'owner@example.com'}],1
  self.published=kwargs['body'];return {'applied':True},None

def structure():
 return {'wuxia_mouth_policy':{'auto_prepare':True},'wuxia_ae_package':{
  'contract':'wuxia_still_ae_episode/v1','scenes':[{'states':[{'asset_id':'one'}],'graphics':[]}]}}

def test_reserved_pending_owner_is_bound_to_publication(monkeypatch):
 store=Store()
 def prepare(*args):args[4]();return {'states':[],'report':{'state':'not_required','eligible_count':0}}
 monkeypatch.setattr(wuxia_mouth_preparation,'prepare_art',prepare)
 assert prepare_topic(3433,structure(),store)['state']=='not_required'
 assert store.published['p_expected_owner_email']=='owner@example.com'

def test_changed_reservation_does_not_publish(monkeypatch):
 store=Store(change=True)
 def prepare(*args):args[4]();pytest.fail('changed owner must stop preparation')
 monkeypatch.setattr(wuxia_mouth_preparation,'prepare_art',prepare)
 with pytest.raises(RuntimeError,match='reservation owner changed'):prepare_topic(3433,structure(),store)
 assert store.published is None
