import uuid
import pytest
from worker.script_guidelines import approved_guidelines, propose, review, record_outcome


class Store:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def request(self, method, table, **kwargs):
        self.calls.append((method, table, kwargs))
        if method == 'GET':
            return self.rows, len(self.rows)
        if method == 'POST':
            return [{**kwargs['body'], 'version': 1}], 1
        return self.rows, len(self.rows)

    def get(self, identity):
        if identity != 'a'*32:
            raise ValueError('Unknown job')


def test_scope_and_reproducible_version_snapshot():
    rows = [dict(id=str(uuid.uuid4()),version=i,title='Rule',instruction='Preserve era',category=c,language=l)
            for i,c,l in [(1,'',''),(2,'옛날이야기','ja'),(3,'음악',''),(4,'','en')]]
    store = Store(rows)
    selected, text = approved_guidelines(store, {'category':'옛날이야기','language':'ja'})
    assert [r['version'] for r in selected] == [1,2]
    assert '지침 v2' in text and '지침 v3' not in text
    assert store.calls[0][2]['params']['status'] == 'eq.approved'


def test_pending_submission_requires_evidence_and_does_not_auto_approve():
    store = Store()
    row = propose(store,dict(title='Fix',issue='Wrong era',instruction='Check era',source_job_id='a'*32))
    assert 'status' not in row  # DB default is pending.
    assert row['source_job_id'] == 'a'*32
    with pytest.raises(ValueError):
        propose(store,dict(title='Fix',issue='',instruction='Check era'))
    with pytest.raises(ValueError):
        propose(store,dict(title='Fix',issue='Wrong era',instruction='Check era',source_job_id='b'*32))


def test_review_compare_and_set_and_retirement_reason():
    store = Store([{'status':'approved'}])
    identity = str(uuid.uuid4())
    review(store, identity, 'approve', 'verified')
    assert store.calls[-1][2]['params']['status'] == 'eq.pending'
    with pytest.raises(ValueError):
        review(store,identity,'retire','')
    review(store,identity,'retire','Superseded')
    assert store.calls[-1][2]['params']['status'] == 'eq.approved'
    with pytest.raises(ValueError):
        review(Store(),identity,'approve','')


def test_outcome_keeps_applied_instruction_and_evaluation_without_full_script():
    store = Store()
    record_outcome(store,{'id':'a'*32,'title':'Story','status':'awaiting_approval'},
        {'category':'옛날이야기','language':'ja'},
        {'script':'Full text', 'applied_guidelines':[{'version':2,'instruction':'Check era'}], 'script_quality_report':{'score':90}})
    body = store.calls[-1][2]['body']
    assert body['applied_versions'][0]['version'] == 2
    assert body['evaluation']['script_quality_report']['score'] == 90
    assert 'script' not in body


def test_generation_wrapper_carries_guidance_and_freezes_snapshot(monkeypatch,tmp_path):
    from worker import codex_local_workflow as workflow
    seen=[]
    rows=[dict(id='v',version=1,title='Rule',instruction='Check era')]
    monkeypatch.setattr('worker.script_guidelines.approved_guidelines',lambda store,request:(rows,'Approved guidance'))
    monkeypatch.setattr(workflow,'_produce',lambda identity,request,*args:(seen.append(request) or {'script':'New'}))
    result=workflow.produce('a'*32,{'notes':'User requirements'},None,tmp_path,lambda _:None)
    assert seen[0]['notes']=='User requirements'
    assert seen[0]['_approved_guidance']=='Approved guidance'
    assert result['applied_guidelines'][0]['instruction']=='Check era'


def test_repair_feedback_becomes_pending_once():
    store=Store()
    job={'id':'a'*32,'title':'Repair','status':'awaiting_approval'}
    request={'mode':'repair','notes':'Remove era errors','category':'옛날이야기','language':'ja'}
    record_outcome(store,job,request,{})
    proposal=[args['body'] for method,table,args in store.calls if method=='POST' and table=='script_guideline_versions'][0]
    assert proposal['status']=='pending' and proposal['instruction']==request['notes']
    store.rows=[{'id':proposal['id']}]
    store.calls.clear()
    record_outcome(store,job,request,{})
    assert not any(method=='POST' and table=='script_guideline_versions' for method,table,_ in store.calls)
