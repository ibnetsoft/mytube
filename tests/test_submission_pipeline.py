import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from submission_pipeline import recorded_rows, validate_layers
from ae_mouth_automation import automatic_phase
from ae_mouth_runtime import claimable_filter

def test_new_submission_has_no_model_approval_phase():
    assert automatic_phase({'pipeline_version': 2, 'automatic': True, 'state': 'queued'}) is None
    assert automatic_phase({'pipeline_version': 2, 'automatic': True, 'state': 'artifact_ready'}) == 'auto_enqueue'
    assert 'artifact_ready' in claimable_filter()

def test_saved_speaker_is_not_reinterpreted():
    rows = recorded_rows({'subtitles': [{'text':'hello','kind':'dialogue','speaker':'Jiro'}, {'text':'narration','kind':''}]})
    assert rows[0]['speaker'] == 'Jiro'
    assert rows[1]['kind'] == 'narration'
    with pytest.raises(ValueError): recorded_rows({'subtitles':[{'kind':'dialogue'}]})

def test_missing_prepared_layers_never_calls_generator(monkeypatch,tmp_path):
    import prepared_mouth_layers
    monkeypatch.setattr(prepared_mouth_layers, 'reuse_prepared', lambda *args: False)
    with pytest.raises(ValueError, match='keep selected original'): validate_layers(tmp_path/'image',{})

def test_completed_voice_preview_is_reused_when_submit_arrives_during_preview():
    from submission_pipeline import ready_scene_artifacts
    snapshot={'audio':{'id':'audio'},'scenes':[{'number':23,'start':0,'end':3,'image':{'id':'image'}}]}
    meta={'artifact_ready':True,'timing_locked':True,'duration_seconds':3,'source_image_id':'image',
          'source_audio_id':'audio','ae_mouth_fingerprint':'recipe','render_sha256':'a'*64}
    asset={'id':'clip','asset_type':'video','status':'uploaded','scene_number':23,'metadata':meta}
    assert ready_scene_artifacts(snapshot,[asset],'recipe')[23]['asset_id']=='clip'
    assert ready_scene_artifacts(snapshot,[{**asset,'metadata':{**meta,'source_audio_id':'wrong'}}],'recipe')=={}


@pytest.mark.parametrize('extra', [{'kind':'mouth_preview'}, {'timing_mode':'preview_cycle'}, {'voice_synced':False}])
def test_pose_preview_is_never_reused_as_final_dialogue_even_with_matching_duration(extra):
    from submission_pipeline import ready_scene_artifacts
    snapshot={'audio':{'id':'audio'},'scenes':[{'number':19,'start':120,'end':123,'image':{'id':'image'}}]}
    meta={'artifact_ready':True,'timing_locked':True,'duration_seconds':3,'source_image_id':'image',
          'source_audio_id':'audio','ae_mouth_fingerprint':'recipe','render_sha256':'a'*64,**extra}
    asset={'id':'preview','asset_type':'video','status':'uploaded','scene_number':19,'metadata':meta}
    assert ready_scene_artifacts(snapshot,[asset],'recipe')=={}


def test_final_lips_follow_changed_scene_length_and_each_actual_speakers_interval():
    from ae_mouth import amplitude_cues
    samples=[1000,-1000]*int(14*8000/2)
    rows=[{'speaker':'A','start':121,'end':124},{'speaker':'B','start':127,'end':131}]
    for name in ('A','B'):
        cues=amplitude_cues(samples,[r for r in rows if r['speaker']==name],start=120,duration=14)
        def pose(t): return next(c['pose'] for c in reversed(cues) if c['at_seconds']<=t)
        assert pose(2) in ('half','open') if name=='A' else pose(2)=='closed'
        assert pose(8) in ('half','open') if name=='B' else pose(8)=='closed'
        assert pose(12)=='closed'
        assert cues[-1]['pose']=='closed'

def test_ae_retry_is_bounded_and_does_not_retry_input_errors():
    from submission_pipeline import render_prepared_scene
    class Renderer:
        calls=0
        def _render_job(self,*args,**kwargs):
            self.calls+=1
            if self.calls==1: raise RuntimeError('aerender timeout')
            return {'local_path':'ready'}
    renderer=Renderer()
    assert render_prepared_scene(renderer,object(),True)['local_path']=='ready'
    assert renderer.calls==2
    renderer=Renderer()
    with pytest.raises(RuntimeError): render_prepared_scene(renderer,object(),False)
    assert renderer.calls==1

def test_technical_preparation_has_no_repeated_visual_review(tmp_path, monkeypatch):
    import prepared_mouth_layers as prepared
    import ae_mouth
    monkeypatch.setattr(prepared, 'ROOT', tmp_path/'cache')
    image=tmp_path/'source';image.write_bytes(b'source')
    from test_mouth_geometry import speaker as verified_speaker
    speaker=verified_speaker();speaker['speaker']='Jiro'
    speaker['mouth_geometry']['source_sha256']=ae_mouth.digest(image)
    def layers(_generator,_image,row,directory):
        directory.mkdir(parents=True,exist_ok=True)
        result={}
        for pose in ae_mouth.POSES:
            file=directory/(pose+'.png');file.write_bytes(pose.encode());result[pose]=str(file)
        return result
    monkeypatch.setattr(ae_mouth,'mouth_layers',layers)
    reviews=[]
    monkeypatch.setattr(ae_mouth,'review_layers',lambda *args: reviews.append('initial review'))
    geometry={'state':'ready','source_sha256':ae_mouth.digest(image),'speakers':[speaker]}
    assert prepared.prepare_scene(image,geometry,generator=object(),technical=True)['state']=='ready'
    monkeypatch.setattr(ae_mouth,'review_layers',lambda *args: pytest.fail('cached patches must not be reviewed again'))
    assert prepared.prepare_scene(image,geometry,generator=object(),technical=True)['state']=='ready'
    assert reviews==['initial review']
    assert prepared.reuse_prepared(image,dict(speaker))
