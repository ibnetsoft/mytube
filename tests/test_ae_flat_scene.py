import json
import sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_flat_scene import prepare, write_jsx, VERSION

def args(tmp_path):
    source=tmp_path/'original.png';Image.new('RGB',(640,360),'navy').save(source)
    scene={'number':1,'start':0,'end':1,'source_kind':'image'}
    motion={'aspect':'16:9','fps':30}
    direction={'fit':'contain','keys':[{'t':t,'x':.5,'y':.5,'scale':1+t*.05,'rotation':0,'opacity':100} for t in (0,1)],'effects':[]}
    return source,scene,motion,direction

def test_original_camera_and_frame_rate_go_to_native_ae_without_synthetic_layers(tmp_path):
    source,scene,motion,direction=args(tmp_path);p=prepare(source,scene,motion,direction)
    assert p['plan']['camera']==direction['keys']
    assert p['layers']=={'original':source}
    assert p['fps']==30
    jsx=tmp_path/'scene.jsx';write_jsx(p['plan'],p['layers'],tmp_path/'scene.aep',tmp_path/'native.avi',jsx,1,30)
    text=jsx.read_text();data=json.loads(text.split(';\n',1)[0][8:])
    assert data['fps']==30 and data['duration']==1
    assert 'base=Math.min(O.width/W,O.height/H)' in text
    assert 'layer.audioEnabled=false' in text
    assert 'P.camera[a].opacity' in text
    assert 'timeRemap' not in text and 'MoviePy' not in text

def test_short_video_and_invalid_camera_are_rejected_before_ae(tmp_path,monkeypatch):
    from ae_scene_production import _video_info
    import ae_scene_production
    source,scene,motion,direction=args(tmp_path)
    monkeypatch.setattr(ae_scene_production,'_video_info',lambda _:dict(width=640,height=360,duration=.8))
    with pytest.raises(ValueError,match='shorter'):prepare(source,{**scene,'source_kind':'video'},motion,direction)
    direction['keys'][1]['scale']=9
    with pytest.raises(ValueError,match='camera'):prepare(source,scene,motion,direction)

def test_old_python_motion_cache_cannot_count_as_an_ae_render():
    from motion_automation_worker import renderer_cache_is_current
    from services.video_playback_policy import POLICY
    snapshot={'scenes':[{'number':1,'source_kind':'image'}]}
    record={'number':1,'video_playback_policy':POLICY}
    assert not renderer_cache_is_current(snapshot,record)
    assert renderer_cache_is_current(snapshot,{**record,'adobe_flat_renderer':VERSION})
