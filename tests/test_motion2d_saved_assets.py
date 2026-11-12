import copy
import shutil
import sys
from pathlib import Path

import imageio_ffmpeg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
import motion2d_mvp
from motion2d_saved_assets import prepare_and_render, sha256
from test_motion2d_mvp import fixture


def setup(tmp_path):
    _, data = fixture(tmp_path)
    source, voice = tmp_path / data['source'], tmp_path / data['audio']
    image_sha, audio_sha = sha256(source), sha256(voice)
    def asset(ident, name, kind, metadata):
        return {'id':ident,'project_id':'p','scene_number':1,'asset_type':kind,'status':'uploaded','metadata':{'gcs_bucket':'b','gcs_path':str(tmp_path/name),**metadata}}
    image=asset('image','source.png','image',{})
    audio=asset('audio','voice.wav','audio',{'sha256':audio_sha})
    patch_files={'mouth_closed':'closed.png','mouth_half':'closed.png','mouth_open':'open.png','blink':'blink.png','hair':'hair.png'}
    patches={r:asset(r,f,'other',{'kind':'motion2d_patch','role':r,'imageId':'image','imageSha256':image_sha,'sha256':sha256(tmp_path/f)}) for r,f in patch_files.items()}
    background=asset('bg','source.png','other',{'kind':'region_layer_upload','role':'background','imageId':'image','imageSha256':image_sha,'sha256':image_sha})
    return {'version':1,'project_id':'p','scene':1,'image':image,'image_sha256':image_sha,'audio':audio,'audio_sha256':audio_sha,'audio_start':0,'patches':patches,'background':background}


def download(bucket, key, target):
    assert bucket == 'b'
    shutil.copyfile(key,target)


def test_saved_patches_render_and_verify(tmp_path, monkeypatch):
    snapshot=setup(tmp_path)
    monkeypatch.setattr(motion2d_mvp, 'rhubarb_cues', lambda *a:[{'start':0,'end':1,'pose':'half'},{'start':1,'end':2,'pose':'open'}])
    result=prepare_and_render(snapshot,tmp_path/'job',download,'ignored')
    assert result['patch_assets']['mouth_open']=='mouth_open'
    assert imageio_ffmpeg.count_frames_and_secs(result['output']) == (96,4.0)
    assert result['original_sha256']==snapshot['image_sha256']


@pytest.mark.parametrize('change', ['wrong_project','wrong_source','wrong_hash','missing_background'])
def test_rejects_unrelated_or_changed_assets(tmp_path, change):
    snapshot=setup(tmp_path)
    if change=='wrong_project': snapshot['patches']['blink']['project_id']='other'
    if change=='wrong_source': snapshot['patches']['blink']['metadata']['imageId']='other'
    if change=='wrong_hash': snapshot['patches']['blink']['metadata']['sha256']='0'*64
    if change=='missing_background': snapshot['background']=None
    with pytest.raises(ValueError): prepare_and_render(snapshot,tmp_path/'job',download,'ignored')
    assert not (tmp_path/'job'/'motion2d.mp4').exists()
