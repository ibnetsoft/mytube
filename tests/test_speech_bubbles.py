import sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import pytest
from speech_bubbles import *

def spec():return {'contract':CONTRACT,'cues':[dict(text='안녕',speaker='수진',style='rounded',reason='gentle greeting')]}
def layout():return dict(status='ready',evidence='Visible speaker at lower right; empty upper left',bubbles=[dict(text='안녕',speaker='수진',style='rounded',start_seconds=0,end_seconds=1,box=[.08,.08,.4,.28],speaker_anchor=[.45,.18],protected_boxes=[[.44,.13,.52,.3]],speaker_evidence='Same clothing and face as named cast')])
def test_script_requires_exact_confirmed_spans():
 scene={'dialogue_spans':[dict(text='안녕',speaker='수진',status='confirmed')]}
 assert validate_script({'speech_bubble_plan':spec()},scene)==spec()
 for style in ('thought','narration','unknown'):
  value=spec();value['cues'][0]['style']=style
  with pytest.raises(ValueError):validate_script({'speech_bubble_plan':value},scene)
 with pytest.raises(ValueError):validate_script({},scene)
def test_recorded_clock_and_repeated_lines():
 value=spec();value['cues']+=copy.deepcopy(value['cues'])
 bound=bind(value,[dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='수진',start=10,end=11),dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='수진',start=12,end=13)],10,14)
 assert [c['start_seconds'] for c in bound['cues']]==[0,2]
 with pytest.raises(ValueError):bind(spec(),[dict(text='다른말',start=10,end=11)],10,14)
def test_protected_boxes_and_tail_corridor():
 frozen=bind(spec(),[dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='수진',start=0,end=1)],0,1)
 assert len(validate_layout(layout(),frozen)['bubbles'])==1
 for box in ([.1,.1,.3,.2],[.416,.16,.426,.2]):
  response=layout();response['bubbles'][0]['protected_boxes'].append(box)
  with pytest.raises(ValueError):validate_layout(response,frozen)
 response=layout();response['bubbles'][0]['speaker']='다른사람'
 with pytest.raises(ValueError):validate_layout(response,frozen)
def test_bubbles_cannot_skip_review():
 from submitted_video_postwork import required_review
 assert required_review({'scenes':[{'speech_bubble_plan':spec()}]})
def test_flat_native_writer_injects_presets(tmp_path):
 from ae_flat_scene import write_jsx
 plan={'camera':[dict(t=t,opacity=100) for t in (0,1)],'effects':[],'fit':'contain','layers':[],'speech_bubbles':{'bubbles':[]}}
 jsx=tmp_path/'s.jsx';write_jsx(plan,{},tmp_path/'s.aep',tmp_path/'s.avi',jsx,1)
 text=jsx.read_text();assert 'renderPresetBubbles(comp);' in text
 assert text.index('renderPresetBubbles(comp);')<text.index('var item=app.project.renderQueue')
 assert len(PRESETS)==8


def test_final_gate_rejects_missing_bubble_checks():
 from submitted_video_postwork import require_final_reviews,require_reviewed_outputs
 snapshot={'scenes':[{'number':1,'speech_bubble_plan':spec()}]}
 ids=['captions','scene_boundary','visual_quality','postwork_continuity','voice_clock_preserved']
 def review(keys):return {'passed':True,'critical_issues':[],'checks':[{'id':k,'passed':True,'evidence':'Actual decoded frame'} for k in keys]}
 with pytest.raises(ValueError):require_final_reviews(snapshot,[review(ids)])
 require_final_reviews(snapshot,[review(ids+['bubble_readability','bubble_speaker_tail','bubble_occlusion'])])
 receipt={'number':1,'sha256':'render','review':{'passed':True,'render_sha256':'render','final_voice_sha256':'voice','batches':[review(['bubble_readability'])]}}
 with pytest.raises(ValueError):require_reviewed_outputs(snapshot,[receipt],'voice')
 receipt['speech_bubble_layout']={**layout(),'render_version':2};receipt['review']['batches']=[review(['bubble_readability','bubble_speaker_tail','bubble_occlusion'])]
 require_reviewed_outputs(snapshot,[receipt],'voice')

def test_recorded_speaker_and_narration_are_not_guessed():
 for row in (dict(text='안녕',start=0,end=1),dict(text='안녕',dialogue_kind='narration',dialogue_speaker='수진',start=0,end=1),dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='다른사람',start=0,end=1)):
  with pytest.raises(ValueError):bind(spec(),[row],0,1)

def test_long_tail_is_rejected_before_render():
 frozen=bind(spec(),[dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='수진',start=0,end=1)],0,1)
 response=layout();response['bubbles'][0]['speaker_anchor']=[.7,.55]
 with pytest.raises(ValueError,match='tail too long'):validate_layout(response,frozen)

def test_actual_frame_tracking_moves_entire_bubble_and_keeps_short_tail(tmp_path):
 import cv2,numpy as np
 from speech_bubbles import track_layout
 video=tmp_path/'actual.mp4';rng=np.random.default_rng(12);source=rng.integers(40,210,(360,640,3),dtype=np.uint8)
 writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(640,360))
 for i in range(12):writer.write(cv2.warpAffine(source,np.float32([[1,0,i],[0,1,0]]),(640,360),borderMode=cv2.BORDER_REFLECT))
 writer.release();cue=dict(text='hello',speaker='A',style='dialogue',reason='test',start_seconds=0,end_seconds=.5)
 item={**cue,'box':[.435,.25,.64,.45],'speaker_anchor':[.4,.35],'speaker_face_box':[.2,.2,.4,.55],'speaker_mouth_box':[.25,.4,.31,.45],'protected_boxes':[[.2,.2,.418,.55]],'speaker_evidence':'Known fixture face'}
 checked=validate_layout({'status':'ready','evidence':'Actual translated texture fixture','bubbles':[item]},{'cues':[cue]})
 result=track_layout(video,checked,tmp_path/'tracking',24);c=result['bubbles'][0]
 assert result['render_version']==2 and len(c['tracking'])==12
 assert abs(c['tracking'][-1]['offset'][0]*640-11)<1
 assert abs(c['tracking'][-1]['offset'][1]*360)<1
 assert c['tracking_proof']['frames_checked']==12
 # Measured motion must not bypass protection at later frames.
 checked['bubbles'][0]['protected_boxes'].append([.65,.25,.75,.45])
 with pytest.raises(ValueError,match='protected'):track_layout(video,checked,tmp_path/'bad',24)

def test_native_body_and_tail_have_one_union_before_stroke():
 from speech_bubble_shapes import BUBBLE_JSX
 assert 'ADBE Vector Filter - Merge' in BUBBLE_JSX
 assert BUBBLE_JSX.index('ADBE Vector Filter - Merge')<BUBBLE_JSX.index('ADBE Vector Graphic - Stroke')
 assert "layer.property('Position').setValueAtTime" in BUBBLE_JSX
 assert "label.property('Position').setValueAtTime" in BUBBLE_JSX
