import pytest
from worker.script_topic_delivery import spoken_translation_blocks

def test_silent_cuts_keep_scene_indices_without_spoken_filler():
 p={'script':'앞 대사\n\n\n\n뒤 대사','structure':{'scenes':[{'scene_text':'앞 대사'},{'silent_visual':True,'spoken_blocks':[]},{'scene_text':'뒤 대사'}]}}
 assert spoken_translation_blocks(p)==[{'index':0,'source_text':'앞 대사'},{'index':2,'source_text':'뒤 대사'}]

def test_missing_speech_is_not_a_silent_cut_and_changed_script_is_rejected():
 p={'script':'앞 대사','structure':{'scenes':[{'scene_text':'앞 대사'},{}]}}
 with pytest.raises(ValueError,match='explicitly silent'):spoken_translation_blocks(p)
 p['structure']['scenes'][1]={'silent_visual':True,'spoken_blocks':[]};p['script']='다른 대사'
 with pytest.raises(ValueError):spoken_translation_blocks(p)


def test_live_script_producer_prevents_duplicate_recovery(monkeypatch):
 import json
 from io import BytesIO
 from worker.script_delivery_status import local_producer_active
 def response(request,timeout):
  if isinstance(request,str):return BytesIO(b'<meta name="local-token" content="test-token">')
  return BytesIO(json.dumps({'local_busy':True,'producer_inflight_ids':['same'],'jobs':[{'id':'same'}]}).encode())
 monkeypatch.setattr('urllib.request.urlopen',response)
 assert local_producer_active('same')
 assert not local_producer_active('another')


def test_ui_running_overlay_is_not_a_live_producer(monkeypatch):
 import json
 from io import BytesIO
 from worker.script_delivery_status import local_producer_active
 def response(request,timeout):
  if isinstance(request,str):return BytesIO(b'<meta name="local-token" content="test-token">')
  return BytesIO(json.dumps({'local_busy':True,'producer_inflight_ids':[],'jobs':[{'id':'same','status':'running'}]}).encode())
 monkeypatch.setattr('urllib.request.urlopen',response)
 assert not local_producer_active('same')
