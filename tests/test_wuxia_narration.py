import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from worker.wuxia_narration import applies, produce_sections, spoken_text, validate_draft, validate_review


def sections():
    return [dict(scene_order=1, visual_action='서진이 손으로 바닥을 짚는다. 상처 난 옆구리를 누른다.',
                 spoken_blocks=[dict(id='n1', kind='narration', text='손으로 바닥을 짚었습니다.'),
                                dict(id='d1', kind='dialogue', speaker='도겸', text='“일어나지 마.”')],
                 text='손으로 바닥을 짚었습니다.\n“일어나지 마.”'),
            dict(scene_order=2, visual_action='닫힌 중개소 문과 장부 표지. 죽음의 기록은 아직 보이지 않는다.',
                 spoken_blocks=[dict(id='n2', kind='narration', text='장부에는 이미 죽은 사람이 되어 있었습니다.')],
                 text='장부에는 이미 죽은 사람이 되어 있었습니다.')]


BUDGETS = [dict(min_chars=100, max_chars=200)] * 2


def report(rows, remove=True):
    decisions = []
    for s in rows:
        for b in s['spoken_blocks']:
            if b['kind'] != 'narration': continue
            d = dict(scene_order=s['scene_order'], block_id=b['id'], quote=b['text'], reason='같은 컷에 보이는 행동' if b['id']=='n1' else '화면에 없는 장부 기록')
            if remove and b['id'] == 'n1':
                d.update(decision='remove_visible_repeat', visual_evidence='서진이 손으로 바닥을 짚는다.')
            else:
                d.update(decision='keep', adds='new_fact')
            decisions.append(d)
    return dict(mode='planned_visuals_and_speech',
                checks={k:dict(passed=True, reason='장부 기록과 부상 및 소품 연속성을 시각 정보와 발화로 검토',
                               evidence=dict(scene_order=1, channel='visual_action',quote=rows[0]['visual_action']))
                        for k in ('continuity','story_clarity','no_padding')}, narration_decisions=decisions)


@pytest.mark.parametrize('payload', [{'category_id':18},{'category':'무협 웹툰'}, {'image_style':'wuxia_webtoon'}, {'content_setting':{'image_style':'wuxia_webtoon'}}])
def test_explicit_wuxia_webtoon_scope(payload):
    assert applies(payload)


@pytest.mark.parametrize('payload', [{'category_id':7}, {'category':'옛날이야기'}, {'topic':'무협 같은 경제 이야기'}, {}])
def test_other_categories_are_unchanged(payload):
    assert not applies(payload)


def test_grounded_removal_preserves_dialogue_visuals_and_new_information():
    original=sections(); calls=[]
    def stage(name, context, task):
        calls.append(name)
        if name == '02w_wuxia_script':return {'sections':copy.deepcopy(original)}
        return report(context['sections'])
    result,audit=produce_sections(stage,{'topic':'탈출'},[{'duration_seconds':20}]*2,BUDGETS)
    assert result[0]['text']=='“일어나지 마.”'
    assert result[0]['spoken_blocks']==original[0]['spoken_blocks'][1:]
    assert original[0]['visual_action'] in result[0]['visual_action']
    assert original[0]['spoken_blocks'][0]['text'] in result[0]['visual_action']
    assert result[1]==original[1]
    assert len(audit['removed'])==1 and len(audit['rounds'])==2
    assert audit['actual_artwork_reviewed'] is False
    assert original==sections() # no in-place mutation
    assert '02w_wuxia_visual_review_2' in calls


def test_silent_cut_survives_and_never_leaks_action_into_spoken_text():
    rows=sections(); rows[0]['spoken_blocks']=rows[0]['spoken_blocks'][:1];rows[0]['text']=spoken_text(rows[0])
    def stage(name,context,task):
        return {'sections':rows} if name=='02w_wuxia_script' else report(context['sections'])
    result,_=produce_sections(stage,{},[{'duration_seconds':20}]*2,BUDGETS)
    assert result[0]['text']=='' and result[0]['spoken_blocks']==[]
    assert result[0]['visual_action']
    validate_draft({'sections':result},BUDGETS)


@pytest.mark.parametrize('corruption', ['missing','fabricated_quote','fabricated_visual','delete_dialogue','no_added_information','fabricated_check'])
def test_review_requires_every_sentence_and_same_cut_grounding(corruption):
    rows=sections(); r=report(rows)
    if corruption=='missing':r['narration_decisions'].pop()
    elif corruption=='fabricated_quote':r['narration_decisions'][0]['quote']='존재하지 않는 문장'
    elif corruption=='fabricated_visual':r['narration_decisions'][0]['visual_evidence']='달리는 말'
    elif corruption=='delete_dialogue':r['narration_decisions'][0]['block_id']='d1'
    elif corruption=='no_added_information':r['narration_decisions'][1]['adds']='visible_action'
    else:r['checks']['continuity']['evidence']['quote']='존재하지 않는 이미지'
    with pytest.raises(ValueError):validate_review(r,rows)


