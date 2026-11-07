import sys,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_transition import validate,jsx
from wuxia_worker_contract import claim_acknowledgement

def timeline():
 return {'contract':'wuxia_native_timeline/v4','samples':[{'at':0,'transition':{
  'contract':'wuxia_transition_samples/v1','kind':'dissolve','dx':0,'dy':0,'scale':1,
  'opacity':0,'flash':0,'backdrop':1,'issues':[]}}]}

def test_old_worker_and_missing_or_unsafe_frames_never_skip_transitions():
 t=timeline();validate(t)
 for mutate in [lambda t:t.update(contract='wuxia_native_timeline/v3'),lambda t:t['samples'][0].pop('transition'),
                lambda t:t['samples'][0]['transition'].update(scale=2),lambda t:t['samples'][0]['transition'].update(dx=float('nan'))]:
  bad=copy.deepcopy(t);mutate(bad)
  with pytest.raises(ValueError):validate(bad)
 assert claim_acknowledgement({'scenes':[{'wuxia_timeline':t}]},{'required_worker_contract':t['contract']},'lease')['worker_contract_ack']['contract']==t['contract']

def test_ae_moves_complete_scene_and_captures_original_lettering_opacity_before_writing_keys():
 s=jsx(timeline())
 assert 'transitionChildren[ti].parent=transitionRig' in s
 assert s.index('originalOpacity.push(values)')<s.index('originalOpacity[ci][ti]*f.opacity')
 assert 'whold(tt.property' in s and 'wuxia_transition_previous_still' in s

def test_transition_backdrop_requires_actual_png_and_matching_sha(tmp_path):
 from PIL import Image
 from ambient_loop import digest
 from wuxia_native_timeline import prepare
 image=tmp_path/'a.png';Image.new('RGB',(32,18),'red').save(image)
 ref={'asset_id':'a','sha256':digest(image),'ambient_loops':[],'dialogue_mouths':[]}
 t=timeline();t.update(states=[ref],graphics={},transition_source=ref.copy());t['samples'][0].update(state='a',graphics=[],effects={})
 def download(ref,target):target.write_bytes(image.read_bytes())
 r=prepare(t,tmp_path/'runtime',lambda:None,download,1,1)
 assert Path(r['transition_source']['file']).exists()
 t['transition_source']['sha256']='0'*64
 with pytest.raises(ValueError,match='checksum'):prepare(t,tmp_path/'bad',lambda:None,download,1,1)
