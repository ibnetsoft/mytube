import copy
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker import codex_local_console as console
from worker.content_language import LANGUAGE_NAMES, language_directive
import codex_content_runner as runner
from senior_script_guard import CHECKS, PROFILE, text_issues

SAMPLES = {
    'ko': '할머니는 오래된 편지를 펼치고 그날의 약속을 떠올렸습니다.',
    'en': 'She opened the old letter and finally understood why her brother had left.',
    'ja': '祖母は古い手紙を開き、あの日に交わした約束を静かに思い出しました。',
    'es': 'Abrió la carta y comprendió por qué su hermano se había marchado sin despedirse.',
}


@pytest.mark.parametrize('language', LANGUAGE_NAMES)
def test_request_language_is_persisted(tmp_path, monkeypatch, language):
    jobs = console.Jobs(tmp_path)
    monkeypatch.setattr(console, 'jobs', jobs)
    monkeypatch.setattr(jobs.pool, 'submit', lambda *args: None)
    client = TestClient(console.app, base_url=console.ORIGIN, headers={'X-Codex-Local': console.TOKEN})
    response = client.post('/api/jobs', json={'mode': 'new', 'title': '제목', 'category': '가족 사연', 'language': language})
    assert response.status_code == 200
    identity = response.json()['id']
    import json
    assert json.loads((tmp_path / identity / 'request.json').read_text())['language'] == language
    assert response.json()['language'] == language
    assert client.post('/api/jobs', json={'mode': 'new', 'language': 'fr'}).status_code == 422
    assert console.StartRequest(mode='new').language == 'ko'
    jobs.pool.shutdown()


@pytest.mark.parametrize('language', LANGUAGE_NAMES)
def test_full_script_stages_use_selected_language(monkeypatch, language):
    seen = []
    def stage(self, identity, name, context, task):
        seen.append((name, context, task))
        if name == '01_plan':
            assert context['language'] == language
            assert f'OUTPUT LANGUAGE: {LANGUAGE_NAMES[language]}' in context['category_narration_voice']
            return {'scenes': [{}], 'story_core': {}, 'narrative_blueprint': {}}
        if name in ('02_script', '02b_script_qa'):
            assert context['language'] == language
            return {'sections': [{'scene_order': 1, 'text': SAMPLES[language]}]}
        if name == '02c_senior_review':
            assert context['language'] == language
            return {'script_quality_report': {'profile': PROFILE, 'verdict': 'pass', 'score': 90,
                'critical_issues': [], 'checks': {key: {'pass': True, 'evidence': 'Synthetic test evidence in scene one.'} for key in CHECKS}}}
        if name.startswith('02f_listener_'):
            assert language_directive(language) in task
            assert set(context) == {'title', 'sections'}
            return {'verdict': 'pass', 'issues': [], 'strengths': [{'scene_order': 1, 'quote': SAMPLES[language], 'reason': 'Test only'}]}
        if name == '02e_dialogue':
            assert context['language'] == language
            return {'scenes': [{'scene_number': 1, 'spans': []}]}
        raise AssertionError(name)
    monkeypatch.setattr(runner.CodexStagedContentRunner, '_stage', stage)
    monkeypatch.setattr(runner, '_resolve_script_style_directive', lambda _: '')
    result = runner.CodexStagedContentRunner().generate('test', {
        'topic': '한국어로 입력한 주제', 'language': language, 'category_id': '5',
        'target_duration_seconds': 5}, script_only=True)
    assert result['script'] == SAMPLES[language]
    assert result['language'] == language
    assert not text_issues([{'scene_order': 1, 'text': SAMPLES[language]}], {'language': language})
    if language != 'ko':
        assert text_issues([{'scene_order': 1, 'text': SAMPLES['ko']}], {'language': language})


def test_language_specific_budgets_and_category_override():
    budgets = {code: runner._scene_char_budgets([{'duration_seconds': 5}],
        {'target_duration_seconds': 5, 'language': code})[0] for code in LANGUAGE_NAMES}
    assert budgets['en']['target_chars'] > budgets['ko']['target_chars'] * 2
    assert budgets['es']['max_chars'] > budgets['ko']['max_chars']
    voice = runner._category_narration_voice({'category_id': '12', 'language': 'es'})
    assert 'OUTPUT LANGUAGE: Spanish (es)' in voice
    assert 'Write idiomatic spoken ENGLISH' not in voice
    assert '25 Korean characters' not in runner._script_rhythm_contract({'language': 'es', 'target_duration_seconds': 60})


