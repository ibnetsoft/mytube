from copy import deepcopy
from worker.thumbnail_contract import thumbnail_draft, background_ready, can_sync_background

def test_copy_is_editable_and_not_competing_candidates():
    draft=thumbnail_draft(['first','alternative','third'])
    assert [l['text'] for l in draft['text_layers']]==['first']
    assert draft['thumbnail_url'] is None
    assert draft['render_status']=='awaiting_background'
    assert draft['coordinate_width']==480

def test_background_ready_is_not_a_final_thumbnail():
    source={'thumbnail_design':thumbnail_draft(['headline'],[{'text':'headline'},{'text':'subhead'}])}
    old=deepcopy(source)
    result=background_ready(source,'https://example.test/background.png')
    assert source==old
    assert result['thumbnail_completed'] is False
    assert result['thumbnail_url'] is None
    assert result['thumbnail_design']['editor_bg_url']==result['thumbnail_bg_url']
    assert len(result['thumbnail_design']['text_layers'])==2
    assert result['thumbnail_design']['render_status']=='awaiting_user_save'

def test_existing_user_design_and_script_are_protected():
    project={'status':'in_progress','project_payload':{'script':'new'},'progress_payload':{}}
    assert can_sync_background(project,'new')
    assert not can_sync_background(project,'old')
    for patch in ({'thumbnail_completed':True},{'thumbnail_design':{'saved_at':'saved'}},
                  {'thumbnail_design':{'text_layers':[{'text':'manual'}]}}):
        p=deepcopy(project); p['project_payload'].update(patch)
        assert not can_sync_background(p,'new')
    project['status']='submitted'
    assert not can_sync_background(project,'new')
