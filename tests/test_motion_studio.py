import copy
import json
import pathlib
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw

from services.motion_render_service import EFFECTS, MotionFrames, compose_frame, validate_motion

ROOT=pathlib.Path(__file__).resolve().parents[1]

def scene():
    return dict(source='image',fit='contain',direction='Preserve face; push toward center.',
                keys=[dict(t=t,x=.5,y=.5,scale=1+t*.15,rotation=0,opacity=100) for t in (0,1)],effects=[],transition='cut')

def draft(aspect='16:9'):
    return dict(version=1,enabled=True,aspect=aspect,fps=24,scenes={'1':scene()})

def image():
    image=Image.new('RGB',(320,180),'#25405f');d=ImageDraw.Draw(image)
    d.rectangle((100,30,220,160),fill='#ed6b42');d.ellipse((130,45,190,105),fill='#f4d4b3')
    return image

@pytest.mark.parametrize('aspect,size',[('16:9',(320,180)),('9:16',(180,320))])
def test_frames_preserve_source_and_timeline_with_no_added_transition_time(tmp_path,aspect,size):
    source=tmp_path/'source.png';image().save(source)
    source2=tmp_path/'second.png';Image.new('RGB',(320,180),'green').save(source2)
    frames=MotionFrames([str(source),str(source2)],[1,1],[],{'motion':draft(aspect)},size,'')
    try:
        assert frames.duration==2 and frames.turn==0
        assert frames.frame(.5).shape==(size[1],size[0],3)
        assert not np.array_equal(frames.frame(.5),frames.frame(1.1))
        assert not np.array_equal(frames.frame(.1),frames.frame(.9))
    finally:frames.close()

@pytest.mark.parametrize('kind',sorted(EFFECTS))
def test_every_enabled_effect_changes_actual_pixels_and_stops_after_window(kind):
    base=scene();base['keys'][1]['scale']=1
    active=copy.deepcopy(base);active['effects']=[dict(type=kind,start=.2,end=.8,intensity=.8,center=[.5,.5],radius=.4,color=[1,.7,.2])]
    assert not np.array_equal(compose_frame(image(),base,.45,(320,180)),compose_frame(image(),active,.45,(320,180)))
    assert np.array_equal(compose_frame(image(),base,.9,(320,180)),compose_frame(image(),active,.9,(320,180)))

def test_web_and_worker_agree_on_saved_contract_and_reject_bad_keys():
    value=draft()
    script="const load=require('./tests/load-ts.cjs');const fs=require('fs');const lib=load(require('path').resolve('lib/stdMotionStudio.ts'));process.stdout.write(JSON.stringify(lib.normalizeMotionDraft(JSON.parse(fs.readFileSync(0,'utf8')))));"
    result=subprocess.run(['node','-e',script],cwd=ROOT/'auth-web',input=json.dumps(value),text=True,capture_output=True,check=True)
    assert validate_motion(json.loads(result.stdout))==value
    for change in [lambda v:v['scenes']['1']['keys'].reverse(),lambda v:v['scenes']['1']['keys'][0].update(x=float('nan')),lambda v:v.update(aspect='1:1')]:
        bad=copy.deepcopy(value);change(bad)
        with pytest.raises(ValueError):validate_motion(bad)

def test_real_preview_mp4_round_trip_and_final_psd_is_not_double_animated(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'worker'))
    from motion_preview_worker import render_preview
    from moviepy import VideoFileClip
    source=tmp_path/'input.png';image().save(source)
    snapshot=dict(aspect='9:16',fps=24,duration=1,scene=scene(),asset={'scene_number':1,'file_name':'source.png','metadata':{'gcs_bucket':'test','gcs_path':'source.png'}})
    def download(bucket,key,path):path.write_bytes(source.read_bytes())
    output,sha=render_preview(snapshot,tmp_path/'render',download)
    assert len(sha)==64
    with VideoFileClip(str(output)) as video:
        assert video.size==[360,640]
        assert abs(video.duration-1)<.05
        assert not np.array_equal(video.get_frame(.1),video.get_frame(.9))
    psd=scene();psd.update(source='psd',effects=[dict(type='impact_flash',start=0,end=1,intensity=1,center=[.5,.5],radius=.4,color=[1,1,1])])
    settings={'motion':{**draft(),'scenes':{'1':psd}}}
    frames=MotionFrames([str(source)],[1],[],settings,(320,180),'')
    try:assert np.array_equal(frames.frame(.1),frames.frame(.9))
    finally:frames.close()


@pytest.mark.parametrize('aspect,size',[('16:9',(320,180)),('9:16',(180,320))])
def test_final_motion_export_keeps_recorded_audio_caption_style_fps_and_manifest(tmp_path,aspect,size):
    import wave
    from moviepy import VideoFileClip
    from services.motion_render_service import render_motion
    source=tmp_path/'source.png';image().save(source)
    audio=tmp_path/'voice.wav'
    with wave.open(str(audio),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
        wav.writeframes((np.sin(np.arange(8000)*2*np.pi*220/8000)*2000).astype('<i2').tobytes())
    settings={'motion':{**draft(aspect),'fps':30},'subtitle_font_family':'NanumSquareExtraBold','subtitle_text_color':'#00ff00','subtitle_bg_enabled':False}
    output=render_motion(temp_dir=str(tmp_path),images=[str(source)],durations=[1],audio_path=str(audio),subtitles=[dict(start=0,end=1,text='Motion')],settings=settings,resolution=size,scene_numbers=[1])
    with VideoFileClip(output) as result:
        assert result.size==list(size) and result.fps==30
        assert abs(result.duration-1)<.08 and result.audio is not None
    manifest=json.loads((tmp_path/'motion_manifest.json').read_text())
    assert manifest['motion']['aspect']==aspect and len(manifest['source_sha256'][0])==64
    assert manifest['review_status']=='rendered_not_automatically_approved'
    assert '&H0000FF00' in (tmp_path/'subtitles.fast.ass').read_text(encoding='utf-8-sig')