@pytest.mark.parametrize('language', LANGUAGE_NAMES)
def test_local_workflow_passes_language(monkeypatch, tmp_path, language):
    from worker import codex_local_workflow as workflow, codex_bgm
    captured = {}
    def generate(self, identity, payload, **kwargs):
        captured.update(payload)
        return {'script': SAMPLES[language], 'structure': {'scenes': []}}
    monkeypatch.setattr(runner.CodexStagedContentRunner, 'generate', generate)
    monkeypatch.setattr(codex_bgm, 'plan_package_bgm', lambda *a, **k: None)
    monkeypatch.setattr(workflow, 'finalize_sfx', lambda r, i, p, n: p)
    result = workflow.produce('test', console.StartRequest(mode='new', title='제목', category='가족 사연', language=language).model_dump(),
                              None, tmp_path, lambda _: None)
    assert captured['language'] == language and result['language'] == language


@pytest.mark.parametrize('language', LANGUAGE_NAMES)
def test_grounded_writer_receives_language_without_changing_source(language):
    from worker.grounded_script import produce_grounded
    from types import SimpleNamespace
    captured = {}
    class StopAfterCapture(Exception):
        pass
    def stage(identity, name, context, task):
        captured.update(context=context, task=task)
        raise StopAfterCapture()
    source = {'id': 'a' * 32, 'kind': 'reference', 'title': '자료', 'locator': 'page 1',
              'translation': '', 'permission_notes': 'test', 'text': SAMPLES['ko']}
    request = console.StartRequest(mode='grounded', language=language, grounded_type='education').model_dump()
    with pytest.raises(StopAfterCapture):
        produce_grounded('test', request, [source], SimpleNamespace(_stage=stage), lambda _: None)
    assert captured['context']['language'] == language
    assert captured['context']['sources'][0]['text'] == source['text']
    assert language_directive(language) in captured['task']
    assert 'natural Korean source-grounded' not in captured['task']


def test_language_to_default_country_mapping():
    from worker.content_language import resolve_setting
    assert resolve_setting({'language': 'ko'})['setting_country'] == '한국'
    assert resolve_setting({'language': 'en'})['setting_country'] == '미국'
    assert resolve_setting({'language': 'ja'})['setting_country'] == '일본'
    assert resolve_setting({'language': 'es'})['setting_country'] == '스페인'
    assert resolve_setting({'language': 'ja'})['summary_label'] == '일본어 · 일본 현대 지방 소도시 · 실사'


def test_user_override_takes_precedence():
    from worker.content_language import resolve_setting
    # User selects English narration but sets background to South Korea (Korean history in English)
    s1 = resolve_setting({'language': 'en', 'setting_country': '한국', 'era_region': '조선 후기'})
    assert s1['setting_country'] == '한국'
    assert s1['setting_country_en'] == 'South Korea'
    assert s1['country_source'] == 'user_override'
    assert s1['summary_label'] == '영어 · 한국 조선 후기 · 실사'

    # User selects Spanish narration but sets background to Mexico
    s2 = resolve_setting({'language': 'es', 'setting_country': '멕시코'})
    assert s2['setting_country'] == '멕시코'
    assert s2['setting_country_en'] == 'Mexico'
    assert s2['country_source'] == 'user_override'


def test_visual_setting_prompt_and_no_korean_island():
    from worker.content_language import resolve_setting, visual_setting_prompt
    setting_ja = resolve_setting({'language': 'ja', 'setting_country': '일본', 'era_region': '현대 지방 소도시'})
    prompt_ja = visual_setting_prompt(setting_ja)
    assert 'Korean island setting' not in prompt_ja
    assert 'Japan' in prompt_ja
    assert 'modern regional small town' in prompt_ja or '현대 지방 소도시' in prompt_ja
    assert 'realistic visual continuity' in prompt_ja


def test_character_cache_invalidation_on_setting_change():
    from worker.codex_character_assets import digest, VERSION
    char = {'name': '하야시', 'role': '여관 주인'}
    # Japan setting
    f_ja = digest([VERSION, char, 'realistic', '일본', '현대 지방 소도시'])
    # Korea setting
    f_ko = digest([VERSION, char, 'realistic', '한국', '현대 지방 소도시'])
    # Era change
    f_ja_80s = digest([VERSION, char, 'realistic', '일본', '1980년대'])
    assert f_ja != f_ko
    assert f_ja != f_ja_80s
