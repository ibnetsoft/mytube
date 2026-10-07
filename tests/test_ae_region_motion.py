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


def test_layers_and_background_preserve_dimensions_and_alpha(tmp_path):
    from PIL import Image,ImageDraw
    import numpy as np
    source=tmp_path/'original.png';image=Image.new('RGB',(320,200),'white');ImageDraw.Draw(image).rectangle((64,40,128,100),fill='red');image.save(source)
    d=fixture();d['imageSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    runtime=prepare_layers(source,tmp_path/'layers',d)
    assert (runtime['width'],runtime['height'])==(320,200)
    layer=Image.open(runtime['regions'][0]['path']);assert layer.mode=='RGBA';assert layer.getpixel((90,60))[3]==255;assert layer.getpixel((0,0))[3]==0
    background=np.asarray(Image.open(runtime['background']));assert background[70,90,1]>230
    before=source.read_bytes();write_jsx(runtime,tmp_path/'scene.aep',tmp_path/'out.avi',tmp_path/'script.jsx')
    assert source.read_bytes()==before
    script=(tmp_path/'script.jsx').read_text();assert 'AIR_REGION_MOTION' in script;assert 'KeyframeInterpolationType.LINEAR' in script
    d['imageSha256']='0'*64
    with pytest.raises(ValueError):prepare_layers(source,tmp_path/'invalid',d)
