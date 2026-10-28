import copy
import json
import pytest

from worker.story_chapters import (CHECKS, applies, produce_story, progress, validate_outline,
                                  validate_package, validate_review)
from worker.sermon_chapters import chapter_minutes, fingerprint


REQUEST = {'mode': 'new', 'language': 'ja', 'script_style': 'story', 'production_mode': 'standard',
           'title': '一つの長い物語', 'duration_minutes': 180, 'chapter_minutes': 15, 'notes': '江戸の人情噺',
           'required_video_scene_count': 2}


def outline(minutes):
    return {'logline': '一人の女が失われた約束を守る', 'ending': '約束を果たす', 'era_region': '江戸',
            'characters': [{'name': 'お鈴', 'role': 'protagonist', 'visual_dna_en': 'Japanese woman, age 30',
                'hair_design_en': 'black hair bun', 'wardrobe_en': 'indigo kimono', 'continuity_instruction': 'same face'}],
            'threads': [{'id': 'letter', 'description': '封じた手紙', 'setup_chapter': 1, 'payoff_chapter': len(minutes)}],
            'chapters': [{'chapter_number': i, 'title': f'第{i}章', 'objective': '前の選択の結果',
                'time_anchor': f'第{i}日', 'transition': '次の因果へ', 'beats': ['新しい選択']} for i in range(1, len(minutes) + 1)]}


class Runner:
    def __init__(self):
        self.calls = []

    def _stage(self, identity, stage, context, task):
        self.calls.append(stage)
        if stage == '02_story_outline':
            return outline(context['chapter_minutes'])
        final = stage == '02_story_final_review'
        quote = context['chapters'][0]['opening'] if final else context['script'][:10]
        number = 0 if final else context['current_chapter']['chapter_number']
        return {'verdict': 'pass', 'issues': [], 'summary': f'検証済み{number}章',
                'continuation_state': {'characters': ['お鈴'], 'open_threads': ['letter'] if not final and number < len(context['story_bible']['chapters']) else [],
                    'timeline': f'第{number}日', 'established_facts': ['約束は一つ']},
                'checks': {key: {'pass': True, 'evidence': 'exact supplied prose matches the story bible',
                    'script_quote': quote, 'chapter_number': number} for key in CHECKS}}


def producer(calls, fail_at=None):
    def run(identity, request):
        number = request['_story_context']['current_chapter']['chapter_number']
        calls.append((number, copy.deepcopy(request)))
        if number == fail_at:
            raise RuntimeError('simulated worker interruption')
        texts = [f'お鈴は第{number}日の朝、手紙を握りしめた。', f'第{number}日の夜、次の道を選んだ。']
        scenes = [{'scene_number': i, 'scene_order': i, 'duration_seconds': request['duration_minutes'] * 30,
                   'scene_text': text, 'narration': text} for i, text in enumerate(texts, 1)]
        return {'script': '\n\n'.join(texts), 'language': 'ja', 'structure': {'scenes': scenes,
                    'scene_cast': [{'scene_number': i, 'characters': ['お鈴']} for i in (1, 2)],
                    'scene_direction_plans': [{'scene_number': i} for i in (1, 2)],
                    'audio_performance': {'version': 1, 'scenes': [{'scene_number': i, 'source_text': text, 'cues': []} for i, text in enumerate(texts, 1)]}},
                'sfx_plan': {'status': 'ready', 'assets': []}, 'sfx_cues': [],
                'script_quality_report': {'verdict': 'pass'}}
    return run


def test_180_minute_continuous_story_resume_and_global_numbering(tmp_path):
    first, runner = [], Runner()
    with pytest.raises(RuntimeError, match='interruption'):
        produce_story('job', REQUEST, runner, lambda _: None, tmp_path, producer(first, fail_at=3))
    assert progress(tmp_path)['completed_chapters'] == 2
    original = (tmp_path / 'story/chapter-001.json').read_bytes()
    resumed = []
    result = produce_story('job', REQUEST, runner, lambda _: None, tmp_path, producer(resumed))
    assert [number for number, _ in resumed] == list(range(3, 13))
    assert (tmp_path / 'story/chapter-001.json').read_bytes() == original
    assert sum(s['duration_seconds'] for s in result['structure']['scenes']) == 10800
    assert [s['scene_number'] for s in result['structure']['scenes']] == list(range(1, 25))
    assert [r['scene_number'] for r in result['structure']['scene_direction_plans']] == list(range(1, 25))
    assert [r['scene_number'] for r in result['structure']['audio_performance']['scenes']] == list(range(1, 25))
    assert result['structure']['character_anchors']['main_character']['scene_numbers'] == list(range(1, 25))
    assert result['story_plan']['chapters'][-1]['scene_end'] == 24
    assert result['story_plan']['chapters'][-1]['start_seconds'] == 9900
    assert result['script'].count('手紙を握りしめた') == 12
    assert all(req['required_video_scene_count'] == 0 for _, req in resumed)
    assert resumed[0][1]['_story_context']['previous_chapters'][-1]['continuation_state']['open_threads'] == ['letter']
    assert resumed[0][1]['_scene_boundary_mode'] == 'paragraph_min18_v1'
    assert resumed[0][1]['_story_elapsed_seconds'] == 1800
    assert progress(tmp_path)['status'] == 'reviewed'
    runner_calls = len(runner.calls)
    produce_story('job', REQUEST, runner, lambda _: None, tmp_path, lambda *_: pytest.fail('reused completed chapter regenerated'))
    assert len(runner.calls) == runner_calls


