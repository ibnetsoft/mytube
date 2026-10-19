import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from motion_automation_worker import NeedsReview, unseal, validate_direction

def snapshot(mode='ae_only'):
    return {'version':1,'motion':{'version':1,'enabled':True,'aspect':'9:16','fps':24,'automation':{'mode':mode,'max_ai_clips':1,'max_ai_seconds':5}},
            'model_ref':{'id':'provider'} if mode=='hybrid' else None,
            'scenes':[{'number':1,'start':0,'end':20,'source_kind':'image'}]}

def sealed(value):
    raw=json.dumps(value,separators=(',',':'))
    return {'snapshot_json':raw,'fingerprint':hashlib.sha256(raw.encode()).hexdigest()}

def direction():
    return {'status':'ready','scene':{'source':'image','fit':'contain','direction':'Preserve the original face; slow push.',
        'keys':[{'t':t,'x':.5,'y':.5,'scale':1+t*.05,'rotation':0,'opacity':100} for t in (0,1)],'effects':[],'transition':'cut'},
        'evidence':['Original has an orange coat against a blue background.'],
        'continuity':dict(entry='Wide blue room',exit='Orange coat center',screen_direction='Maintain left to right',lighting='Blue ambient'), 'ai':None}

def test_frozen_input_and_mode_boundaries():
    s=snapshot();assert unseal(sealed(s))==s
    bad=sealed(s);bad['snapshot_json']+=' ';pytest.raises(NeedsReview,unseal,bad)
    for mutate in [lambda s:s.update(model_ref={'id':'x'}),lambda s:s['scenes'][0].update(start=.01),lambda s:s['scenes'][0].update(source_kind='unknown'),lambda s:s['scenes'].append(s['scenes'][0].copy())]:
        value=copy.deepcopy(s);mutate(value);pytest.raises(NeedsReview,unseal,sealed(value))

def test_ae_only_never_accepts_generated_insert():
    s=snapshot();response=direction();assert validate_direction(response,s['scenes'][0],s,[])['ai'] is None
    response['ai']={'start':0,'duration':3,'prompt':'Keep exact identity; wind only.'}
    pytest.raises(NeedsReview,validate_direction,response,s['scenes'][0],s,[])

def test_hybrid_enforces_shared_clip_budget_and_actual_evidence():
    s=snapshot('hybrid');r=direction();r['ai']={'start':0,'duration':4,'prompt':'Original coat moves subtly; exact face.'}
    assert validate_direction(r,s['scenes'][0],s,[])['ai']['duration']==4
    pytest.raises(NeedsReview,validate_direction,r,s['scenes'][0],s,[{'ai':r['ai']}])
    r['ai']['duration']=5;pytest.raises(NeedsReview,validate_direction,r,s['scenes'][0],s,[])
    r['ai']=None;r['evidence']=[];pytest.raises(NeedsReview,validate_direction,r,s['scenes'][0],s,[])

def test_fast_cut_effects_need_visible_output_frames():
    s=snapshot();r=direction();r['scene']['effects']=[dict(type='impact_flash',start=.5,end=.501,intensity=.4,center=[.5,.5],radius=.3,color=[1,1,1])]
    pytest.raises(NeedsReview,validate_direction,r,s['scenes'][0],s,[])

def test_dashboard_counts_only_reviewed_automatic_outputs():
    from worker.local_media_dashboard import summarize
    item=summarize({'id':'job','metadata':{'kind':'motion_automation','state':'complete','total_scenes':2,
        'results':[{'review':{'passed':True}},{'review':{'passed':False}}]}})
    assert item['group']=='completed' and item['done']==1 and item['total']==2

def test_supervisor_dispatches_automation_without_a_manual_editor():
    from worker.local_media_supervisor import role_command
    command=role_command('motion_automation')
    assert command[-1]=='--once' and command[-2].endswith('motion_automation_worker.py')