def test_failed_audiovisual_review_cannot_become_pass():
    def stage(name,context,task):
        if name=='02w_wuxia_script':return {'sections':sections()}
        r=report(context['sections'],False);r['checks']['continuity']['passed']=False;return r
    with pytest.raises(ValueError,match='rejected continuity'):
        produce_sections(stage,{},[{}]*2,BUDGETS)


@pytest.mark.parametrize('change', ['leaked_action','reordered','missing_visual','duplicate_block','unnamed_speaker'])
def test_split_contract_is_enforced(change):
    rows=sections()
    if change=='leaked_action':rows[0]['text']+='\n'+rows[0]['visual_action']
    elif change=='reordered':rows.reverse()
    elif change=='missing_visual':rows[0]['visual_action']=''
    elif change=='duplicate_block':rows[0]['spoken_blocks'][1]['id']='n1'
    else:rows[0]['spoken_blocks'][1]['speaker']=''
    with pytest.raises(ValueError):validate_draft({'sections':rows},BUDGETS)


def test_runner_budgets_allow_silence_only_for_webtoon():
    from worker.codex_content_runner import _scene_char_budgets
    scenes=[{'duration_seconds':20}]
    assert _scene_char_budgets(scenes,{'target_duration_seconds':20,'category_id':18})[0]['min_chars']==0
    assert _scene_char_budgets(scenes,{'target_duration_seconds':20,'category_id':1})[0]['min_chars']>0


def test_active_runner_bypasses_audio_only_rewrites_and_keeps_both_channels(monkeypatch):
    import worker.codex_content_runner as runner
    monkeypatch.setattr(runner,'_pacing_schedule',lambda _: [{'duration_seconds':20}]*2)
    calls=[]
    class ReachedSpeechBoundary(Exception):pass
    def stage(self, job, name, context, task):
        calls.append(name)
        if name=='01_plan':
            assert 'wuxia_narration_contract' in context
            return {'scenes':[{'scene_summary':'탈출'},{'scene_summary':'장부'}]}
        if name=='02w_wuxia_script':
            rows=sections();rows[0]['spoken_blocks']=rows[0]['spoken_blocks'][:1];rows[0]['text']=spoken_text(rows[0])
            return {'sections':rows}
        if name.startswith('02w_wuxia_visual_review_'):return report(context['sections'])
        if name=='02e_dialogue':
            first,second=context['scenes']
            assert first['scene_text']==first['narration']==first['narration_text']==''
            assert first['silent_visual'] is True and first['spoken_blocks']==[]
            assert '바닥' in first['visual_action'] and first['duration_seconds']==20
            assert context['script']==second['scene_text']
            assert '바닥' not in context['script']
            raise ReachedSpeechBoundary
        raise AssertionError('Unexpected legacy audio-only stage '+name)
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',stage)
    with pytest.raises(ReachedSpeechBoundary):
        runner.CodexStagedContentRunner().generate('wuxia-test',{'topic':'탈출','category_id':18,'target_duration_seconds':40,'required_video_scene_count':0})
    assert '02w_wuxia_visual_review_2' in calls
    assert '02b_script_qa' not in calls


def test_chapter_validation_accepts_reviewed_silent_visual_but_not_missing_scenes():
    from worker.story_chapters import validate_package
    scenes=[{'scene_text':'', 'spoken_blocks':[], 'visual_action':'피 묻은 손바닥을 비춘다.',
             'speech_contract':'wuxia_visual_narration/v1','duration_seconds':5},
            {'scene_text':'“일어나지 마.”','duration_seconds':5}]
    p={'script':'“일어나지 마.”','structure':{'wuxia_narration_profile':'wuxia_visual_narration/v1','scenes':scenes}}
    assert validate_package(p,10)==p
    broken=copy.deepcopy(p);broken['structure']['scenes'][0]['visual_action']=''
    with pytest.raises(ValueError):validate_package(broken,10)
    broken=copy.deepcopy(p);broken['structure'].pop('wuxia_narration_profile')
    with pytest.raises(ValueError):validate_package(broken,10)


def test_visual_instructions_participate_in_image_integrity_without_changing_legacy_keys():
    from worker.cowork_scene_assets import _template_source_snapshot
    scene={'scene_number':1,'narration':'기존 문장','image_prompt':'unchanged'}
    legacy=_template_source_snapshot(scene,1)
    assert 'visual_action' not in legacy and 'spoken_blocks' not in legacy
    split={**scene,'visual_action':'서진이 바닥을 짚는다.','spoken_blocks':[]}
    current=_template_source_snapshot(split,1)
    assert current['visual_action']==split['visual_action']
    changed={**split,'visual_action':'서진이 부상 부위를 누른다.'}
    assert current!=_template_source_snapshot(changed,1)
    assert {k:v for k,v in current.items() if k not in ('visual_action','spoken_blocks')}==legacy
