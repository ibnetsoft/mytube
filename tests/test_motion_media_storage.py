import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import motion_media_storage as storage
from effectcraft_render import _scene_script

def test_render_media_uses_configured_drive_without_moving_review_images(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'ROOT',tmp_path/'project')
    monkeypatch.setenv('AIR_MOTION_MEDIA_ROOT',str(tmp_path/'media'))
    work=storage.ROOT/'output/codex-local-console/motion-automation/job/scene-1/attempt-0'
    work.mkdir(parents=True)
    target=storage.media_directory(work)
    assert target==tmp_path/'media/job/scene-1/attempt-0'
    assert target.is_dir() and work.is_dir()
    assert storage.media_directory(tmp_path/'unrelated')==tmp_path/'unrelated'

def test_short_video_imports_the_actual_last_frame_only_after_source_end():
    script=_scene_script({'generic':True,'video_tail':{'path':'actual-last-frame.png','start':6,'policy':'hold_original_last_frame'}})
    assert 'original_last_frame_hold' in script
    assert 'tail.inPoint=S.video_tail.start;tail.outPoint=S.duration' in script
    assert 'timeRemap' not in script
