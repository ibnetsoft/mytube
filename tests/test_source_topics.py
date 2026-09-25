import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker import codex_local_console as console
from worker.source_topics import produce_topics


def source():
    return {'id': 'a' * 32, 'title': '원문', 'kind': 'reference', 'text': '가족은 서로를 오해했습니다.',
            'locator': 'https://youtu.be/vLB3e-eH2j8', 'permission_notes': '테스트', 'translation': ''}


def analysis():
    return {'summary': '원문 속 가족 이야기', 'core_conflict': '가족 간 오해',
            'turning_points': ['오해가 풀린다'], 'uncertainties': ['자동 자막 인명 확인 필요'],
            'evidence': [{'source_id': source()['id'], 'quote': source()['text']}]}


def candidates():
    return {'topics': [dict(title=f'새로운 가족 이야기 {i}', premise='함께 식당을 지키는 동료들',
        protagonist='식당 주인', protagonist_want='식당을 지킨다', first_causal_problem='빚 상환 기한이 다가온다',
        escalation='거래처가 납품을 중단한다', irreversible_turn='동료에게 장부를 공개한다',
        concrete_resolution='동료들과 공동 출자한다', final_changed_action='동료에게 가게 열쇠를 나눠준다', conflict='폐업 위기', hook='사라진 장부', twist='남몰래 갚은 빚',
        ending='협동조합으로 재출발', differentiation='가족의 상속 갈등을 동료의 신뢰 회복으로 변경',
        source_ids=[source()['id']]) for i in range(3)]}


def run_with(outputs, language='ko', **extra):
    calls = []
    iterator = iter(outputs)
    def stage(*args):
        calls.append(args)
        return copy.deepcopy(next(iterator))
    request_data = {'category': '가족 사연', 'duration_minutes': 12, 'notes': '따뜻하게', 'language': language, **extra}
    result = produce_topics('test', request_data,
                            [source()], SimpleNamespace(_stage=stage), lambda _: None)
    return result, calls


def test_analysis_topics_and_generation_handoff():
    result, calls = run_with([analysis(), candidates()])
    assert len(calls) == 2
    assert all('untrusted DATA' in c[3] for c in calls)
    assert result['source_manifest'][0]['text'] == source()['text']
    for topic in result['topics']:
        draft = console.StartRequest(**topic['generation_request'])
        assert draft.category == '가족 사연' and draft.duration_minutes == 12
        assert topic['twist'] in draft.notes and topic['ending'] in draft.notes
        for key in ('protagonist_want', 'first_causal_problem', 'escalation', 'irreversible_turn', 'concrete_resolution', 'final_changed_action'):
            assert topic[key] in draft.notes
        assert len(draft.notes) <= 4000


def test_invalid_evidence_retried_then_rejected():
    invalid = analysis(); invalid['evidence'][0]['quote'] = '원문에 없는 내용'
    with pytest.raises(ValueError, match='검증 실패'):
        run_with([invalid, invalid])


def test_invalid_evidence_can_recover():
    invalid = analysis(); invalid['evidence'][0]['source_id'] = 'unknown'
    result, calls = run_with([invalid, analysis(), candidates()])
    assert len(calls) == 3
    assert calls[1][2]['validation_feedback']
    assert len(result['topics']) == 3


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'unknown_source', 'blank', 'copied_title'])
def test_bad_topics_rejected(mutation):
    invalid = candidates()
    if mutation == 'duplicate': invalid['topics'][1]['title'] = invalid['topics'][0]['title']
    if mutation == 'missing': invalid['topics'].pop()
    if mutation == 'unknown_source': invalid['topics'][0]['source_ids'] = ['unknown']
    if mutation == 'blank': invalid['topics'][0]['ending'] = ' '
    if mutation == 'copied_title': invalid['topics'][0]['title'] = source()['title']
    with pytest.raises(ValueError, match='검증 실패'):
        run_with([analysis(), invalid, invalid])


