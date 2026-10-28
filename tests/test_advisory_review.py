import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from advisory_review import fixed_plan,note,enabled,POLICY

def test_failed_direction_uses_saved_source_without_mutating_original():
    scene={'number':1,'source_kind':'video','prepared_direction':{'source':'image','keys':[{'scale':1}],'effects':[],'transition':'cut'}}
    snapshot={}
    plan=fixed_plan(snapshot,scene,'Unexpected character in existing footage')
    assert plan['scene']['source']=='video' and plan['ai'] is None
    assert scene['prepared_direction']['source']=='image'
    assert snapshot['_quality_notes'][0]['scene_number']==1
    assert 'passed' not in plan

def test_quality_notes_preserve_failures_without_duplicates():
    snapshot={};scene={'number':8}
    note(snapshot,scene,'output_review','Face mismatch')
    note(snapshot,scene,'output_review','Face mismatch')
    note(snapshot,scene,'output_review','Wrong subtitle')
    assert len(snapshot['_quality_notes'])==2
    assert snapshot['_quality_notes'][0]['detail']=='Face mismatch'

def test_missing_execution_material_cannot_be_falsely_completed():
    with pytest.raises(ValueError):fixed_plan({}, {'number':1,'source_kind':'video'}, 'No plan')

def test_explicit_policy_is_recognized():
    assert enabled({'execution_policy':{'review_policy':POLICY}})
    assert not enabled({})
