import sys
from pathlib import Path
import numpy as np
from PIL import Image
from moviepy import VideoClip
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import motion_automation_worker as worker

def test_video_review_receives_time_aligned_input_frames(tmp_path,monkeypatch):
    source=tmp_path/'uploaded.mp4'
    def frame(t):
        pixels=np.full((36,64,3),90,dtype='uint8');pixels[:,int(t*40):int(t*40)+8]=[200,40,30]
        return pixels
    with VideoClip(frame,duration=.5) as clip:
        clip.write_videofile(str(source),fps=12,codec='libx264',audio=False,logger=None,threads=1)
    reference=tmp_path/'saved-still.png';Image.fromarray(frame(0)).save(reference)
    monkeypatch.setattr(worker,'pcm',lambda *args:np.ones(4000,dtype='float32'))
    seen=[]
    class Reviewer:
        def _stage(self,job,stage,context,task):
            seen.append(context)
            assert context['paired_source_times']
            expected=[Path(p) for p in context['_local_image_paths'] if 'expected-source-' in p]
            actual=[Path(p) for p in context['_local_image_paths'] if Path(p).name.startswith('actual-')]
            assert len(expected)==len(actual)==len(context['paired_source_times'])
            assert all('paired ground truth' in label for label in context['image_labels'][-len(expected):])
            for a,b in zip(actual,expected):
                with Image.open(a) as x,Image.open(b) as y:
                    assert np.abs(np.asarray(x).astype('float32')-np.asarray(y).astype('float32')).mean()<3
            return {'passed':True,'critical_issues':[], 'checks':[{'id':key,'passed':True,'evidence':'fixture source/output frame pair checked'} for key in context['required_checks']]}
    plan={'scene':{'keys':[{'t':0},{'t':1}],'effects':[]}}
    result=worker.review_output(Reviewer(),source,reference,source,{'number':1,'start':0,'end':.5,'_source_video_path':str(source)},plan,tmp_path,lambda:None)
    assert result['passed'] and seen
