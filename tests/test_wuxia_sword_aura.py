import json,sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from worker.wuxia_sword_aura import prepare,validate_alpha,protection_mask
from worker.ambient_loop import digest,prepare_runtime

def test_isolated_aura_changes_phase_but_never_original_or_protected_blade(tmp_path):
 base=Image.new('RGB',(240,140),(25,35,40));d=ImageDraw.Draw(base);d.line([(105,60),(190,40)],fill=(30,160,255),width=8)
 d.line([(100,80),(195,70)],fill=(180,180,190),width=4)
 source=tmp_path/'source.png';plate=tmp_path/'plate.png';base.save(source);Image.new('RGB',base.size,(25,35,40)).save(plate)
 spec={'source_reviewed':True,'source_sha256':digest(source),'reason':'visible blue sword energy', 'region':[.4,.2,.85,.65], 'protected_regions':[[0,0,.3,1]],'protected_polygons':[[[.38,.5],[.85,.45],[.85,.6],[.38,.65]]],'amplitude_px':3,'end_ms':5000}
 loop=prepare(source,plate,spec,tmp_path/'patches');assert digest(source)==spec['source_sha256']
 images=[Image.open(f['local_path']) for f in loop['frames']]
 assert len({im.tobytes() for im in images})==16
 for im in images:validate_alpha(loop,im.getchannel('A'))
 bad=Image.new('L',base.size);ImageDraw.Draw(bad).rectangle((130,75,132,77),fill=255)
 with pytest.raises(ValueError,match='protected'):validate_alpha(loop,bad)
 spec['source_sha256']='0'*64
 with pytest.raises(ValueError,match='exact source'):prepare(source,plate,spec,tmp_path/'bad')

def test_aura_output_review_samples_different_actual_patch_phases():
 from worker.wuxia_motion_review import evidence
 t={'auto_motion_policy':{'actual_output_review_required':True},'states':[{'asset_id':'a','sha256':'a'*64,'ambient_loops':[{'sword_aura':{'contract':'wuxia_sword_aura/v1'}}]}], 'samples':[{'at':i/24,'state':'a','motion':{},'ambient':[{'loop':0,'frame':i%16}]} for i in range(48)]}
 e=evidence({'wuxia_timeline':t},2,24)
 assert 'wuxia_sword_aura_execution' in e['required_checks']
 assert len({str(s['ambient']) for s in e['frozen_samples']})>1
 assert e['source_states'][0]['sword_aura']
