import copy
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_native import NativeTimeline, pose_at, ticks, color, validate_scene
from filmcraft_render import PIN, VERSION, CONTRACT


def scene_plan():
    return {'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1+t*.1,rotation=0,opacity=100) for t in (0,1)],'effects':[],'transition':'cut'}


def test_default_delivery_and_caption_metrics_match_measured_benchmark():
    from filmcraft_profile import encoding_profile,caption_metrics
    settings=encoding_profile(CONTRACT,(1920,1080),24)
    assert settings['bitrateKbps']==1540 and settings['maxBitrateKbps']==2000
    assert settings['hardwareEncoding']=='auto' and settings['audio']['bitrateKbps']==192
    assert settings['audio']['channels']==1
    face=dict(units=1000,win_height=1448,win_descent=288,ascent=1000,descent=-200)
    size,margin=caption_metrics(face,1920*5.4*2.8/440,1.1,1080)
    assert size==pytest.approx(45.56504269211451) and margin==pytest.approx(6/1080)
    assert encoding_profile(CONTRACT,(1080,1920),24)['bitrateKbps']==1540


def test_native_captions_reject_missing_glyphs(monkeypatch):
    import filmcraft_native as native
    monkeypatch.setattr(native,'font_coverage',lambda family:frozenset(map(ord,'音A')))
    native.validate_caption_glyphs('Selected',[{'text':'音 A\n'}])
    with pytest.raises(ValueError,match='声'):
        native.validate_caption_glyphs('Selected',[{'text':'音声'}])


def test_recorded_fractional_caption_boundaries_remain_contiguous():
    from filmcraft_native import caption_commands,TICKS
    boundaries=[0,2.22040816326529,2.8995918367346575,7.157551020408107,9.351836734693847,12.747755102040798,16.22204081632651]
    commands=caption_commands([dict(start=a,end=b,text='音声') for a,b in zip(boundaries,boundaries[1:])],24)
    for (_,a),(_,b) in zip(commands,commands[1:]):
        assert a['time']+round(a['durationSeconds']*TICKS)==b['time']
    assert commands[-1][1]['time']==306*TICKS//24


def test_native_contract_binds_adapter_and_rejects_missing_geometry():
    snapshot={'renderer':{'revision':PIN['revision'],'adapter':VERSION},'motion':{}}
    scene={'source_kind':'image'};plan=scene_plan()
    validate_scene(snapshot,scene,plan)
    for invalid in ({**plan,'native':{'rig':True}},{**plan,'effects':[{'type':'heat_distortion'}]}):
        with pytest.raises(ValueError):validate_scene(snapshot,scene,invalid)
    assert pose_at(plan['keys'],.5)['scale']==pytest.approx(1.05)
    assert color('#12345600')=='#12345600'
    assert ticks(1/24)*24==254016000000


def test_native_camera_uses_original_source_and_editable_keys_without_rasterization():
    native=object.__new__(NativeTimeline);native.size=(1920,1080);native.fps=24;native.scene_clips=[]
    commands=[]
    native.place=lambda path,*args,**kwargs:(7,{'video':{'width':320,'height':180,'par':[1,1]},'duration':10*254016000000})
    native.batch=lambda batch:commands.extend(batch)
    scene={'source_kind':'image','number':1,'start':10,'end':12}
    native.source_scene(scene,scene_plan(),Path('original.png'),10)
    scale=[p for command,p in commands if p['effect']=='motion' and p['param']=='scale']
    assert [p['value'] for p in scale]==pytest.approx([600,660])
    assert [p['time'] for p in scale]==[ticks(10),ticks(12)]
    assert all(p['keyframe'] for p in scale)
    assert native.scene_clips[0]['source'].endswith('original.png')


def test_native_sfx_overlap_allocates_distinct_audio_tracks():
    native=object.__new__(NativeTimeline);native.duration=4;native.sfx_ends=[]
    native.import_media=lambda path:(1,{'duration':254016000000})
    calls=[]
    native.audio_clip=lambda *args,**kwargs:calls.append((args,kwargs))
    native.soundtrack('voice.wav',{},[{'path':'cue.wav','start':.5},{'path':'cue.wav','start':.75},{'path':'cue.wav','start':2}])
    assert [args[3] for args,_ in calls]==['A1','A3','A4','A3']


def test_native_master_sources_cannot_regress_to_review_mp4s_or_pixel_frames():
    # This source guard protects the architectural requirement, not individual CLI spelling.
    import filmcraft_native,filmcraft_render
    text=Path(filmcraft_native.__file__).read_text(encoding='utf-8')+Path(filmcraft_render.__file__).read_text(encoding='utf-8')
    for dependency in ('MotionFrames','moviepy','render_ffmpeg_slideshow','frames_dir'):
        assert dependency not in text
    assert CONTRACT['gpu_composition']=='required'


def test_worker_routes_originals_to_native_master_and_preserves_legacy_compositor(monkeypatch,tmp_path):
    import filmcraft_render
    import services.ffmpeg_slideshow_service as legacy
    from motion_automation_worker import assemble_master
    received={}
    def native(snapshot,**kwargs):received['native']=kwargs;return tmp_path/'native.mp4'
    def old(**kwargs):received['legacy']=kwargs;return str(tmp_path/'legacy.mp4')
    monkeypatch.setattr(filmcraft_render,'render_master',native)
    monkeypatch.setattr(legacy,'render_ffmpeg_slideshow',old)
    snapshot={'final_renderer':{'engine':'filmcraft'},'renderer':{'engine':'filmcraft'},'motion':{'aspect':'16:9'},
        'scenes':[{'number':1,'start':0,'end':2}],'subtitles':[]}
    arguments=dict(sources={1:'original.jpg'},plans=[{'number':1}],voice='recording.wav',
        ordered=[{'number':1,'path':'review-intermediate.mp4'}],settings={},cues=[],overlay=None,
        final_dir=tmp_path,fresh=lambda:None,ai_sources={})
    assert assemble_master(snapshot,**arguments).name=='native.mp4'
    assert 'legacy' not in received
    assert received['native']['sources']=={1:'original.jpg'}
    assert 'ordered' not in received['native']
    snapshot['renderer']['engine']='effectcraft'
    snapshot.pop('final_renderer')
    assert assemble_master(snapshot,**arguments).name=='legacy.mp4'
    assert received['legacy']['images']==['review-intermediate.mp4']
    assert received['legacy']['image_effects']==['none']
    assert received['legacy']['transition_effects']==['none']
    snapshot['renderer']['engine']='filmcraft'
    assert assemble_master(snapshot,**arguments).name=='legacy.mp4'
    snapshot['renderer']['engine']='effectcraft'
    import services.filmcraft_final_service as final
    monkeypatch.setattr(final,'render_final',lambda **kwargs:received.setdefault('final',kwargs) and tmp_path/'filmcraft-final.mp4')
    snapshot['final_renderer']={'engine':'filmcraft'}
    assert assemble_master(snapshot,**arguments).name=='filmcraft-final.mp4'
    assert received['final']['images']==['review-intermediate.mp4']
    assert 'sources' not in received['final'] and 'plans' not in received['final']
