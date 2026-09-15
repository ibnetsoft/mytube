import copy
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from worker.grounded_script import validate_source, validate_citations, validate_grounding_review
from worker import codex_local_console as console


def source():
    # Artificial test fixture, not an actual Bible translation.
    return {'id':'a'*32,'kind':'scripture','title':'테스트 자료','locator':'테스트 1:1',
            'translation':'인공 테스트 본문','permission_notes':'테스트 전용', 'text':'그는 집으로 돌아왔습니다.'}


def candidate():
    return {'sections':[{'scene_order':1,'text':'그는 집으로 돌아왔습니다.', 'kind':'scripture',
                        'citations':[{'source_id':'a'*32,'quote':'그는 집으로 돌아왔습니다.',
                        'claim':'그는 집으로 돌아왔습니다.','locator':'테스트 1:1','translation':'인공 테스트 본문'}]}]}


def test_exact_source_and_quote():
    assert validate_source(source())['sha256']
    assert len(validate_citations(candidate(),[source()]))==1


@pytest.mark.parametrize('key,value',[('quote','없는 원문'),('claim','없는 대본'),('source_id','b'*32),
                                    ('locator','테스트 99:1'),('translation','다른 번역')])
def test_bad_citations_rejected(key,value):
    result=candidate();result['sections'][0]['citations'][0][key]=value
    with pytest.raises(ValueError):validate_citations(result,[source()])


def test_commentary_not_scripture():
    row=source();row['kind']='commentary'
    with pytest.raises(ValueError):validate_citations(candidate(),[row])


def test_missing_evidence_and_source_limits():
    result=candidate();result['sections'][0]['citations']=[]
    with pytest.raises(ValueError):validate_citations(result,[source()])
    row=source();row['text']='가'*40001
    with pytest.raises(ValueError):validate_source(row)
    row=source();row['translation']=''
    with pytest.raises(ValueError):validate_source(row)


def test_review_must_be_grounded():
    with pytest.raises(ValueError):validate_grounding_review({'verdict':'pass','issues':[],'checks':{}},candidate()['sections'])


def test_local_source_library_and_snapshots(tmp_path,monkeypatch):
    monkeypatch.setattr(console,'OUT',tmp_path)
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    row=source();row.pop('id')
    response=client.post('/api/references',json=row)
    assert response.status_code==200
    identity=response.json()['id']
    assert client.get('/api/references').json()['items'][0]['characters']==len(row['text'])
    assert client.get('/api/references/'+identity).json()['text']==row['text']
    assert console.load_sources([identity])[0]['sha256']
    with pytest.raises(ValueError):console.load_sources(['../secret'])
    with pytest.raises(ValueError):console.load_sources([identity,identity])
    assert client.post('/api/jobs',json={'mode':'grounded','title':'설교','perspective':'본문 중심','passage':'1:1','source_ids':[]}).status_code==409


def test_grounded_request_requires_scripture(tmp_path,monkeypatch):
    monkeypatch.setattr(console,'OUT',tmp_path)
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    row=source();row['kind']='commentary';row.pop('id')
    identity=client.post('/api/references',json=row).json()['id']
    response=client.post('/api/jobs',json={'mode':'grounded','title':'설교','perspective':'본문 중심','passage':'1:1','source_ids':[identity]})
    assert response.status_code==409
    assert '성경 원문' in response.json()['detail']


def test_grounded_stages_pin_astra(monkeypatch,tmp_path):
    import codex_content_runner as runner
    import subprocess,json
    monkeypatch.setattr(runner,'OUTPUT_DIR',tmp_path)
    calls=[]
    def fake(command,**kwargs):
        calls.append(command)
        Path(command[command.index('--output-last-message')+1]).write_text('{}',encoding='utf-8')
        return subprocess.CompletedProcess(command,0,'','')
    monkeypatch.setattr(runner.subprocess,'run',fake)
    runner.CodexStagedContentRunner(runner.CodexContentConfig('codex','other-model',60))._stage('test','02_grounded_write',{},'Write from sources')
    assert calls[0][calls[0].index('--model')+1]=='gpt-6-astra'
    assert 'untrusted data' in calls[0][-1]
    assert 'supplied YouTube' not in calls[0][-1]


@pytest.mark.parametrize('bad',[False,True])
def test_grounded_pipeline_mocked_no_paid_generation(monkeypatch,bad):
    from worker.grounded_script import produce_grounded
    import codex_content_runner as runner
    monkeypatch.setattr(runner,'_pacing_schedule',lambda duration:[{'scene_number':1,'duration_seconds':duration}])
    monkeypatch.setattr(runner,'_scene_char_budgets',lambda scenes,payload:[{'scene_order':1,'min_chars':1,'max_chars':100}])
    calls=[]
    class FakeRunner:
        def _stage(self,identity,name,context,task):
            calls.append(name)
            if name=='02_grounded_write':
                assert context['sources'][0]['text']==source()['text']
                value=candidate()
                if bad:value['sections'][0]['citations'][0]['quote']='missing'
                return value
            if name=='02_grounded_source_review':
                check={'pass':True,'evidence':'synthetic fixture only','scene_order':1,'script_quote':source()['text']}
                return {'verdict':'pass','issues':[],'checks':{key:dict(check) for key in
                    ('citation_coverage','context','interpretation_separation','illustration_labeling','translation','theological_scope')}}
            if name.startswith('02f_listener_'):
                return {'verdict':'pass','issues':[],'strengths':[{'scene_order':1,'quote':source()['text'],'reason':'fixture only'}]}
            if name=='02e_dialogue':return {'scenes':[{'scene_number':1,'spans':[]}]}
            raise AssertionError(name)
    request={'grounded_type':'sermon','duration_minutes':1,'title':'test','audience':'test','perspective':'test','passage':'test','notes':''}
    if bad:
        with pytest.raises(ValueError):produce_grounded('test',request,[source()],FakeRunner(),lambda stage:None)
        assert calls==['02_grounded_write','02_grounded_write']
    else:
        result=produce_grounded('test',request,[source()],FakeRunner(),lambda stage:None)
        assert result['script_model']=='gpt-6-astra'
        assert result['source_manifest'][0]['sha256']
        assert result['grounding_report']['verdict']=='pass'
        assert result['production_ready'] is False
        assert '02e_dialogue' in calls
