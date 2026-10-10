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
