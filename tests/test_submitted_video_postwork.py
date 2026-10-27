import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import submitted_video_postwork as p
from ae_scene_effects import validate_effects

def fixture(mouth=True):
    rows=[dict(scene_number=1,text='반딧불이 빛났다.',dialogue_kind='dialogue' if mouth else 'narration',start=0.,end=1.,voice_id='voice',speaker='hero')]
    post=dict(contract=p.CONTRACT,source_video_id='source',mouth_required=mouth,dialogue=[dict(rows[0],kind='dialogue')] if mouth else [],cast={},requested_effects=[],transition=None,playback_rate=1,review_required=True)
    direction=dict(source='video',fit='contain',direction='Keep source',keys=[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],effects=[],transition='cut')
    scene=dict(number=1,start=0.,end=1.,source_kind='video',source={'id':'source'},postwork=post,prepared_direction=direction)
    snapshot=dict(submitted_video_postwork=p.CONTRACT,motion=dict(fps=24),subtitles=rows,scenes=[scene])
    response=dict(status='ready',scene={**copy.deepcopy(direction),'transition_seconds':0,'transition_reason':'Preserve recorded end'},ai=None,evidence=['Actual video has a clear focal area'],continuity={k:'Actual source evidence' for k in ('entry','exit','screen_direction','lighting')})
    return scene,snapshot,response

def firefly():
    return dict(type='fireflies',story_quote='반딧불이 빛났다.',reason='The narration explicitly describes these lights in this scene',count=8,size=.002,speed=.01,center=[.2,.2],radius=.15,color=[1,.9,.3],intensity=.2,protected_regions=[],start=0,end=1)

def review(ids):return dict(passed=True,critical_issues=[],checks=[dict(id=k,passed=True,evidence='Actual synthetic test pixels inspected') for k in ids])

def test_contract_cannot_drop_dialogue_or_retime_voice():
    scene,snapshot,_=fixture();p.validate_input(snapshot)
    scene['postwork']['mouth_required']=False
    with pytest.raises(ValueError,match='dialogue'):p.validate_input(snapshot)
    scene['postwork']['mouth_required']=True;scene['postwork']['dialogue'][0]['end']=.8
    with pytest.raises(ValueError,match='timing'):p.validate_input(snapshot)

def test_review_bypass_is_never_allowed_for_submitted_video():
    _,snapshot,_=fixture();assert not p.review_bypass({'review_policy':'skip_user_requested/v1'},snapshot)
    assert p.review_bypass({'review_policy':'skip_user_requested/v1'},{})

def test_fireflies_need_exact_narrative_evidence_and_bounded_native_parameters():
    scene,snapshot,response=fixture(False);response['scene']['effects']=[firefly()]
    result=p.validate_direction(response,scene,snapshot);assert result['scene']['effects'][0]['start']==0 and result['scene']['effects'][0]['end']==1
    for field,bad in [('count',100),('size',.2),('intensity',.9),('protected_regions',[[.5,.5,.2,.2]])]:
        effect=firefly();effect[field]=bad
        with pytest.raises(ValueError):validate_effects({'effects':[effect]})
    response['scene']['effects'][0]['story_quote']='밤 숲이었다.'
    with pytest.raises(ValueError,match='Fireflies'):p.validate_direction(response,scene,snapshot)

def test_no_added_camera_ai_or_unrequested_end_transition():
    scene,snapshot,response=fixture();response['scene']['keys'][1]['scale']=1.05
    with pytest.raises(ValueError,match='camera'):p.validate_direction(response,scene,snapshot)
    scene,snapshot,response=fixture();response['ai']={'duration':1}
    with pytest.raises(ValueError,match='camera'):p.validate_direction(response,scene,snapshot)
    scene,snapshot,response=fixture();response['scene'].update(transition='fade_black',transition_seconds=.2)
    with pytest.raises(ValueError,match='Last scene'):p.validate_direction(response,scene,snapshot)

