import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from listener_review import improve_for_listener, validate_report

OLD = [{'scene_order': 1, 'text': '그는 걸었네. 문을 열었지. 들어왔어.'},
       {'scene_order': 2, 'text': '어머니가 그의 젖은 옷을 받아 들었습니다.'}]
NEW = '문 앞에서 망설이던 그가 마침내 손잡이를 돌렸습니다.'
BUDGETS = [{'min_chars': 1, 'max_chars': 100}] * 2

def report(sections, bad=False):
    evidence = {'scene_order': 1, 'quote': sections[0]['text'], 'reason': '행동은 명확하지만 말투가 기계적으로 전환됩니다.' if bad else '주인공의 행동을 자연스럽게 따라갈 수 있습니다.'}
    return {'verdict': 'revise' if bad else 'pass', 'strengths': [evidence],
            'issues': [{**evidence, 'listener_impact': '문장마다 화자가 바뀐 듯 들립니다.', 'suggestion': '상황의 흐름에 맞게 문장을 연결하세요.'}] if bad else []}

def test_pass_no_rewrite_and_no_plan_leak():
    calls = []
    def stage(name, context, task):
        calls.append(name)
        assert set(context) == {'title', 'sections'}
        return report(context['sections'])
    result, audit = improve_for_listener(stage, '귀가', OLD, BUDGETS)
    assert result == OLD and audit['revision_rounds'] == 0
    assert len(calls) == 2

@pytest.mark.parametrize('bad_comparison', [False, True])
def test_local_revision_blind_comparison_and_recheck(bad_comparison):
    snapshot = copy.deepcopy(OLD)
    def stage(name, context, task):
        if name.startswith('02f_'):
            assert set(context) == {'title', 'sections'}
            return report(context['sections'], context['sections'][0]['text'] != NEW)
        if name == '02g_listener_repair':
            return {'patches': [{'scene_order': 1, 'text': NEW}]}
        assert set(context) == {'title', 'versions'}
        versions = context['versions']
        winner = next(k for k, v in versions.items() if v[0]['text'] == NEW)
        return {'naturalness': 'tie' if bad_comparison else winner, 'engagement': 'tie', 'regressions': [],
                'evidence': {k: {'scene_order': 1, 'quote': v[0]['text'], 'reason': '자연스러운 사건 흐름을 비교했습니다.'} for k, v in versions.items()}}
    if bad_comparison:
        with pytest.raises(ValueError, match='not demonstrably better'):
            improve_for_listener(stage, '귀가', OLD, BUDGETS)
    else:
        result, audit = improve_for_listener(stage, '귀가', OLD, BUDGETS)
        assert result[0]['text'] == NEW and result[1] == OLD[1]
        assert audit['revision_rounds'] == 1 and audit['after']['naturalness']['verdict'] == 'pass'
    assert OLD == snapshot

def test_fabricated_evidence_rejected():
    r = report(OLD)
    r['strengths'][0]['quote'] = '원문에 없는 인용'
    with pytest.raises(ValueError, match='exact script'):
        validate_report(r, OLD)

def test_unflagged_scene_cannot_be_rewritten():
    def stage(name, context, task):
        if name.startswith('02f_'): return report(OLD, True)
        return {'patches': [{'scene_order': 2, 'text': NEW}]}
    with pytest.raises(ValueError, match='unflagged'):
        improve_for_listener(stage, '귀가', OLD, BUDGETS)
