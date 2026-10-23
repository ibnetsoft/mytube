import json
from pathlib import Path
import numpy as np
import pytest
from moviepy import VideoClip,VideoFileClip,AudioClip
from services.video_playback_policy import require_video_duration,require_original_video_asset,VideoPlaybackError

def test_short_video_reports_shortfall_without_freeze_or_loop():
    with pytest.raises(VideoPlaybackError,match='7번 씬.*길이가 부족'):
        require_video_duration(6,8,24,7)
    require_video_duration(8,6,24,7)
    require_video_duration(6,6.01,24,7)

def test_known_frozen_source_is_rejected():
    with pytest.raises(VideoPlaybackError):
        require_original_video_asset({'metadata':{'kind':'repaired_source_clip'}},1)
    with pytest.raises(VideoPlaybackError):
        require_original_video_asset({'metadata':{'tail_policy':'hold_last_frame'}},19)
    require_original_video_asset({'metadata':{}},1)

def test_real_compositor_keeps_video_time_and_cuts_without_repeating(tmp_path):
    from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
    paths=[]
    for number in (0,1):
        path=tmp_path/f'{number}.mp4'
        def frame(t,n=number):
            a=np.zeros((72,128,3),dtype='uint8');a[:,:,n]=40+int(t*140);return a
        with VideoClip(frame,duration=1) as clip:
            clip.write_videofile(str(path),fps=24,codec='libx264',audio=False,logger=None,threads=1)
        paths.append(str(path))
    audio=tmp_path/'voice.wav'
    import wave
    with wave.open(str(audio),'wb') as clip:
        clip.setnchannels(1);clip.setsampwidth(2);clip.setframerate(8000);clip.writeframes(bytes(32000))
    out=render_ffmpeg_slideshow(temp_dir=str(tmp_path),images=paths,audio_path=str(audio),durations=[1,1],subtitles=[],subtitle_settings={},image_effects=['none']*2,transition_effects=['none']*2,resolution=(128,72))
    graph=(tmp_path/'ffmpeg.fast.filter.txt').read_text()
    assert 'tpad' not in graph
    assert 'concat=n=2' in graph
    assert 'setpts=2' not in graph
    with VideoFileClip(out) as clip:
        assert abs(clip.duration-2)<.05
        for t in (.2,.7,1.2,1.7):
            expected=40+int((t%1)*140);channel=0 if t<1 else 1
            assert abs(float(clip.get_frame(t)[:,:,channel].mean())-expected)<12
    with pytest.raises(VideoPlaybackError,match='길이가 부족'):
        render_ffmpeg_slideshow(temp_dir=str(tmp_path),images=[paths[0]],audio_path=str(audio),durations=[2],subtitles=[],subtitle_settings={},image_effects=['none'],transition_effects=['none'],resolution=(128,72))
