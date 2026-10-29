from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import submitted_still_coordinates as c
import ae_highlight_worker as ae
import std_project_assets
import prepared_mouth_layers


def fixture(tmp_path,monkeypatch):
 image=tmp_path/'original.png';image.write_bytes(b'original source');post={'dialogue':[{'speaker':'hero','kind':'dialogue','text':'hello'}],'cast':{}}
 scene={'number':19,'text':'hello','source':{'id':'image','metadata':{'gcs_path':'image.png'}}};job={'id':'job','project_id':'project'}
 monkeypatch.setattr(ae,'_supabase',lambda:('https://example.test',{}));monkeypatch.setattr(std_project_assets,'load_project_assets',lambda *args:[])
 monkeypatch.setattr(ae,'_upload_gcs_file',lambda *args:('bucket','coordinates.json',''))
 monkeypatch.setattr(ae,'_request',lambda *args,**kwargs:SimpleNamespace(json=lambda:[{'id':'receipt'}]))
 layers=Mock();monkeypatch.setattr(prepared_mouth_layers,'prepare_scene',layers)
 return image,post,scene,job,layers


def test_missing_coordinates_are_analyzed_saved_and_prepared_from_exact_image(tmp_path,monkeypatch):
 image,post,scene,job,layers=fixture(tmp_path,monkeypatch);locate=Mock(return_value=[{'speaker':'hero','status':'offscreen','confidence':1,'reason':'absent in actual image'}]);monkeypatch.setattr(c,'locate_speakers',locate)
 regions,receipt=c.prepare('runner',job,scene,post,image,tmp_path/'work',lambda:None)
 assert receipt=='receipt';assert regions['image_id']=='image';assert regions['source_sha256']==c.digest(image);assert locate.call_args.args[3]==image;assert layers.call_args.args[0]==image;assert image.read_bytes()==b'original source'


def test_old_coordinates_cannot_authorize_a_changed_source(tmp_path,monkeypatch):
 image,post,scene,job,layers=fixture(tmp_path,monkeypatch);post['speaker_regions']={'image_id':'image','source_sha256':'stale','speakers':[]}
 with pytest.raises(ValueError,match='source changed'):c.prepare('runner',job,scene,post,image,tmp_path/'work',lambda:None)
 layers.assert_not_called()


def test_unverified_visible_geometry_is_not_saved_or_animated(tmp_path,monkeypatch):
 image,post,scene,job,layers=fixture(tmp_path,monkeypatch);monkeypatch.setattr(c,'locate_speakers',lambda *args:[{'speaker':'hero','status':'visible','confidence':1,'reason':'test','face_box':[.1,.1,.5,.5],'mouth_box':[.2,.3,.25,.32]}]);publish=Mock();monkeypatch.setattr(ae,'_upload_gcs_file',publish)
 with pytest.raises(ValueError,match='geometry'):c.prepare('runner',job,scene,post,image,tmp_path/'work',lambda:None)
 publish.assert_not_called();layers.assert_not_called()

def test_matching_source_receipt_reuses_coordinates_without_new_analysis(tmp_path,monkeypatch):
 import json
 image,post,scene,job,layers=fixture(tmp_path,monkeypatch)
 key=c.fingerprint({'version':1,'source_id':'image','source':('air-studio-prod','image.png'),'source_sha256':c.digest(image),'cast':{},'speakers':['hero']})
 regions={'image_id':'image','source_sha256':c.digest(image),'speakers':[{'speaker':'hero','status':'offscreen','confidence':1,'reason':'Actual source reviewed'}]}
 content=json.dumps({'fingerprint':key,'regions':regions}).encode()
 import hashlib
 cached={'id':'cached','metadata':{'kind':'submitted_still_coordinates','fingerprint':key,'state':'ready','gcs_path':'cached.json','receipt_sha256':hashlib.sha256(content).hexdigest()}}
 monkeypatch.setattr(std_project_assets,'load_project_assets',lambda *args:[cached]);monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,target:target.write_bytes(content))
 locate=Mock();publish=Mock();monkeypatch.setattr(c,'locate_speakers',locate);monkeypatch.setattr(ae,'_upload_gcs_file',publish)
 result,identity=c.prepare('runner',job,scene,post,image,tmp_path/'work',lambda:None)
 assert identity=='cached';assert result==regions;locate.assert_not_called();publish.assert_not_called();layers.assert_called_once()