def test_requested_effect_cannot_disappear_and_tracked_faces_are_protected():
    scene,snapshot,response=fixture();scene['postwork']['requested_effects']=[firefly()]
    with pytest.raises(ValueError,match='생략'):p.validate_direction(response,scene,snapshot)
    response['scene']['effects']=[firefly()];plan=p.validate_direction(response,scene,snapshot)
    scene['_mouth_runtime']={'speakers':[{'tracking':[{'face_box':[.2,.2,.4,.5]},{'face_box':[.3,.2,.5,.5]}]}]}
    p.protect_faces(plan,scene);assert plan['scene']['effects'][0]['protected_regions']==[[.19,.19,.51,.51]]

def test_unreviewed_or_silently_skipped_mouth_cannot_enter_final_assembly():
    scene,snapshot,_=fixture();voice='a'*64;sha='b'*64
    ids=['source_identity','postwork_narrative_fit','source_playback_preserved','transition_plan','dialogue_mouth_timing','tracked_mouth_alignment']
    proof=dict(contract=p.CONTRACT,source_sha256='c'*64,final_voice_sha256=voice,playback_rate=1,mouth_required=True,mouth_applied=True)
    result=dict(number=1,sha256=sha,review=dict(passed=True,render_sha256=sha,final_voice_sha256=voice,batches=[review(ids)]),submitted_video_postwork=proof)
    p.require_reviewed_outputs(snapshot,[result],voice)
    result['submitted_video_postwork']['mouth_applied']=False
    with pytest.raises(ValueError,match='원본 대체'):p.require_reviewed_outputs(snapshot,[result],voice)
    result['submitted_video_postwork']['mouth_applied']=True;result['review']['batches'][0]['passed']=False
    with pytest.raises(ValueError,match='검수'):p.require_reviewed_outputs(snapshot,[result],voice)
    with pytest.raises(ValueError):p.require_final_reviews(snapshot,[])
    p.require_final_reviews(snapshot,[review(['captions','scene_boundary','visual_quality','postwork_continuity','voice_clock_preserved'])])

def test_native_mouth_and_firefly_share_one_source_comp(tmp_path):
    from PIL import Image
    from ae_mouth import digest
    from ae_flat_scene import prepare,write_jsx
    scene,snapshot,_=fixture();scene['source_kind']='image';source=tmp_path/'source.png';Image.new('RGB',(640,360),'navy').save(source)
    layers={}
    for pose in ('closed','half','open'):
        path=tmp_path/(pose+'.png');Image.new('RGB',(20,10),'red').save(path);layers[pose]=str(path)
    scene['_mouth_runtime']={'enabled':True,'video_source':False,'speakers':[{'speaker':'hero','mouth_box':[.2,.2,.3,.3],'layers':layers,'layer_sha256':{k:digest(Path(v)) for k,v in layers.items()},'cues':[{'at_seconds':0,'pose':'closed'},{'at_seconds':.25,'pose':'open'}]}]}
    direction=scene['prepared_direction'];direction['effects']=[firefly()]
    prepared=prepare(source,scene,dict(aspect='16:9',fps=24),direction)
    jsx=tmp_path/'scene.jsx';write_jsx(prepared['plan'],prepared['layers'],tmp_path/'scene.aep',tmp_path/'native.avi',jsx,1,24)
    text=jsx.read_text();assert text.index('var mouthRuntime')<text.index('var layer=source.layers.add(footage)')
    assert 'footage=(function(footage)' in text and 'return footage;})(footage)' in text
    assert 'ae_effect_firefly_' in text and 'bg.stretch' not in text and 'timeRemap' not in text
    Image.new('RGB',(20,10),'blue').save(layers['open'])
    with pytest.raises(ValueError,match='patch changed'):prepare(source,scene,dict(aspect='16:9',fps=24),direction)


