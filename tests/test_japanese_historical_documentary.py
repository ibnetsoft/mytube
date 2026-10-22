from worker.japanese_historical_documentary import PROFILE, prepare_request, enforce_package
import copy
import pytest
from worker.japanese_historical_documentary import (
    validate_sources, validate_evidence_review, prepare_sources, finalize_evidence,
)


def test_documentary_settings_and_existing_story_isolation():
    old = {'script_style': 'story', 'language': 'ko', 'duration_minutes': 15}
    assert prepare_request(old) is old
    configured = prepare_request({**old, 'script_style': PROFILE['key']})
    assert configured['language'] == 'ja'
    assert configured['duration_minutes'] == 30
    assert configured['image_style'] == 'sumi_e_ukiyo_e'
    assert '현대' not in configured['era_region']


def test_visual_contract_covers_nested_assets_and_is_idempotent():
    package = {'structure': {'scenes': [{'image_prompt': 'A historical room'}]},
               'image_grid_prompts': [{'shared_style': 'ink', 'panels': [{'panel_prompt': 'An elderly man'}]}],
               'thumbnail_image_prompt': 'An old samurai'}
    result = enforce_package(package, {'script_style': PROFILE['key']})
    enforce_package(result, {'script_style': PROFILE['key']})
    prompts = [result['structure']['scenes'][0]['image_prompt'], result['image_grid_prompts'][0]['shared_style'], result['image_grid_prompts'][0]['panels'][0]['panel_prompt'], result['thumbnail_image_prompt']]
    assert all(prompt.count(PROFILE['prompt']) == 1 for prompt in prompts)
    assert result['script_style'] == PROFILE['key']


def test_documentary_contract_wins_over_japanese_folktale_category():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
    import codex_content_runner as runner
    payload = {'category_id': 13, 'category': '日本昔話', 'script_style': PROFILE['key']}
    assert runner._category_narration_voice(payload) == PROFILE['narration_directive']
    assert runner._story_spine_contract(payload) == PROFILE['narration_directive']
    assert runner._resolve_script_style_directive(PROFILE['key']) == PROFILE['narration_directive']
    assert runner._category_narration_voice({'category_id': 13, 'script_style': 'story'}) != PROFILE['narration_directive']


def evidence_fixture():
    sources = validate_sources([
        {'id': 'a', 'title': 'Archive', 'url': 'https://archive.example/a', 'publisher': 'Archive',
         'source_type': 'primary', 'text': '記録された出来事。' * 15},
        {'id': 'b', 'title': 'Museum', 'url': 'https://museum.example/b', 'publisher': 'Museum',
         'source_type': 'institutional', 'text': '晩年の記録と史料。' * 15},
    ])
    sections = [{'scene_order': 1, 'text': '記録によれば、出来事がありました。'},
                {'scene_order': 2, 'text': '晩年の記録が残っています。'}]
    report = {'verdict': 'pass', 'issues': [], 'scene_evidence': [
        {'scene_order': 1, 'kind': 'documented', 'citations': [
            {'source_id': 'a', 'source_quote': '記録された出来事。', 'script_quote': sections[0]['text']}]},
        {'scene_order': 2, 'kind': 'documented', 'citations': [
            {'source_id': 'b', 'source_quote': '晩年の記録と史料。', 'script_quote': sections[1]['text']}]},
    ], 'checks': {key: {'pass': True, 'evidence': 'Specific comparison of the supplied records.'} for key in (
        'source_reliability', 'all_factual_claims_supported', 'chronology_relationships',
        'uncertainty_in_spoken_text', 'no_invented_quotes_or_private_scenes', 'no_unsupported_period_claims')}}
    return sources, sections, report


def test_missing_and_duplicate_sources_fail_before_writing():
    sources, _, _ = evidence_fixture()
    for bad in ([], sources[:1], [sources[0], sources[0]], [{**sources[0], 'text': 'snippet'}, sources[1]]):
        with pytest.raises(ValueError):
            validate_sources(bad)
    class Runner:
        def _stage(self, job, name, context, task):
            assert name == '00_documentary_research'
            return {'historical_sources': [], 'missing_evidence': ['Cannot read the archive']}
    with pytest.raises(ValueError, match='조사 미완료'):
        prepare_sources(Runner(), 'test', {'script_style': PROFILE['key']})


@pytest.mark.parametrize('tamper', ['quote', 'script', 'coverage', 'verdict', 'check', 'single_source'])
def test_evidence_gate_rejects_unsupported_or_stale_claims(tamper):
    sources, sections, report = evidence_fixture()
    if tamper == 'quote':
        report['scene_evidence'][0]['citations'][0]['source_quote'] = 'Invented quotation'
    elif tamper == 'script':
        sections[0]['text'] = 'Entirely rewritten narration'
    elif tamper == 'coverage':
        report['scene_evidence'].pop()
    elif tamper == 'verdict':
        report['verdict'] = 'revise'
    elif tamper == 'check':
        del report['checks']['source_reliability']
    else:
        report['scene_evidence'][1]['citations'][0].update(source_id='a', source_quote='記録された出来事。')
    with pytest.raises(ValueError):
        validate_evidence_review(report, sections, sources)


def test_repair_rechecks_changed_script_or_source_and_preserves_unchanged_review():
    sources, sections, report = evidence_fixture()
    class Runner:
        calls = 0
        def _stage(self, job, name, context, task):
            self.calls += 1
            result = copy.deepcopy(report)
            for row, section in zip(result['scene_evidence'], context['sections']):
                row['citations'][0]['script_quote'] = section['text']
            return result
    runner = Runner()
    payload = {'script_style': PROFILE['key']}
    package = {'structure': {'scenes': [{'scene_text': s['text']} for s in sections], 'historical_sources': sources}}
    finalize_evidence(runner, 'repair', package, payload)
    assert runner.calls == 1
    finalize_evidence(runner, 'repair', package, payload)
    assert runner.calls == 1
    package['structure']['scenes'][0]['scene_text'] += ' 記録をたどります。'
    finalize_evidence(runner, 'repair', package, payload)
    assert runner.calls == 2
    package['structure']['historical_sources'][0]['text'] += '追加の記録。'
    finalize_evidence(runner, 'repair', package, payload)
    assert runner.calls == 3


def test_visual_style_also_covers_video_and_bibliography_is_idempotent():
    sources, _, _ = evidence_fixture()
    package = {'structure': {'historical_sources': sources, 'scenes': [{'video_prompt': 'Restrained ink landscape'}]},
               'publish_metadata': {'description': '人物の記録をたどります。'}}
    for _ in range(2):
        enforce_package(package, {'script_style': PROFILE['key']})
    assert package['structure']['scenes'][0]['video_prompt'].count(PROFILE['prompt']) == 1
    for source in sources:
        assert package['publish_metadata']['description'].count(source['url']) == 1
    assert package['structure']['script_style'] == PROFILE['key']