def test_changed_request_cannot_reuse_chapters(tmp_path):
    produce_story('job', REQUEST, Runner(), lambda _: None, tmp_path, producer([]))
    with pytest.raises(ValueError, match='변경'):
        produce_story('job', {**REQUEST, 'notes': 'changed'}, Runner(), lambda _: None, tmp_path, producer([]))


def test_legacy_checkpoint_keeps_its_pacing_when_resumed(tmp_path):
    with pytest.raises(RuntimeError, match='interruption'):
        produce_story('legacy', REQUEST, Runner(), lambda _: None, tmp_path, producer([], fail_at=2))
    manifest = tmp_path / 'story/manifest.json'
    state = json.loads(manifest.read_text(encoding='utf-8'))
    state.pop('scene_boundary_mode')  # Format saved before paragraph-based scenes.
    manifest.write_text(json.dumps(state), encoding='utf-8')
    original = (tmp_path / 'story/chapter-001.json').read_bytes()
    resumed = []
    produce_story('legacy', REQUEST, Runner(), lambda _: None, tmp_path, producer(resumed))
    assert all('_scene_boundary_mode' not in request for _, request in resumed)
    assert (tmp_path / 'story/chapter-001.json').read_bytes() == original


def test_failed_audit_does_not_become_completed_checkpoint(tmp_path):
    class BadReview(Runner):
        def _stage(self, identity, stage, context, task):
            response = super()._stage(identity, stage, context, task)
            if stage.startswith('02_story_review'):
                response['checks']['timeline']['script_quote'] = 'not in the actual script'
            return response
    with pytest.raises(ValueError, match='인용'):
        produce_story('job', REQUEST, BadReview(), lambda _: None, tmp_path, producer([]))
    assert not (tmp_path / 'story/chapter-001.json').exists()
    assert progress(tmp_path)['completed_chapters'] == 0
    calls = []
    produce_story('job', REQUEST, Runner(), lambda _: None, tmp_path, producer(calls))
    assert calls[0][0] == 2  # Valid saved first-chapter draft is audited again, not rewritten.


def test_long_mode_and_story_contract_validation():
    assert applies(REQUEST)
    assert not applies({**REQUEST, 'language': 'ko'})
    assert not applies({**REQUEST, 'duration_minutes': 181})
    assert not applies({**REQUEST, 'script_style': 'japanese_historical_documentary'})
    assert sum(chapter_minutes(180, 20)) == 180
    invalid = outline([15] * 12); invalid['threads'][0]['payoff_chapter'] = 13
    with pytest.raises(ValueError): validate_outline(invalid, [15] * 12)
    invalid = outline([15] * 12); invalid['characters'].append(copy.deepcopy(invalid['characters'][0]))
    with pytest.raises(ValueError): validate_outline(invalid, [15] * 12)


def test_bad_scene_duration_and_text_are_rejected():
    request = {**REQUEST, 'duration_minutes': 15, '_story_context': {'current_chapter': {'chapter_number': 1}}}
    package = producer([])('chapter', request)
    with pytest.raises(ValueError): validate_package(package, 899)
    package['script'] += 'changed'
    with pytest.raises(ValueError): validate_package(package, 900)


def test_console_accepts_only_explicit_japanese_long_story_and_retries_same_job(monkeypatch):
    from worker import codex_local_console as console
    assert console.StartRequest(**REQUEST).duration_minutes == 180
    for changes in ({'language': 'ko'}, {'duration_minutes': 181}, {'youtube_url': 'https://example.invalid'}, {'duration_seconds': 3600}):
        with pytest.raises(ValueError): console.StartRequest(**{**REQUEST, **changes})
    from types import SimpleNamespace
    calls = []
    job_id = 'a' * 32
    bundle = {'job': {'status': 'interrupted'}, 'request': REQUEST, 'source': {}, 'references': []}
    monkeypatch.setattr(console, 'jobs', SimpleNamespace(load=lambda _: bundle,
        start=lambda *args, **kwargs: calls.append(kwargs) or {'id': kwargs.get('identity')}))
    assert console.retry_job(job_id)['id'] == job_id
    assert calls[0]['identity'] == job_id


def test_global_dialogue_indices_and_sfx_are_not_left_in_first_chapter(tmp_path):
    from worker.codex_dialogue import validate_dialogue
    base = producer([])
    def with_dialogue(identity, request):
        package = base(identity, request)
        scenes = package['structure']['scenes']
        raw = {'scenes': [{'scene_number': i, 'spans': []} for i in (1, 2)]}
        raw['scenes'][0]['spans'] = [{'text': '手紙', 'occurrence': 1, 'speaker': 'お鈴', 'status': 'confirmed', 'reason': 'fixture'}]
        package['structure']['dialogue_annotations'] = validate_dialogue(raw, scenes)
        package['sfx_cues'] = [{'id': 'chapter-local', 'scene_number': 1, 'anchor_scope': 'scene', 'anchor_source_text': scenes[0]['scene_text'], 'asset_id': 'footsteps', 'anchor_offset': 0}]
        return package
    result = produce_story('job', REQUEST, Runner(), lambda _: None, tmp_path, with_dialogue)
    assert result['structure']['dialogue_annotations']['dialogue_scene_index']['scene_numbers'] == list(range(1, 25, 2))
    assert result['structure']['video_dialogue_postwork_index']['scene_numbers'] == list(range(1, 19, 2))
    assert [c['scene_number'] for c in result['sfx_cues']] == list(range(1, 25, 2))
    assert len({c['id'] for c in result['sfx_cues']}) == 12
    assert len({c['script_version'] for c in result['sfx_cues']}) == 1