def test_actual_video_preparation_is_reviewed_and_cues_use_final_voice(monkeypatch,tmp_path):
    import submitted_video_coordinates as coordinates
    import ae_mouth
    import manga_layer_generation
    from PIL import Image
    scene,snapshot,_=fixture();source=tmp_path/'source.mp4';source.write_bytes(b'unchanged source fixture')
    image=tmp_path/'actual-frame.png';Image.new('RGB',(100,100),'navy').save(image)
    layers={}
    for pose in ('closed','half','open'):
        path=tmp_path/(pose+'.png');Image.new('RGB',(10,10),'red').save(path);layers[pose]=str(path)
    speaker={'speaker':'hero','status':'visible','mouth_box':[.2,.2,.3,.3]}
    calls=[]
    scene['_dialogue_target']={'dialogue':[dict(scene['postwork']['dialogue'][0],local_start=0.,local_end=1.)]}
    def track(*args,**kwargs):
        assert args[2]['source']['id']=='source' and args[3][0]['local_start']==0. and args[3][0]['local_end']==1.
        assert kwargs['local_video']==source and kwargs['allow_analyze'] is True
        return source,image,[speaker],[copy.deepcopy(speaker)],{'source_duration':1},'coordinates'
    monkeypatch.setattr(coordinates,'prepare_submitted_video',track)
    monkeypatch.setattr(ae_mouth,'mouth_layers',lambda *args,**kwargs:layers)
    monkeypatch.setattr(ae_mouth,'review_layers',lambda *args:calls.append('actual_layer_review'))
    monkeypatch.setattr(ae_mouth,'decode_scene_audio',lambda *args:[1000]*8000)
    monkeypatch.setattr(manga_layer_generation,'NativeCodexLayerGenerator',lambda:object())
    voice=tmp_path/'voice.wav';voice.write_bytes(b'finalized voice fixture')
    receipt=p.prepare_mouth(object(),{'id':'job','project_id':'p'},scene,snapshot,source,voice,tmp_path,lambda:None)
    assert calls==['actual_layer_review']
    assert receipt['runtime']['video_source'] is True
    assert receipt['runtime']['audio_sha256']==ae_mouth.digest(voice)
    assert receipt['runtime']['speakers'][0]['cues'][0]['at_seconds']==0
    assert source.read_bytes()==b'unchanged source fixture'
    scene['postwork']['mouth_required']=False
    assert p.prepare_mouth(None,{},scene,snapshot,source,voice,tmp_path,lambda:None) is None


def test_direct_dialogue_targets_reject_wrong_scene_source_or_local_clock():
    scene,snapshot,_=fixture()
    target=dict(scene_number=1,source_video_id='source',scene_start=0.,scene_end=1.,dialogue=[dict(text=r['text'],speaker=r['speaker'],voice_id=r['voice_id'],start=r['start'],end=r['end'],local_start=r['start'],local_end=r['end']) for r in scene['postwork']['dialogue']])
    snapshot['video_dialogue_targets']=dict(contract='video_dialogue_targets/v1',scenes=[target])
    p.validate_input(snapshot)
    assert scene['_dialogue_target']==target
    for key,value in [('scene_number',18),('source_video_id','wrong')]:
        old=target[key];target[key]=value
        with pytest.raises(ValueError,match='target'):p.validate_input(snapshot)
        target[key]=old
    target['dialogue'][0]['local_start']=.2
    with pytest.raises(ValueError,match='target'):p.validate_input(snapshot)
    snapshot['video_dialogue_targets']['scenes']=[]
    with pytest.raises(ValueError,match='target'):p.validate_input(snapshot)


def test_all_parallax_requires_prepared_psds_and_preserves_dialogue_review():
    scene,snapshot,_=fixture();snapshot.pop('submitted_video_postwork');snapshot['all_scene_parallax']='all_scene_parallax/v1'
    scene.update(source_kind='psd',preparation={'ready':True},parallax_plan={'enabled':True},parallax_mouth=scene.pop('postwork'))
    assert p.required_review(snapshot)
    assert not p.review_bypass({'review_policy':'skip_user_requested/v1'},snapshot)
    p.validate_input(snapshot)
    scene['parallax_mouth']['dialogue'][0]['end']=.7
    with pytest.raises(ValueError,match='final voice'):p.validate_input(snapshot)
    scene['source_kind']='image'
    with pytest.raises(ValueError,match='PSDs'):p.validate_input(snapshot)
