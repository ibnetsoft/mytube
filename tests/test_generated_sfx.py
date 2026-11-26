import json,shutil,wave
from pathlib import Path
from types import SimpleNamespace
import pytest
from worker import generated_sfx as g
PROJECT='11111111-1111-4111-8111-111111111111'
def plan():return {'contract':g.CONTRACT,'project_id':PROJECT,'cues':[{'id':'impact','cut_id':'C002','prompt':'Dry stone impact, no voices or music','duration_seconds':1.,'offset_seconds':.2,'volume_db':-18.,'start':2.2,'end':2.7,'scene_number':2}]}
def audio(path):
 with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\x10\x00'*8000)
class AE:
 def __init__(self):self.rows={};self.files={}
 class GcsRef:
  def __init__(self,bucket,path):self.bucket=bucket;self.path=path
 def _request(self,method,url,headers,params=None,json=None):
  if method=='GET':return SimpleNamespace(json=lambda:[self.rows[params['id'][3:]]] if params['id'][3:] in self.rows else [])
  self.rows[json['id']]=json;return SimpleNamespace(json=lambda:[json])
 def _upload_gcs_file(self,path,key,mime):self.files[key]=Path(path).read_bytes();return 'bucket',key,'url'
 def _download_gcs_file(self,ref,path):Path(path).write_bytes(self.files[ref.path])
def test_generation_is_reused_after_local_cache_loss_and_cue_stays_in_cut(tmp_path,monkeypatch):
 ae=AE();calls=[]
 def gen(cue,raw,ticket):calls.append(cue['id']);audio(raw)
 def dec(raw,clean):shutil.copy2(raw,clean);return 1.
 monkeypatch.setattr(g,'generate',gen);monkeypatch.setattr(g,'decode',dec)
 first=g.ensure(plan(),tmp_path,ae=ae,base='db',headers={},fresh=lambda:None)
 assert len(first)==1 and first[0]['start']==2.2 and first[0]['duration']==pytest.approx(.5)
 shutil.rmtree(tmp_path/'generated-sfx')
 second=g.ensure(plan(),tmp_path,ae=ae,base='db',headers={},fresh=lambda:None)
 assert calls==['impact'] and second[0]['asset_id']==first[0]['asset_id']
 assert len([r for r in ae.rows.values() if r['metadata']['kind']=='generated_sfx'])==1
 assert any(r['metadata'].get('cue_bindings') for r in ae.rows.values())
def test_existing_user_cue_suppresses_provider_call(tmp_path,monkeypatch):
 monkeypatch.setattr(g,'generate',lambda *a:pytest.fail('must not generate duplicate'))
 ae=AE();assert g.ensure(plan(),tmp_path,ae=ae,base='db',headers={},fresh=lambda:None,existing=[{'id':'impact','enabled':False}])==[]
def test_unknown_request_result_never_blindly_resends(tmp_path,monkeypatch):
 raw=tmp_path/'sound.raw';ticket=tmp_path/'sound.request.json';ticket.write_text('{}')
 monkeypatch.setattr(g.requests,'post',lambda *a,**k:pytest.fail('paid duplicate'))
 with pytest.raises(RuntimeError,match='unknown result'):g.generate(plan()['cues'][0],raw,ticket)
def test_invalid_frozen_time_rejected_before_api():
 p=plan();p['cues'][0]['start']=p['cues'][0]['end']
 with pytest.raises(ValueError):g.validate(p)
def test_empty_plan_has_no_side_effects(tmp_path):
 assert g.ensure(None,tmp_path)==[] and not list(tmp_path.iterdir())
def test_provider_receives_duration_as_parameter_not_prompt_suffix(tmp_path,monkeypatch):
 seen={};monkeypatch.setenv('ELEVENLABS_API_KEY','unit-test-key')
 def post(url,**kw):seen.update(kw);return SimpleNamespace(status_code=200,ok=True,content=b'fake-audio')
 monkeypatch.setattr(g.requests,'post',post);raw=tmp_path/'s.raw';ticket=tmp_path/'t.json';g.generate(plan()['cues'][0],raw,ticket)
 assert seen['json']['duration_seconds']==1 and seen['json']['loop'] is False and raw.read_bytes()==b'fake-audio' and not ticket.exists()

def test_real_decode_trims_leading_silence_and_keeps_audible_body(tmp_path):
 import math,struct
 raw=tmp_path/'provider.wav';clean=tmp_path/'clean.wav'
 with wave.open(str(raw),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
  w.writeframes(b'\0\0'*1600+b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*440*n/8000))) for n in range(6400)))
 duration=g.decode(raw,clean)
 assert .75<duration<.85
 with wave.open(str(clean),'rb') as w:assert w.getnchannels()==1 and w.getframerate()==48000
