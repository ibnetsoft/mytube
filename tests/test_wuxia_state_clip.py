import copy
import hashlib
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from wuxia_state_clip import prepare, jsx, CONTRACT

def fixture(tmp_path):
    source=tmp_path/'source.mp4';source.write_bytes(b'fixture video')
    clip=dict(contract=CONTRACT,asset_id='v',source_state_sha256='a'*64,sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              width=1280,height=720,duration_seconds=2,source_in_seconds=.5,play_seconds=1,start_offset_seconds=0)
    timeline=dict(state_clip_contract=CONTRACT,states=[dict(asset_id='s',sha256='a'*64,clip=clip)],
                  samples=[dict(at=i/24,state='s',video=dict(asset_id='v',source_seconds=.5+i/24),mouths=[],ambient=[],effects={}) for i in range(24)])
    return source,timeline

def run_prepare(tmp_path,timeline,source):
    return prepare(timeline,tmp_path/'prepared',lambda:None,lambda descriptor,path:path.write_bytes(source.read_bytes()),
                   probe=lambda p:dict(width=1280,height=720,duration=2,codec='h264'),decode=lambda p:None)

def test_preserves_source_clock_and_mutes_video(tmp_path):
    source,t=fixture(tmp_path);run_prepare(tmp_path,t,source)
    script=jsx(t)
    assert 'vl.audioEnabled=false' in script
    assert 'timeRemapEnabled=true' in script
    assert 'whold(tm)' in script
    assert t['samples'][-1]['video']['source_seconds']==.5+23/24

@pytest.mark.parametrize('failure',['hash','artwork','speed','interval','mouth'])
def test_refuses_invalid_or_stale_clip(tmp_path,failure):
    source,t=fixture(tmp_path)
    if failure=='hash':t['states'][0]['clip']['sha256']='b'*64
    if failure=='artwork':t['states'][0]['sha256']='b'*64
    if failure=='speed':t['samples'][2]['video']['source_seconds']+=.01
    if failure=='interval':t['states'][0]['clip']['play_seconds']=3
    if failure=='mouth':t['samples'][0]['mouths']=[dict(pose='open')]
    with pytest.raises(ValueError):run_prepare(tmp_path,t,source)

def test_real_ffmpeg_clip_decodes_and_matches_metadata(tmp_path):
    from ae_media_utils import ffmpeg,run
    source=tmp_path/'actual.mp4'
    run([ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=c=blue:s=1280x720:r=24:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
    _,t=fixture(tmp_path);t['states'][0]['clip']['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    prepare(t,tmp_path/'actual-prepared',lambda:None,lambda d,p:p.write_bytes(source.read_bytes()))
    assert Path(t['states'][0]['clip']['file']).is_file()

def test_requires_updated_worker_acknowledgement(tmp_path):
    from wuxia_worker_contract import claim_acknowledgement
    _,t=fixture(tmp_path);t['contract']='wuxia_native_timeline/v3'
    snapshot={'scenes':[{'wuxia_timeline':t}]}
    ack=claim_acknowledgement(snapshot,{'required_worker_contract':CONTRACT},'lease')
    assert ack['worker_contract_ack']=={'contract':CONTRACT,'lease_token':'lease'}
    with pytest.raises(ValueError):claim_acknowledgement(snapshot,{},'lease')
