import sys,copy,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_motion import validate,jsx
from wuxia_transition import jsx as transition_jsx
from wuxia_worker_contract import claim_acknowledgement

def timeline():
 return {'contract':'wuxia_native_timeline/v5','states':[{'asset_id':'a','heat_face_reviewed':True,'heat_protection_boxes':[[.3,.25,.6,.55]]}],
  'samples':[{'at':.5,'state':'a','motion':{'contract':'wuxia_motion_samples/v1','dx':.02,'dy':0,'scale':1.2,'heat':[0]*48,'issues':[]},
    'transition':{'contract':'wuxia_transition_samples/v1','kind':'none','dx':0,'dy':0,'scale':1,'opacity':1,'flash':0,'backdrop':0,'issues':[]}}]}

def test_native_camera_and_heat_require_new_worker_acknowledgement():
 t=timeline();validate(t)
 assert claim_acknowledgement({'scenes':[{'wuxia_timeline':t}]},{'required_worker_contract':t['contract']},'fresh')['worker_contract_ack']=={'contract':t['contract'],'lease_token':'fresh'}
 t['contract']='wuxia_native_timeline/v4'
 with pytest.raises(ValueError,match='v5'):validate(t)

@pytest.mark.parametrize('change',[{'scale':1.5},{'dx':float('nan')},{'heat':[6]*48},{'heat':[0]*3},{'issues':['missing_review']}])
def test_unsafe_or_incomplete_samples_fail(change):
 t=timeline();t['samples'][0]['motion'].update(change)
 with pytest.raises(ValueError):validate(t)

def test_heat_never_warps_reviewed_anatomy_and_requires_review():
 t=timeline();t['samples'][0]['motion']['heat'][15]=1
 with pytest.raises(ValueError,match='anatomy'):validate(t)
 t=timeline();t['states'][0]['heat_face_reviewed']=False
 with pytest.raises(ValueError,match='review'):validate(t)

def test_ae_uses_frozen_heat_offsets_below_lettering_and_fades_real_children_of_nested_camera():
 t=timeline();t['samples'][0]['motion']['heat'][0]=3.125;s=jsx(t)
 data=json.loads(s.split('var WMC=',1)[1].split(';\n',1)[0]);assert data[0]['heat'][0]==3.125
 assert 'wuxia_heat_band_' in s and 'band=view.duplicate()' in s and 'wuxia_opening_camera_rig' in s
 assert "whold(mt.property('ADBE Position'))" in s
 transition=transition_jsx(t)
 assert 'if(!tl.nullLayer)transitionOpacityLayers.push(tl)' in transition
 assert "transitionOpacityLayers[ci].property" in transition # null opacity alone would silently omit the fade

def test_real_web_frozen_camera_and_heat_samples_pass_native_validation_for_every_combination():
 import subprocess
 root=Path(__file__).resolve().parents[1]
 script="""
 const load=require('./tests/load-ts-module.cjs'),{freezeWuxiaScene}=load('lib/stdWuxiaNative.ts'),{WUXIA_MOTIONS}=load('lib/stdWuxiaMotion.ts');
 const result=WUXIA_MOTIONS.map(m=>{const p={project_payload:{structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',preview_duration_seconds:2,states:[{asset_id:'a',sha256:'a'.repeat(64),media_url:'/api/std/media?bucket=b&path=a.png',start:0,end:1,face_exclusion_boxes:[[.3,.25,.6,.55]]}],graphics:[]}]},scenes:[{scene_number:1,image_effect:m.id+'+heat'}]}}};return freezeWuxiaScene(p,1,[],0,2,24,{metadata:{}})});process.stdout.write(JSON.stringify(result));
 """
 timelines=json.loads(subprocess.check_output(['node','-e',script],cwd=root/'auth-web'))
 assert len(timelines)==15
 for t in timelines:validate(t)
