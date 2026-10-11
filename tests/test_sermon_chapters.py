"""Synthetic Scripture fixtures only; no real Bible text or paid model/TTS calls."""
import copy
import json
import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from worker.sermon_chapters import (produce_sermon, chapter_minutes, fingerprint, validate_outline)
from worker.grounded_script import validate_source
from worker import codex_local_console as console


def source():
    return validate_source({'id':'a'*32,'kind':'scripture','title':'인공 테스트','locator':'테스트 1:1',
        'translation':'인공 본문','permission_notes':'테스트 전용','text':'인공 테스트 본문입니다.'})


def audit(number=1):
    return {'verdict':'pass','issues':[], 'summary':'인공 테스트 요약', 'checks':{k:{'pass':True,
        'evidence':'인공 근거','chapter_number':number,'script_quote':source()['text']} for k in
        ('continuity','repetition','perspective','source_scope')}}


def package():
    s=source()
    section={'scene_order':1,'text':s['text'],'kind':'scripture','citations':[{'source_id':s['id'],
        'quote':s['text'],'claim':s['text'],'locator':s['locator'],'translation':s['translation']}]}
    checks={k:{'pass':True,'evidence':'인공 근거','scene_order':1,'script_quote':s['text']} for k in
        ('citation_coverage','context','interpretation_separation','illustration_labeling','translation','theological_scope')}
    return {'script':s['text'],'sections':[section],'source_manifest':[s],
        'grounding_report':{'verdict':'pass','issues':[],'checks':checks},
        'content_setting':{'language':'ko'},'script_model':'fixture',
        'structure':{'scenes':[{'duration_seconds':2,'scene_order':1,'scene_text':s['text']}]}}


def candidate():
    chapters=[]
    for i in (1,2):
        p=package()
        chapters.append({'chapter_number':i,'title':f'인공 {i}장','status':'reviewed',
            'package':p,'package_hash':fingerprint(p),'continuity_review':audit(i)})
    return {'script':'\n\n'.join(c['package']['script'] for c in chapters),'language':'ko',
        'sermon_plan':{'profile':'sermon_chapters/v1','chapters':chapters,
                       'target_duration_seconds':4,'final_review':audit()}}


def test_duration_scope_and_even_chapters():
    assert chapter_minutes(135,15)==[15]*9
    assert sum(chapter_minutes(122,15))==122
    assert max(chapter_minutes(122,15))-min(chapter_minutes(122,15))<=1
    assert console.StartRequest(mode='grounded',grounded_type='sermon',duration_minutes=360)
    with pytest.raises(ValueError):console.StartRequest(mode='new',duration_minutes=135)
    with pytest.raises(ValueError):console.StartRequest(mode='grounded',grounded_type='education',duration_minutes=135)
    with pytest.raises(ValueError):console.StartRequest(mode='grounded',duration_minutes=361)


def test_outline_requires_registered_scripture_and_packet_limit():
    row={'chapter_number':1,'title':'인공','objective':'인공','transition':'인공','source_ids':['a'*32]}
    assert validate_outline({'chapters':[row]},[source()],[15])[0]['duration_minutes']==15
    with pytest.raises(ValueError):validate_outline({'chapters':[dict(row,source_ids=['b'*32])]},[source()],[15])
    with pytest.raises(ValueError):validate_outline({'chapters':[row]},[dict(source(),kind='commentary')],[15])


def test_failed_second_chapter_resumes_first_and_rejects_changed_sources(tmp_path,monkeypatch):
    import worker.grounded_script as grounded
    calls=[]
    fail={'value':True}
    def generate(identity,request,sources,runner,notify):
        calls.append(identity)
        if identity.endswith('ch002') and fail['value']:raise RuntimeError('interrupted fixture')
        return package()
    monkeypatch.setattr(grounded,'produce_grounded',generate)
    class Runner:
        def _stage(self,identity,name,context,task):
            if name=='02_sermon_outline':return {'chapters':[{'chapter_number':i,'title':f'{i}장',
                'objective':'인공 목표','transition':'인공 연결','source_ids':['a'*32]} for i in range(1,10)]}
            if name=='02_sermon_final_review':return audit()
            return audit(context['chapter']['chapter_number'])
    request={'duration_minutes':135,'chapter_minutes':15,'title':'인공 테스트','passage':'테스트 1:1',
             'audience':'테스트','perspective':'테스트','notes':'','language':'ko','grounded_type':'sermon'}
    with pytest.raises(RuntimeError):produce_sermon('fixture',request,[source()],Runner(),lambda x:None,tmp_path)
    assert (tmp_path/'sermon/chapter-001.json').exists()
    fail['value']=False
    result=produce_sermon('fixture',request,[source()],Runner(),lambda x:None,tmp_path)
    assert calls.count('fixture-ch001')==1
    assert len(result['sermon_plan']['chapters'])==9
    assert [s['scene_order'] for s in result['sections']]==list(range(1,10))
    assert result['structure']['required_video_scene_count']==0
    assert 'CHAPTER' not in result['script']
    with pytest.raises(ValueError,match='변경'):
        produce_sermon('fixture',request,[dict(source(),text='다른 인공 본문')],Runner(),lambda x:None,tmp_path)
    # Corrupt a cached chapter: checksum prevents bypassing independent review.
    path=tmp_path/'sermon/chapter-001.json'
    saved=json.loads(path.read_text());saved['package']['script']='수정된 대본';path.write_text(json.dumps(saved))
    produce_sermon('fixture',request,[source()],Runner(),lambda x:None,tmp_path)
    assert calls.count('fixture-ch001')==2


