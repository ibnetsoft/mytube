import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from uploaded_video_passthrough import eligible,VERSION,SOURCE_VERSION
from motion_automation_worker import render_base,renderer_cache_is_current

def fixture():
    direction={'source':'video','fit':'contain','keys':[{'t':t,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100} for t in (0,1)],'effects':[]}
    return {'number':1,'source_kind':'video','prepared_direction':direction},{'number':1,'scene':direction,'ai':None}

def test_unmodified_uploaded_video_never_calls_adobe_or_ffmpeg(tmp_path,monkeypatch):
    scene,plan=fixture();source=tmp_path/'original.mp4';source.write_bytes(b'original-upload-bytes');calls=[]
    import ae_scene_production
    monkeypatch.setattr(ae_scene_production,'_render_native',lambda *a,**k:pytest.fail('AE must not render an unchanged video'))
    result=render_base({},scene,plan,source,None,None,tmp_path,lambda:calls.append('fresh'))
    assert result==source and source.read_bytes()==b'original-upload-bytes' and calls==['fresh']

@pytest.mark.parametrize('change',['camera','effect','mouth','bubbles','ai','psd'])
def test_visual_work_still_requires_rendering(change):
    scene,plan=fixture();scene=copy.deepcopy(scene);plan=copy.deepcopy(plan)
    if change=='camera':plan['scene']['keys'][1]['scale']=1.1
    elif change=='effect':plan['scene']['effects']=[{'type':'fireflies'}]
    elif change=='mouth':scene['postwork']={'mouth_required':True}
    elif change=='bubbles':scene['speech_bubble_plan']={'cues':[{}]}
    elif change=='ai':plan['ai']={'start':0}
    else:scene['source_kind']='psd'
    assert not eligible(scene,plan)

def test_previous_ae_output_is_not_reused_for_passthrough():
    scene,plan=fixture()
    from services.video_playback_policy import POLICY
    snapshot={'scenes':[scene]};base={'number':1,'video_playback_policy':POLICY,'adobe_flat_renderer':'adobe_flat_scene/v1'}
    assert not renderer_cache_is_current(snapshot,base)
    assert renderer_cache_is_current(snapshot,{**base,'source_passthrough':SOURCE_VERSION})


def test_offscreen_or_unapplied_mouth_does_not_force_an_empty_ae_render():
    scene,plan=fixture();scene['postwork']={'mouth_required':True}
    assert not eligible(scene,plan)
    assert eligible(scene,plan,runtime_resolved=True)
    scene['_mouth_runtime']={'enabled':True,'speakers':[{}]}
    assert not eligible(scene,plan,runtime_resolved=True)


def test_plain_still_image_goes_directly_to_final_composition(tmp_path,monkeypatch):
    scene,plan=fixture();scene['source_kind']='image';scene['still_mouth']={'mouth_required':False}
    source=tmp_path/'original.png';source.write_bytes(b'original-image-bytes')
    import ae_scene_production
    monkeypatch.setattr(ae_scene_production,'_render_native',lambda *a,**k:pytest.fail('No-op still must not launch Adobe'))
    assert eligible(scene,plan)
    assert render_base({},scene,plan,source,None,None,tmp_path,lambda:None)==source

def test_still_with_fade_keeps_visual_render_path():
    scene,plan=fixture();scene['source_kind']='image';plan['scene']['transition']='fade_black'
    assert not eligible(scene,plan,runtime_resolved=True)
