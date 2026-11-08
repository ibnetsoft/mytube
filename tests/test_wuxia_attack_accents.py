import copy,hashlib,json,sys
from pathlib import Path
import pytest
from PIL import Image
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'worker')]
from wuxia_attack_accents import attach,validate_frozen,CONTRACT

def fixture(tmp):
 image=tmp/'source.png';Image.new('RGB',(192,108),'#25354a').save(image)
 sha=hashlib.sha256(image.read_bytes()).hexdigest()
 pkg={'scenes':[{'scene_id':'S01','states':[{'asset_id':'art','sha256':sha,'face_exclusion_boxes':[]}],'effects':[{'type':'legacy','asset_id':'art'}]}]}
 review={'contract':CONTRACT,'source_sha256':sha,'source_reviewed':True,'event':'palm contact','materials':'stone','reason':'charged strike','motion_evidence':'reviewed action pose','protected_boxes':[],'timing_basis':'scene_local','electricity_motivated':True}
 effect={'type':'electric_discharge','attack_path':[[.2,.6],[.7,.6]],'center':[.7,.6],'contact_at_seconds':1,'duration_seconds':.4,'intensity':1,'radius':.5}
 return pkg,[{'scene_id':'S01','asset_id':'art','source_file':'source.png','review':review,'effects':[effect]}]

def test_actual_source_copy_preserves_existing_assets_and_is_idempotent(tmp_path):
 pkg,selected=fixture(tmp_path);original=copy.deepcopy(pkg)
 output=attach(pkg,selected,tmp_path)
 assert pkg==original and len(output['scenes'][0]['effects'])==2
 assert attach(output,selected,tmp_path)==output
 selected[0]['effects']=[]
 assert attach(output,selected,tmp_path)['scenes'][0]['effects']==original['scenes'][0]['effects']

@pytest.mark.parametrize('change',[lambda s:s['review'].update(source_sha256='b'*64),lambda s:s['review'].update(electricity_motivated=False),lambda s:s['effects'][0].update(contact_at_seconds=-1),lambda s:s['effects'][0].update(attack_path=[[.7,.6],[.7,.6]])])
def test_no_guessed_source_electricity_or_contact(tmp_path,change):
 pkg,selected=fixture(tmp_path);change(selected[0])
 with pytest.raises(ValueError):attach(pkg,selected,tmp_path)

def test_frozen_contact_order_source_and_face_protection_are_checked():
 sha='a'*64
 accent={'type':'electric_discharge','asset_id':'a','source_sha256':sha,'contact_at':1,'from':1,'duration_seconds':.5,'shape_offset':0,'shape_count':1,'protected_boxes':[[0,0,.2,.2]],'review':{'contract':CONTRACT,'source_sha256':sha,'source_reviewed':True}}
 frame={'action_accents':[accent],'active':['electric_discharge:0'],'overlays':[{'kind':'polygon','points':[[900,500],[920,500],[920,520],[900,520]]}]}
 sample={'at':1.1,'state':'a'};timeline={'states':[{'asset_id':'a','sha256':sha}]}
 validate_frozen(timeline,sample,frame)
 for patch in [{'from':.5},{'source_sha256':'b'*64},{'protected_boxes':[[0,0,1,1]]}]:
  bad=copy.deepcopy(frame);bad['action_accents'][0].update(patch)
  with pytest.raises(ValueError):validate_frozen(timeline,sample,bad)

def test_screen_wash_exception_cannot_hide_opaque_or_nonflash_protected_overlays():
 sha='a'*64
 accent={'type':'contact_flash','protection_mode':'exposure_wash/v1','asset_id':'a','source_sha256':sha,'contact_at':1,'from':1,'duration_seconds':.08,'shape_offset':0,'shape_count':1,'protected_boxes':[[0,0,1,1]],'review':{'contract':CONTRACT,'source_sha256':sha,'source_reviewed':True,'screen_flash_reviewed':True}}
 frame={'action_accents':[accent],'active':['contact_flash:0'],'overlays':[{'kind':'polygon','points':[[0,0],[1920,0],[1920,1080],[0,1080]],'color':'#fff7cf','opacity':.22}]}
 sample={'at':1.01,'state':'a'};timeline={'states':[{'asset_id':'a','sha256':sha}]}
 validate_frozen(timeline,sample,frame)
 for target,patch in [('accent',{'type':'electric_discharge'}),('shape',{'opacity':1}),('shape',{'points':[[0,0],[20,0],[20,20],[0,20]]})]:
  bad=copy.deepcopy(frame)
  (bad['action_accents'][0] if target=='accent' else bad['overlays'][0]).update(patch)
  with pytest.raises(ValueError):validate_frozen(timeline,sample,bad)