def test_structured_bible_import_idempotent_search_and_atomic_validation(tmp_path,monkeypatch):
    monkeypatch.setattr(console,'OUT',tmp_path)
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    payload={'translation':'인공 본문','permission_notes':'테스트 전용','verses':[
        {'book':'테스트','chapter':1,'verse':1,'text':'인공 본문 하나'},
        {'book':'테스트','chapter':1,'verse':2,'text':'인공 본문 둘'}]}
    first=client.post('/api/bible/import',json=payload)
    assert first.status_code==200
    assert client.post('/api/bible/import',json=payload).json()==first.json()
    found=client.get('/api/references?book=테스트&chapter=1&verse=2&translation=인공 본문').json()['items']
    assert len(found)==1 and found[0]['verse_start']==2
    broken=copy.deepcopy(payload);broken['verses'][1]['verse']=999
    assert client.post('/api/bible/import',json=broken).status_code==400
    assert len(list((tmp_path/'sources').glob('*.json')))==2
    assert client.get('/api/references/../secrets').status_code!=200


def test_media_real_render_resume_and_tamper_guard(tmp_path):
    from worker.sermon_media_worker import process_sermon,font_path,video_duration
    calls=[]
    def audio(text,target,config,previous,following):
        calls.append(target.name)
        with wave.open(str(target),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
            wav.writeframes(b''.join(struct.pack('<h',int(2000*math.sin(i*2*math.pi*440/48000))) for i in range(96000)))
    config={'voice_id':'fixture','voice_speed':1.,'language':'ko','font_path':font_path()}
    stop_calls={'n':0}
    def stop():stop_calls['n']+=1;return stop_calls['n']>1
    interrupted=process_sermon(candidate(),tmp_path,config,should_stop=stop,audio_fn=audio)
    assert interrupted['status']=='interrupted' and len(calls)==1
    result=process_sermon(candidate(),tmp_path,config,audio_fn=audio)
    assert result['status']=='review_pending' and result['completed_chapters']==2
    assert result['duration_seconds']>=4
    assert len(calls)==2 and len(result['timeline'])==2
    assert video_duration(Path(result['output']))>=4
    process_sermon(candidate(),tmp_path,config,audio_fn=audio)
    assert len(calls)==2
    (tmp_path/'ch001-s0001.wav').write_bytes(b'broken')
    process_sermon(candidate(),tmp_path,config,audio_fn=audio)
    assert len(calls)==3
    bad=candidate();bad['sermon_plan']['chapters'][0]['package']['script']='unreviewed'
    with pytest.raises(ValueError,match='지문|인용'):process_sermon(bad,tmp_path,config,audio_fn=audio)


def test_short_audio_never_claims_target_duration(tmp_path):
    from worker.sermon_media_worker import process_sermon,font_path
    def audio(text,target,*args):
        with wave.open(str(target),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(b'\0\0'*4800)
    config={'voice_id':'fixture','voice_speed':1.,'language':'ko','font_path':font_path()}
    with pytest.raises(ValueError,match='분량 보완'):process_sermon(candidate(),tmp_path,config,audio_fn=audio)
    state=json.loads((tmp_path/'media.json').read_text())
    assert state['status']=='failed' and not (tmp_path/'sermon-final.mp4').exists()


def test_continuity_feedback_repairs_only_current_chapter(tmp_path,monkeypatch):
    import worker.grounded_script as grounded
    requests=[]
    def generate(identity,request,*args):requests.append(request);return package()
    monkeypatch.setattr(grounded,'produce_grounded',generate)
    class Runner:
        def _stage(self,identity,name,context,task):
            if name=='02_sermon_outline':return {'chapters':[{'chapter_number':1,'title':'인공 장',
                'objective':'인공 목표','transition':'인공 연결','source_ids':['a'*32]}]}
            if name=='02_sermon_final_review':return audit()
            if not context['review_feedback']:return {'verdict':'revise','issues':['인공 반복 개선']}
            return audit()
    request={'duration_minutes':15,'chapter_minutes':15,'title':'인공 테스트','passage':'테스트 1:1',
             'audience':'테스트','perspective':'테스트','notes':'','language':'ko','grounded_type':'sermon'}
    result=produce_sermon('fixture',request,[source()],Runner(),lambda x:None,tmp_path)
    assert len(requests)==2 and '인공 반복 개선' in requests[-1]['notes']
    assert result['sermon_plan']['chapters'][0]['status']=='reviewed'


def test_media_queue_requires_current_approval_and_can_set_voice_after_draft(tmp_path):
    from worker.sermon_queue import enqueue
    c=candidate()
    job={'approved_hash':fingerprint(c),'worker_id':'fixtureworker'}
    bundle={'job':job,'candidate':c,'request':{'sermon_voice_id':''}}
    class Jobs:
        root=tmp_path
        worker_id='fixtureworker'
        import threading
        lock=threading.RLock()
        def load(self,identity):return bundle
        def update(self,identity,**fields):job.update(fields)
    with pytest.raises(ValueError,match='음성 ID'):enqueue(Jobs(),'a'*32)
    assert enqueue(Jobs(),'a'*32,'fixturevoice')['status']=='queued'
    assert json.loads((tmp_path/('a'*32)/'request.json').read_text())['sermon_voice_id']=='fixturevoice'
    assert enqueue(Jobs(),'a'*32)['status']=='queued'
    job['worker_id']='otherworker'
    with pytest.raises(ValueError,match='컴퓨터'):enqueue(Jobs(),'a'*32)
    job['worker_id']='fixtureworker'
    with pytest.raises(ValueError,match='변경'):enqueue(Jobs(),'a'*32,'differentvoice')
    job['approved_hash']='obsolete'
    with pytest.raises(ValueError,match='승인'):enqueue(Jobs(),'a'*32)
