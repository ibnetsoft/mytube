import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import ae_mouth_automation as auto


def test_review_requires_every_check_and_specific_evidence():
    good={'passed':True,'critical_issues':[],'checks':[{'id':'identity','passed':True,'evidence':'The gray-haired man at left matches the source.'}]}
    assert auto.valid_review(good,['identity'])
    for bad in [{}, {**good,'passed':'true'}, {**good,'critical_issues':['drifting mouth']},
                {**good,'checks':[]}, {**good,'checks':[{'id':'identity','passed':True,'evidence':''}]}]:
        assert not auto.valid_review(bad,['identity'])
    assert not auto.valid_review(good,['identity','timing'])


def test_audio_check_detects_changed_voice_and_truncation():
    import numpy as np
    rng=np.random.default_rng(42)
    samples=(rng.normal(size=16000)*1200).astype(int).tolist()
    assert auto.audio_integrity(samples,samples)['correlation']==1
    with pytest.raises(ValueError): auto.audio_integrity(samples,samples[:8000])
    with pytest.raises(ValueError): auto.audio_integrity(samples,list(reversed(samples)))
    with pytest.raises(ValueError): auto.audio_integrity([0]*16000,[0]*16000)


def test_phase_resume_and_legacy_isolation():
    assert auto.automatic_phase({'state':'direction_pending'}) is None
    assert auto.automatic_phase({'automatic':True,'state':'direction_pending'})=='auto_direction'
    assert auto.automatic_phase({'automatic':True,'state':'processing','phase':'auto_review'})=='auto_review'
    assert auto.automatic_phase({'automatic':True,'state':'direction_approved','phase':'auto_direction'}) is None


def test_sample_times_cover_every_utterance_and_end():
    times=auto.sample_times({'start':10,'end':20},[{'start':11,'end':12},{'start':18,'end':19}])
    assert 1.25 in times and 8.65 in times and 9.92 in times
    assert all(0<=t<10 for t in times)


def setup_job(phase,results):
    meta={'automatic':True,'state':'processing','phase':phase,'fingerprint':'f',
          'worker_token':'lease','input':{'scenes':[{'number':r['number']} for r in results]},'results':results}
    return {'id':'job','project_id':'project','metadata':meta},meta


def test_direction_failure_persists_but_next_scene_proceeds(monkeypatch,tmp_path):
    job,meta=setup_job('auto_direction',[{'number':1,'status':'direction_pending'},{'number':2,'status':'direction_pending'}])
    calls=[];saves=[]
    def inspect(*args):
        number=args[2]['number'];calls.append(number)
        if number==1: raise ValueError('face uncertain')
        return {'source_sha256':'proof'},None
    monkeypatch.setattr(auto,'inspect_scene',inspect)
    def save(**changes):meta.update(copy.deepcopy(changes));saves.append(copy.deepcopy(changes))
    auto.run_phase(None,job,meta,tmp_path,tmp_path/'audio',lambda:None,save,lambda:False)
    assert calls==[1,2]
    assert saves[0]['results'][0]['status']=='needs_review'
    assert meta['results'][1]['status']=='direction_approved'
    assert meta['state']=='direction_approved' and meta['phase']=='render'


def test_successful_output_review_is_persisted_before_enqueue(monkeypatch,tmp_path):
    job,meta=setup_job('auto_review',[{'number':1,'status':'review_pending'},{'number':2,'status':'skipped'}])
    monkeypatch.setattr(auto,'inspect_scene',lambda *args:({'render_sha256':'h'}, {'id':'a','updated_at':'v1','metadata':{'render_sha256':'h'}}))
    monkeypatch.setattr(auto.ae,'_supabase',lambda:('db',{}))
    writes=[]
    def request(*args,**kwargs):writes.append(kwargs);return SimpleNamespace(json=lambda:[{'id':'a'}])
    monkeypatch.setattr(auto.ae,'_request',request)
    auto.run_phase(None,job,meta,tmp_path,tmp_path/'audio',lambda:None,lambda **c:meta.update(c),lambda:False)
    assert writes[0]['params']['updated_at']=='eq.v1'
    assert writes[0]['json']['metadata']['ae_reviewed'] is True
    assert meta['results'][0]['status']=='approved'
    assert meta['state']=='reviewed' and meta['phase']=='auto_enqueue' and meta['auto_pending']


def test_uncertain_output_blocks_final_render(monkeypatch,tmp_path):
    job,meta=setup_job('auto_review',[{'number':1,'status':'review_pending'}])
    monkeypatch.setattr(auto,'inspect_scene',lambda *args:(_ for _ in ()).throw(ValueError('mouth drifts')))
    auto.run_phase(None,job,meta,tmp_path,tmp_path/'audio',lambda:None,lambda **c:meta.update(c),lambda:False)
    assert meta['state']=='review_pending' and not meta['auto_pending']
    assert meta['results'][0]['status']=='needs_review'


def test_final_enqueue_receipt_and_bounded_retries(monkeypatch,tmp_path):
    import requests
    job,meta=setup_job('auto_enqueue',[{'number':1,'status':'approved'}])
    monkeypatch.setattr(auto.ae,'_supabase',lambda:('db',{'Authorization':'Bearer fake'}))
    def fail(*args,**kwargs):raise requests.Timeout()
    monkeypatch.setattr(requests,'post',fail)
    for i in range(3):
        auto.run_phase(None,job,meta,tmp_path,None,lambda:None,lambda **c:meta.update(c),lambda:False)
    assert meta['auto_enqueue_attempts']==3 and not meta['auto_pending']
    calls=[]
    def success(*args,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:{'render_queue_id':'queue','status':'pending'})
    monkeypatch.setattr(requests,'post',success)
    auto.run_phase(None,job,meta,tmp_path,None,lambda:None,lambda **c:meta.update(c),lambda:False)
    assert meta['auto_render_queue_id']=='queue' and not meta['auto_pending']
    assert calls[0]['json']['workerToken']=='lease' and calls[0]['allow_redirects'] is False


def test_video_tail_dependency_yields_worker_without_consuming_failure_retries(monkeypatch,tmp_path):
    import requests
    job,meta=setup_job('auto_enqueue',[{'number':1,'status':'approved'}])
    monkeypatch.setattr(auto.ae,'_supabase',lambda:('db',{'Authorization':'Bearer fake'}))
    monkeypatch.setattr(requests,'post',lambda *a,**kw:SimpleNamespace(status_code=409,json=lambda:{'code':'VIDEO_TAIL_PENDING','error':'tail waiting'}))
    auto.run_phase(None,job,meta,tmp_path,None,lambda:None,lambda **c:meta.update(c),lambda:False)
    assert meta['auto_pending'] and meta['auto_not_before']
    assert not meta.get('auto_enqueue_attempts')
    from ae_mouth_runtime import claimable_filter
    assert 'auto_not_before.lt.' in claimable_filter()


def test_real_aac_mux_preserves_finalized_narration(tmp_path):
    from ae_media_utils import ffmpeg, run
    from ae_mouth import decode_scene_audio
    source=tmp_path/'voice.wav';output=tmp_path/'output.m4a'
    run([ffmpeg(),'-v','error','-y','-f','lavfi','-i',
         'aevalsrc=0.25*sin(2*PI*220*t)+0.1*sin(2*PI*430*t):s=48000:d=2',str(source)])
    run([ffmpeg(),'-v','error','-y','-i',str(source),'-c:a','aac',str(output)])
    report=auto.audio_integrity(decode_scene_audio(ffmpeg(),source,0,2),decode_scene_audio(ffmpeg(),output,0,2))
    assert report['correlation']>.9
