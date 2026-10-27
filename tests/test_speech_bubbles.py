import sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import pytest
from speech_bubbles import *

def spec():return {'contract':CONTRACT,'cues':[dict(text='안녕',speaker='수진',style='rounded',reason='gentle greeting')]}
def layout():return dict(status='ready',evidence='Visible speaker at lower right; empty upper left',bubbles=[dict(text='안녕',speaker='수진',style='rounded',start_seconds=0,end_seconds=1,box=[.08,.08,.4,.28],speaker_anchor=[.6,.5],protected_boxes=[[.58,.46,.7,.62]],speaker_evidence='Same clothing and face as named cast')])
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
 for box in ([.1,.1,.3,.2],[.45,.33,.52,.4]):
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
 receipt['speech_bubble_layout']=layout();receipt['review']['batches']=[review(['bubble_readability','bubble_speaker_tail','bubble_occlusion'])]
 require_reviewed_outputs(snapshot,[receipt],'voice')

def test_recorded_speaker_and_narration_are_not_guessed():
 for row in (dict(text='안녕',start=0,end=1),dict(text='안녕',dialogue_kind='narration',dialogue_speaker='수진',start=0,end=1),dict(text='안녕',dialogue_kind='dialogue',dialogue_speaker='다른사람',start=0,end=1)):
  with pytest.raises(ValueError):bind(spec(),[row],0,1)
