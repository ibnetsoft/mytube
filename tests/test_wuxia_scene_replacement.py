import hashlib
from PIL import Image
import pytest
from worker.wuxia_art_quality import CHECKS
from worker.wuxia_scene_replacement import prepare_replacement


def test_replacement_requires_matching_file_review_and_current_source(tmp_path):
    path=tmp_path/'candidate.png'
    Image.new('RGB',(16,16),(32,64,96)).save(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    review={'source_sha256':sha,'coverage':{'all_people':True,'all_visible_hands':True},'people':[],'hands':[],
            'checks':{k:{'verdict':'not_visible','evidence':'No person visible','boxes':[]} for k in CHECKS}}
    old='a'*64
    result=prepare_replacement(path,review,current_sha=old,expected_current_sha=old,scene_id='S1',asset_id='image-1')
    assert result['source_sha256']==sha and result['source_bound_effects']=='review_required'
    with pytest.raises(ValueError): prepare_replacement(path,review,current_sha=old,expected_current_sha='b'*64,scene_id='S1',asset_id='image-1')
    review['checks']['head_neck']={'verdict':'uncertain','evidence':'Unclear','boxes':[[0,0,1,1]]}
    with pytest.raises(ValueError): prepare_replacement(path,review,current_sha=old,expected_current_sha=old,scene_id='S1',asset_id='image-1')
    Image.new('RGB',(16,16),(0,0,0)).save(path)
    with pytest.raises(ValueError): prepare_replacement(path,review,current_sha=old,expected_current_sha=old,scene_id='S1',asset_id='image-1')

def test_worker_review_requires_pass_and_unchanged_bytes(tmp_path, monkeypatch):
    import json
    import worker.wuxia_art_quality as anatomy
    from worker.wuxia_scene_replacement import review_local_candidate
    path=tmp_path/'candidate.png'
    Image.new('RGB',(16,16),(30,60,90)).save(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    raw={'source_sha256':sha,'coverage':{'all_people':True,'all_visible_hands':True},'people':[],'hands':[],
         'checks':{k:{'verdict':'not_visible','evidence':'No people in frame','boxes':[]} for k in CHECKS}}
    evidence=tmp_path/'review.json';evidence.write_text(json.dumps(raw),encoding='utf-8')
    def reviewer(state,scene,identity,download,check,runner):
        return {'asset_id':state['asset_id'],'source_sha256':state['sha256'],'decision':'passed','passed':True,'evidence_file':str(evidence)}
    monkeypatch.setattr(anatomy,'review_state',reviewer)
    result=review_local_candidate(path,scene={'scene_id':'S1'},current_sha='a'*64,expected_current_sha='a'*64,
                                  asset_id='asset-1',runner=object(),check=lambda:None)
    assert result['source_sha256']==sha and result['preserve_script_audio'] is True
    def failed(*args): return {'asset_id':'asset-1','source_sha256':sha,'decision':'uncertain','passed':False,'evidence_file':str(evidence)}
    monkeypatch.setattr(anatomy,'review_state',failed)
    with pytest.raises(ValueError):
        review_local_candidate(path,scene={'scene_id':'S1'},current_sha='a'*64,expected_current_sha='a'*64,
                               asset_id='asset-1',runner=object(),check=lambda:None)


def test_scene_patch_preserves_original_and_blocks_both_transitions(tmp_path):
    from worker.wuxia_scene_replacement import prepare_project_scene_patch, block_adjacent_transitions
    import copy
    old='a'*64; new='b'*64
    scene={'id':'row','scene_number':8,'metadata':{'scene_id':'S008','cut_id':'C008','source_image_sha256':old,
           'narration':'keep speech','cowork_image_asset':{'speaker_geometry':{'source_sha256':old}},'image_effect':'zoom'}}
    reviewed={'contract':'wuxia_scene_replacement/v1','scene_id':'S008','previous_source_sha256':old,'source_sha256':new,
              'anatomy_review':{'contract':'wuxia_anatomy_review/v1','source_sha256':new,'passed':True,'decision':'passed','scene_id':'S008','asset_id':'new-asset'},'asset_id':'new-asset'}
    asset={'sha256':new,'gcs_bucket':'b','gcs_path':'project/version.png','image_url':'https://example.test/image'}
    before=copy.deepcopy(scene)
    patch=prepare_project_scene_patch(scene,asset,reviewed)
    assert scene==before and patch['metadata']['narration']=='keep speech'
    assert 'cowork_image_asset' not in patch['metadata'] and patch['metadata']['image_effect']=='none'
    assert patch['metadata']['source_bound_review']['mouth_and_effects']=='review_required'
    plan={'transitions':[{'transition_id':'T7','from_cut_id':'C007','to_cut_id':'C008','blocked_cut_ids':[]},
                         {'transition_id':'T8','from_cut_id':'C008','to_cut_id':'C009','blocked_cut_ids':[]},
                         {'transition_id':'T9','from_cut_id':'C009','to_cut_id':'C010','blocked_cut_ids':[]}]}
    updated, affected=block_adjacent_transitions(plan,'C008')
    assert affected==['T7','T8'] and updated['blocked_transitions']==['T7','T8']
    assert plan['transitions'][0]['blocked_cut_ids']==[]
    reviewed['previous_source_sha256']='c'*64
    with pytest.raises(ValueError): prepare_project_scene_patch(scene,asset,reviewed)


def test_retirement_plan_preserves_original_videos_and_other_scenes():
    from worker.wuxia_scene_replacement import plan_dependent_asset_retirement
    def asset(key, scene, kind, **extra):
        return {'id':key,'project_id':'p','scene_number':scene,'status':'uploaded','updated_at':'v1',
                'metadata':{'kind':kind,**extra}}
    assets=[asset('mouth',8,'mouth_preview'),asset('geo',8,'ae_speaker_coordinates'),
            asset('recorded',8,'video',ae_mouth_fingerprint='old'),asset('source-video',8,'original'),
            asset('other-scene',9,'mouth_preview')]
    plan=plan_dependent_asset_retirement(assets,project_id='p',scene_number=8)
    assert [item['id'] for item in plan]==['mouth','geo','recorded']
    assert assets[0]['status']=='uploaded'


def test_continuity_reviewer_rejects_mismatch(tmp_path):
    from worker.wuxia_scene_replacement import review_scene_continuity
    first=tmp_path/'first.png';second=tmp_path/'second.png'
    Image.new('RGB',(16,16),'red').save(first);Image.new('RGB',(16,16),'blue').save(second)
    class Runner:
        def _stage(self, identity, name, context, task):
            assert context['_local_image_paths']==[str(first.resolve()),str(second.resolve())]
            return {'source_sha256':context['source_sha256'],'candidate_sha256':context['candidate_sha256'],
                    'verdict':'uncertain','evidence':['inconclusive'], 'issues':['cannot establish identity']}
    with pytest.raises(ValueError): review_scene_continuity(first,second,scene_id='S008',runner=Runner())
