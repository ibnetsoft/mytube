import hashlib,json
from worker.wuxia_delivery_state import delivery_state

def test_preview_is_not_episode_delivery(tmp_path):
    (tmp_path/'motion-preview.html').write_text('preview')
    assert not delivery_state(tmp_path)['complete']

def evidence(root):
    p=root/'packaging';p.mkdir()
    saved={'id':42,'pregenerated_script':'확정 본문','pregenerated_structure':{'scenes':[{'scene_number':1}]}}
    receipt={'topic_id':42,'script_sha256':hashlib.sha256('확정 본문'.encode()).hexdigest(),
             'scene_count':1,'database_readback':'exact_match','web_readiness':{'ready':True},'thumbnail_completed':True}
    (p/'registered-topic-readback.json').write_text(json.dumps(saved))
    (p/'registration-receipt.json').write_text(json.dumps(receipt))
    return p,receipt

def test_registered_package_does_not_require_final_render(tmp_path):
    evidence(tmp_path)
    assert delivery_state(tmp_path)['complete']

def test_wrong_readback_cannot_claim_completion(tmp_path):
    p,r=evidence(tmp_path);r['script_sha256']='different'
    (p/'registration-receipt.json').write_text(json.dumps(r))
    assert not delivery_state(tmp_path)['complete']

def test_image_job_list_is_not_generated_art(tmp_path):
    from scripts.wuxia_episode_status import checkpoint
    (tmp_path/'script-final.json').write_text('{}')
    (tmp_path/'image-generation-jobs.json').write_text(json.dumps([{'asset_id':'E02_S01_STATE_01'}]))
    state=checkpoint(tmp_path)
    assert state['next_stage']=='art_and_direction' and state['saved_images']==0
