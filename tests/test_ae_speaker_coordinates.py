import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_mouth import assess_dialogue, visible_speakers

def test_saved_assignments_need_no_model_call():
    class Runner:
        def _stage(self,*args): raise AssertionError('Saved assignments must not be reclassified')
    rows=[{'index':0,'text':'はい','scene_number':19,'kind':'dialogue','speaker':'娘'},
          {'index':1,'text':'語り','scene_number':20,'kind':'narration','speaker':''},
          {'index':2,'text':'不明','scene_number':21,'kind':'','speaker':''}]
    result=assess_dialogue(Runner(),'saved',{'subtitles':rows})
    assert [r['kind'] for r in result]==['dialogue','narration','uncertain']
    assert result[0]['speaker']=='娘'

def test_mouth_must_be_inside_verified_face():
    row={'speaker':'娘','status':'visible','confidence':.99,'reason':'visual evidence','face_box':[.2,.2,.6,.6],'mouth_box':[.4,.4,.45,.43]}
    assert visible_speakers({'speakers':[row]},['娘'])[0]['face_box']==row['face_box']
    with pytest.raises(ValueError,match='inside'):
        visible_speakers({'speakers':[{**row,'face_box':[.1,.1,.3,.3]}]},['娘'])