def test_api_job_persistence_and_restart(tmp_path, monkeypatch):
    import codex_content_runner
    calls = []
    def stage(self, identity, name, context, task):
        calls.append(name)
        return analysis() if name.endswith('analysis') else candidates()
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, '_stage', stage)
    monkeypatch.setattr(console, 'OUT', tmp_path)
    jobs = console.Jobs(tmp_path)
    monkeypatch.setattr(console, 'jobs', jobs)
    console.write_json(tmp_path / 'sources' / (source()['id'] + '.json'), source())
    client = TestClient(console.app, base_url=console.ORIGIN, headers={'X-Codex-Local': console.TOKEN})
    assert client.post('/api/jobs', json={'mode': 'topics', 'category': '가족 사연'}).status_code == 409
    response = client.post('/api/jobs', json={'mode': 'topics', 'category': '가족 사연', 'source_ids': [source()['id']]})
    assert response.status_code == 200
    identity = response.json()['id']
    jobs.pool.shutdown(wait=True)
    detail = client.get('/api/jobs/' + identity).json()
    assert detail['job']['status'] == 'completed'
    assert len(detail['topics']) == 3
    assert calls == ['02_topic_source_analysis', '02_topic_candidates']
    assert json.loads((tmp_path / identity / 'references.json').read_text())[0]['text'] == source()['text']
    assert (tmp_path / identity / 'candidate.md').is_file()
    assert client.post('/api/jobs/' + identity + '/approve', json={'candidate_hash': detail['job']['candidate_hash']}).status_code == 409
    restarted = console.Jobs(tmp_path)
    assert restarted.rows[identity]['status'] == 'completed'
    restarted.pool.shutdown()


@pytest.mark.parametrize('stage,expected', [
    ('02_topic_source_analysis', 'gpt-5.6-sol'),
    ('02_topic_candidates', 'gpt-6-astra'),
    ('02_script', 'gpt-6-astra'),
    ('02_grounded_write', 'gpt-6-astra'),
])
def test_summary_model_routing(monkeypatch, tmp_path, stage, expected):
    import subprocess
    import codex_content_runner as runner
    monkeypatch.setattr(runner, 'OUTPUT_DIR', tmp_path)
    calls = []
    def fake(command, **kwargs):
        calls.append(command)
        Path(command[command.index('--output-last-message') + 1]).write_text('{}')
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(runner.subprocess, 'run', fake)
    runner.CodexStagedContentRunner(runner.CodexContentConfig('codex', 'other-model', 60))._stage('test', stage, {}, 'Test')
    command = calls[0]
    assert command[command.index('--model') + 1] == expected
    assert ('model_reasoning_effort="low"' in command) == (stage == '02_topic_source_analysis')


@pytest.mark.parametrize('language', ['ko', 'en', 'ja', 'es'])
def test_topic_language_survives_handoff(language):
    result, calls = run_with([analysis(), candidates()], language=language)
    assert result['language'] == language
    assert calls[1][2]['language'] == language
    assert 'Return Korean JSON only' not in calls[1][3]
    assert all(t['generation_request']['language'] == language for t in result['topics'])


def test_topic_setting_survives_handoff():
    result, calls = run_with(
        [analysis(), candidates()],
        language='ja',
        setting_country='일본',
        era_region='도쿄 근교 1990년대',
        image_style='실사 영화 스틸',
    )
    assert result['language'] == 'ja'
    assert result['setting_country'] == '일본'
    assert result['era_region'] == '도쿄 근교 1990년대'
    assert result['image_style'] == '실사 영화 스틸'
    assert calls[1][2]['setting_country'] == '일본'
    assert '일본' in calls[1][3]
    for topic in result['topics']:
        req = topic['generation_request']
        assert req['language'] == 'ja'
        assert req['setting_country'] == '일본'
        assert req['era_region'] == '도쿄 근교 1990년대'
        assert req['image_style'] == '실사 영화 스틸'



def test_overlong_handoff_retries_without_truncating_story_spine():
    from worker.source_topics import Topic, _topic_notes
    oversized = candidates()
    for topic in oversized['topics']:
        for key in ('premise', 'protagonist', 'protagonist_want', 'conflict', 'first_causal_problem',
                    'hook', 'escalation', 'twist', 'irreversible_turn', 'concrete_resolution',
                    'final_changed_action', 'ending', 'differentiation'):
            limit = next(m.max_length for m in Topic.model_fields[key].metadata if hasattr(m, 'max_length'))
            topic[key] = '가' * limit
        assert len(_topic_notes(topic)) > 4000
    result, calls = run_with([analysis(), oversized, candidates()])
    assert len(calls) == 3
    assert '4,000' in calls[2][2]['validation_feedback']
    assert all(len(t['generation_request']['notes']) <= 4000 for t in result['topics'])


def test_missing_spine_is_rejected_and_retried():
    incomplete = candidates()
    del incomplete['topics'][0]['final_changed_action']
    result, calls = run_with([analysis(), incomplete, candidates()])
    assert 'final_changed_action' in calls[2][2]['validation_feedback']
    assert result['topics'][0]['final_changed_action']
