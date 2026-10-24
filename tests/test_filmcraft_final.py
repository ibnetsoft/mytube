import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))


def test_completed_effect_video_never_reapplies_authored_effects(monkeypatch,tmp_path):
    import filmcraft_native
    from services.filmcraft_final_service import render_final
    captured=[]
    class Timeline:
        background_clip=0
        def __init__(self,*args):pass
        def call(self,*args):pass
        def shape(self,*args,**kwargs):raise AssertionError('Do not place another background on the completed-video track')
        def import_media(self,path):return 1,{'kind':'Movie'}
        def source_scene(self,scene,plan,source,start):captured.append((scene,plan,source,start))
        def captions(self,*args):pass
        def soundtrack(self,*args):pass
        def export(self):
            path=tmp_path/'native.mp4';path.write_bytes(b'output');return path
    monkeypatch.setattr(filmcraft_native,'NativeTimeline',Timeline)
    render_final(temp_dir=tmp_path,images=['ae-finished.mp4'],durations=[2],audio_path='voice.wav',
        subtitles=[],resolution=(1920,1080),scene_numbers=[25],image_effects=['zoom_in'],
        settings={'motion':{'scenes':{'25':{'effects':[{'type':'impact_flash'}]}}}})
    scene,plan,source,start=captured[0]
    assert scene['source_kind']=='video' and source=='ae-finished.mp4'
    assert plan['effects']==[] and all(k['scale']==1 for k in plan['keys'])


def test_actual_web_executor_routes_final_to_filmcraft_before_python_compositors(monkeypatch,tmp_path):
    import services.remote_render_service as remote
    import services.filmcraft_final_service as final
    from filmcraft_render import CONTRACT
    (tmp_path/'audio').mkdir();(tmp_path/'images').mkdir()
    (tmp_path/'audio/voice.wav').write_bytes(b'voice');(tmp_path/'images/finished.mp4').write_bytes(b'effects')
    config={'final_renderer':'filmcraft','final_renderer_contract':CONTRACT,'audio_filename':'voice.wav',
        'audio_duration':2,'images':['finished.mp4'],'image_timing_starts':[0],'image_effects':['none'],
        'transition_effects':['none'],'render_settings':{},'scene_numbers':[25]}
    (tmp_path/'config.json').write_text(json.dumps(config),encoding='utf8')
    monkeypatch.setattr(remote,'_prepare_narration_audio_for_render',lambda path,*args:(path,2))
    monkeypatch.setattr(remote,'_render_std_template_overlay_png',lambda *args:None)
    calls=[]
    def render(**kwargs):calls.append(kwargs);(tmp_path/'output.mp4').write_bytes(b'native');return tmp_path/'output.mp4'
    monkeypatch.setattr(final,'render_final',render)
    remote.remote_render_executor_func('test',str(tmp_path))
    assert len(calls)==1 and calls[0]['images']==[str(tmp_path/'images/finished.mp4')]
    assert json.loads((tmp_path/'progress.txt').read_text())['progress']>=30
