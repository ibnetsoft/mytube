import hashlib,sys
from pathlib import Path
import numpy as np
import pytest
from moviepy import VideoClip
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from motion_source_repair import validate_repair,verify_repair

def fixture(tmp_path):
    source=tmp_path/'source.bin';source.write_bytes(b'original')
    scene={'source_kind':'video','source':{'id':'source','metadata':{}},'start':10,'end':11}
    recipe={'contract':'recorded_source_prefix/v1','source_asset_id':'source','source_sha256':hashlib.sha256(b'original').hexdigest(),
            'audio_id':'audio','retained_source_frames':7,'duration':1,'fps':24}
    return source,scene,recipe

def test_source_repair_is_bound_to_frozen_asset_audio_and_clock(tmp_path):
    source,scene,recipe=fixture(tmp_path)
    assert validate_repair(recipe,scene,source,'audio') is recipe
    for field,value in [('source_asset_id','other'),('audio_id','other'),('duration',2),('retained_source_frames',0)]:
        with pytest.raises(ValueError):validate_repair({**recipe,field:value},scene,source,'audio')
    scene['source']['metadata']['ae_mouth_fingerprint']='recorded'
    with pytest.raises(ValueError):validate_repair(recipe,scene,source,'audio')

def test_repaired_video_must_match_original_prefix_and_held_frame(tmp_path):
    original=tmp_path/'original.mp4';repaired=tmp_path/'repaired.mp4'
    def frame(t):
        p=np.full((36,64,3),60,dtype='uint8');p[:,int(t*30):int(t*30)+10]=[180,50,80];return p
    for path,fn in [(original,frame),(repaired,lambda t:frame(min(t,.25)))]:
        with VideoClip(fn,duration=1) as clip:clip.write_videofile(str(path),fps=24,codec='libx264',audio=False,logger=None,threads=1)
    recipe={'sha256':hashlib.sha256(repaired.read_bytes()).hexdigest(),'fps':24,'duration':1,'retained_source_frames':7}
    assert verify_repair(recipe,original,repaired)['passed']
    with pytest.raises(ValueError):verify_repair({**recipe,'retained_source_frames':15},original,repaired)
