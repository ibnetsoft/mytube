import copy,hashlib,json,sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path('worker').resolve()))
from worker.wuxia_cinematic import plan_new_package,validate_review,prepare_scene
from worker.wuxia_cinematic_runtime import mask_image,validate

def test_future_semantic_choices_preserve_edits_and_require_grounded_information():
 package={'structure':{'image_style':'wuxia_webtoon','scenes':[{'scene_number':1,'visual_action':'입문 조건 충족 안내가 등장한다.','transition_effect':'wipe_left'}]}}
 row=dict(scene_number=1,vignette=False,panel=True,bounce=True,slide_blur=True,panel_text='입문 조건 충족',reason='새 자격 정보를 읽히게 한다',evidence_quote='입문 조건 충족 안내가 등장한다.')
 calls=[]
 def stage(*args):calls.append(args);return {'scenes':[copy.deepcopy(row)]}
 p=plan_new_package(stage,'id',package,{'mode':'new'});assert p['structure']['wuxia_mouth_policy']['cinematic_auto']['enabled'];assert not package['structure'].get('wuxia_cinematic_policy')
 assert plan_new_package(stage,'id',p,{'mode':'repair'}) is p
 n=len(calls);plan_new_package(stage,'id',p,{'mode':'new'});assert len(calls)==n
 row['panel_text']='공격력 9999'
 with pytest.raises(ValueError):plan_new_package(stage,'id',package,{'mode':'new'})

def test_native_mask_preserves_protected_people_and_lettering():
 im=mask_image({'center':[.5,.5],'protected_boxes':[[0,0,.2,.3],[.7,.1,.95,.4]]})
 alpha=im.getchannel('A');assert alpha.crop((0,0,192,162)).getextrema()==(0,0)
 assert alpha.getpixel((0,539))>200;assert alpha.getpixel((480,270))==0

def test_panel_full_bounce_envelope_must_clear_faces_and_edges():
 st={'sha256':'a'*64};plan={'panel':True};r=dict(source_sha256=st['sha256'],passed=True,evidence='actual face reviewed',vignette_allowed=True,panel_allowed=True,slide_blur_allowed=False,protected_boxes=[[.1,.1,.5,.9]],lettering_boxes=[],focus=[.5,.5],panel_rect=[.65,.2,.95,.5])
 validate_review(r,st,plan)
 r['panel_rect']=[.4,.2,.7,.5]
 with pytest.raises(ValueError,match='overlaps'):validate_review(r,st,plan)

def test_cinematic_source_review_is_bound_and_cached_without_paid_model_calls(tmp_path):
 source=tmp_path/'source.png';Image.new('RGB',(512,288),'gray').save(source);sha=hashlib.sha256(source.read_bytes()).hexdigest();plan=dict(panel=False,vignette=True,slide_blur=False,bounce=False,plan_id='b'*64)
 class Runner:
  calls=0
  def _stage(self,*args):
   self.calls+=1;assert Path(args[2]['_local_image_paths'][0]).read_bytes()==source.read_bytes()
   return dict(source_sha256=sha,passed=True,evidence='Actual empty background, no people or text',vignette_allowed=True,panel_allowed=False,slide_blur_allowed=False,protected_boxes=[],lettering_boxes=[],focus=[.5,.5],panel_rect=None,quality_notes=[])
 runner=Runner();st=dict(asset_id='A',sha256=sha,gcs_bucket='qa',gcs_path='s');sc=dict(scene_id='E01_S01',states=[st]);policy={'selections':{'1':plan}}
 out=prepare_scene(sc,policy,'test',lambda _,p:p.write_bytes(source.read_bytes()),lambda:None,runner);st['cinematic_review']=out['A'];prepare_scene(sc,policy,'test',None,lambda:None,runner);assert runner.calls==1
