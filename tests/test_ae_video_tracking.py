import sys
import subprocess
from pathlib import Path
import numpy as np
import cv2
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_video_tracking import track_video
from ae_mouth import mouth_jsx
from ae_video_tail import video_tail_jsx
from ae_media_utils import ffmpeg


def clip(tmp_path, cut=False):
    rng=np.random.default_rng(123)
    face=rng.integers(40,220,(72,64,3),dtype=np.uint8)
    frames=[]
    for i in range(18):
        frame=np.full((144,256,3),30,np.uint8)
        if cut and i>=9:
            frame=rng.integers(0,255,frame.shape,dtype=np.uint8)
        else:
            frame[30:102,60+i:124+i]=face
        frames.append(frame)
    reference=tmp_path/'reference.png';cv2.imwrite(str(reference),frames[0])
    video=tmp_path/'moving.mp4'
    subprocess.run([ffmpeg(),'-y','-f','rawvideo','-pix_fmt','bgr24','-s','256x144','-r','24','-i','pipe:0',
        '-c:v','libx264','-crf','12',str(video)],input=b''.join(f.tobytes() for f in frames),capture_output=True,check=True)
    speaker={'speaker':'A','status':'visible','face_box':[60/256,30/144,124/256,102/144],
             'mouth_box':[80/256,75/144,100/256,85/144]}
    return video,reference,[speaker]


def test_actual_video_translation_is_tracked_and_tail_keeps_last_position(tmp_path):
    video,reference,speakers=clip(tmp_path)
    first,tracked,report=track_video(video,reference,speakers,tmp_path/'track',1.2)
    assert first.is_file()
    assert report['frames_checked']==18
    assert report['source_duration']==pytest.approx(.75)
    assert tracked[0]['tracking'][-1]['offset'][0]==pytest.approx(17,abs=1.2)
    assert tracked[0]['tracking'][-1]['offset'][1]==pytest.approx(0,abs=.5)
    assert tracked[0]['tracking'][-1]['scale']==pytest.approx(100,abs=2)


def test_scene_cut_cannot_silently_reassign_the_speaker(tmp_path):
    video,reference,speakers=clip(tmp_path,cut=True)
    with pytest.raises(ValueError):
        track_video(video,reference,speakers,tmp_path/'track',1.2)


def test_video_plate_freezes_but_mouth_animation_does_not():
    jsx=mouth_jsx({'enabled':True,'video_source':True,'speakers':[]})
    assert 'originalMouthPlate.stretch = 100' in jsx
    assert 'plateRemap.setValueAtTime(DUR, lastFrame)' in jsx
    assert 'motion.offset[0]' in jsx
    tail=video_tail_jsx()
    assert 'needsTail && !mouthRuntime.video_source' in tail
    assert 'videoScale.setValueAtTime(sourceDuration' in tail
