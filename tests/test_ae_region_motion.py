import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_region_motion import validate_input, phase, prepare_layers, write_jsx


def fixture():
    return {'timeline':{'duration':5,'subtitles':[{'id':'s1','start':1,'end':5}]},'regions':[{'id':'hand','name':'손','polygon':[[.2,.2],[.4,.2],[.4,.5],[.2,.5]],'anchor':[.3,.2],'action':'rotate','amplitude':12,'period':2,'cycles':2,'subtitleId':'s1','start':1}]}


def test_start_end_and_repeated_cycle():
    r=fixture()['regions'][0]
    assert phase(r,0)==phase(r,1)==phase(r,5)==phase(r,7)==0
    assert phase(r,1.5)==pytest.approx(1)
    assert phase(r,2.5)==pytest.approx(-1)
    assert phase(r,3.5)==pytest.approx(1)


@pytest.mark.parametrize('patch',[{'action':'eval'},{'period':0},{'amplitude':float('nan')},{'cycles':99},{'start':0},{'polygon':[[0,0],[1,0],[1,1],[0,1]]}])
def test_rejects_unsafe_or_out_of_range(patch):
    d=fixture();d['regions'][0].update(patch)
    with pytest.raises(ValueError):validate_input(d)


def test_unreviewed_runtime_layer_generation_is_disabled(tmp_path):
    from PIL import Image,ImageDraw
    import numpy as np
    source=tmp_path/'original.png';image=Image.new('RGB',(320,200),'white');ImageDraw.Draw(image).rectangle((64,40,128,100),fill='red');image.save(source)
    d=fixture();d['imageSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='검수·승인'):prepare_layers(source,tmp_path/'layers',d)


def test_resolves_native_output_module_extension(tmp_path):
    from ae_region_motion import rendered_media
    requested = tmp_path / "native-job.avi"
    actual = tmp_path / "native-job.mp4"
    actual.write_bytes(b"rendered")
    assert rendered_media(requested) == actual
    requested.write_bytes(b"ambiguous")
    with pytest.raises(RuntimeError):
        rendered_media(requested)


def rig():
    d = fixture()
    root = {**d['regions'][0], 'id': 'body', 'action': 'hold'}
    upper = {**root, 'id': 'thigh', 'parentId': 'body', 'action': 'walk', 'amplitude': 25, 'phaseOffset': .5}
    lower = {**upper, 'id': 'calf', 'parentId': 'thigh', 'walkPart': 'lower', 'amplitude': 60}
    d['regions'] = [lower, root, upper]
    return d


def test_joint_rig_validates_unordered_hierarchy():
    assert validate_input(rig())['regions'][0]['parentId'] == 'thigh'


@pytest.mark.parametrize('patch', [{'parentId': 'missing'}, {'parentId': 'calf'}, {'phaseOffset': 2}, {'restAngle': 181}, {'walkPart': 'script'}])
def test_rejects_invalid_joint_graph_and_gait(patch):
    data = rig(); data['regions'][0].update(patch)
    with pytest.raises(ValueError): validate_input(data)


def test_emitted_ae_script_parents_before_animation_and_preserves_rig_data(tmp_path):
    data = rig();runtime = {'width': 320, 'height': 200, 'duration': 5, 'background': 'plate.png', 'regions': [{**r, 'path': r['id']+'.png'} for r in data['regions']]}
    script = tmp_path/'rig.jsx'
    write_jsx(runtime, tmp_path/'rig.aep', tmp_path/'out.avi', script)
    text = script.read_text()
    assert text.index("l.parent=layers['region:'+r.parentId]") < text.index('prop.setValueAtTime')
    assert "bases['region:'+r.id]" in text and 'Math.max(0,wave)' in text
    payload = json.loads(text.split('var D=',1)[1].split(';\n',1)[0])
    assert payload['regions'][0]['walkPart'] == 'lower'
    assert payload['regions'][0]['parentId'] == 'thigh'
    assert payload['regions'][0]['phaseOffset'] == .5
