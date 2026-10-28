"""Static-frame reuse must preserve pixels, cuts, animated keys and effect timing."""
import copy
import numpy as np
from PIL import Image
from services.motion_render_service import MotionFrames,compose_frame

def setup(tmp_path,scene):
    paths=[]
    for i,color in enumerate(['red','blue']):
        p=tmp_path/f'{i}.png';Image.new('RGB',(64,48),color).save(p);paths.append(str(p))
    motion=dict(version=1,enabled=True,aspect='16:9',fps=24,scenes={'1':scene,'2':copy.deepcopy(scene)})
    return MotionFrames(paths,[1,1],[],{'motion':motion},(96,54),'',[1,2])

def neutral():return dict(source='image',fit='contain',direction='',keys=[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in [0,1]],effects=[],transition='cut')

def test_static_pixels_and_cut_are_preserved(tmp_path):
    scene=neutral();frames=setup(tmp_path,scene)
    try:
        first=frames.frame(0);expected=compose_frame(Image.new('RGB',(64,48),'red'),scene,.5,(96,54))
        assert np.array_equal(first,expected)
        assert frames.frame(.5) is first
        following=frames.frame(1);assert not np.array_equal(first,following)
        assert frames.frame(1.5) is following
    finally:frames.close()

def test_animated_pose_is_not_frozen(tmp_path):
    scene=neutral();scene['keys'][1]['scale']=1.5;frames=setup(tmp_path,scene)
    try:
        assert not np.array_equal(frames.frame(0),frames.frame(.9))
        assert frames._still_frame is None
    finally:frames.close()

def test_fade_transition_is_not_frozen(tmp_path):
    scene=neutral();scene['transition']='fade';frames=setup(tmp_path,scene)
    try:
        assert not np.array_equal(frames.frame(0),frames.frame(.2))
        assert frames._still_frame is None
    finally:frames.close()

def test_effect_window_is_not_frozen(tmp_path):
    scene=neutral();scene['effects']=[dict(type='impact_flash',start=.2,end=.8,intensity=.8,center=[.5,.5],radius=.5,color=[1,1,1])];frames=setup(tmp_path,scene)
    try:
        assert not np.array_equal(frames.frame(.1),frames.frame(.5))
        assert frames._still_frame is None
    finally:frames.close()
