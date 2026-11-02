import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'worker'))
from worker.script_topic_delivery import expand_direction_templates, chunked_direction, publish_topic, topic_row, web_readiness
from services.image_grid_prompts import build_compact_image_grid_prompts


def candidate():
    scenes = [{'scene_number': i, 'scene_order': i,
               'image_prompt': f'A unique detailed scene {i}. ' + 'Period appropriate harbor setting, objects, precise composition and restrained light. '*3,
               'media_prompt_status': 'ready', 'video_prompt_required': False} for i in range(1, 5)]
    panels = [{'scene_number': i, 'scene_id': f'scene{i:03d}', 'position': p,
               'panel_prompt': f'Scene {i} depicts a distinct harbor story beat with exact historical architecture, restrained lighting and original composition.'}
              for i, p in enumerate(['Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right'], 1)]
    grids = build_compact_image_grid_prompts([{'grid_number': 1, 'scene_numbers': [1, 2, 3, 4],
                                              'shared_style': 'Meiji ink painting', 'panels': panels}])
    return {'generated_title': 'A new story', 'script': 'actual reviewed narration',
            'structure': {'scenes': scenes, 'image_grid_prompts': grids,
                          'image_grid_prompt_status': 'ready', 'required_video_scene_count': 0},
            'publish_metadata': {'description': 'A complete description'},
            'thumbnail_hook_texts': ['one', 'two', 'three'], 'thumbnail_image_prompt': 'actual authored prompt'}


def request():
    return {'title': 'A new story', 'category_id': '13', 'language': 'ja',
            'duration_minutes': 45, 'required_video_scene_count': 0}


class Store:
    def __init__(self, existing=None, unknown_post=False):
        self.rows = [existing] if existing else []
        self.posts = 0
        self.unknown_post = unknown_post
    def request(self, method, table, **kwargs):
        assert table == 'topics_queue'
        if method == 'POST':
            self.posts += 1
            self.rows.append({'id': 9999, **copy.deepcopy(kwargs['body'])})
            if self.unknown_post:
                raise TimeoutError('Acknowledgment lost after successful insert')
        elif method != 'GET':
            raise AssertionError('No updates to existing topics allowed')
        return copy.deepcopy(self.rows), len(self.rows)


def test_actual_web_predicate_rejects_missing_prompts_and_claimed_topics(tmp_path):
    row = topic_row('a'*32, candidate(), request())
    assert web_readiness(row, tmp_path)['ready']
    broken = copy.deepcopy(row)
    broken['pregenerated_structure']['scenes'][0]['image_prompt'] = ''
    assert not web_readiness(broken, tmp_path)['ready']
    row['assigned_at'] = '2026-10-29T00:00:00Z'
    assert not web_readiness(row, tmp_path)['ready']


def test_delivery_registers_exactly_once_and_preserves_truthful_asset_state(tmp_path):
    store = Store()
    package = candidate()
    first = publish_topic('a'*32, package, request(), store, tmp_path)
    second = publish_topic('a'*32, package, request(), store, tmp_path)
    assert first == second and store.posts == 1
    assert package == candidate()
    assert store.rows[0]['progress_payload']['image_generation_status'] == 'not_started'
    assert store.rows[0]['progress_payload']['thumbnail_completed'] is False
    assert store.rows[0]['assigned_employee_email'] == ''
    assert store.rows[0]['assigned_at'] is None


def test_scene_translations_are_preserved_on_registration(tmp_path):
    store = Store()
    package = candidate()
    package['script_translations'] = {'ko': {'blocks': [{'index': 0, 'source_text': 'original', 'translated_text': '번역'}]},
                                      'th': {'blocks': [{'index': 0, 'source_text': 'original', 'translated_text': 'แปล'}]}}
    publish_topic('a'*32, package, request(), store, tmp_path)
    assert store.rows[0]['progress_payload']['script_translations'] == package['script_translations']
    assert store.rows[0]['progress_payload']['image_generation_status'] == 'not_started'


def test_unknown_insert_outcome_is_recovered_without_duplicate(tmp_path):
    store = Store(unknown_post=True)
    result = publish_topic('a'*32, candidate(), request(), store, tmp_path)
    assert result['topic_id'] == 9999 and store.posts == 1


def test_existing_owned_topic_is_never_updated(tmp_path):
    row = {'id': 9999, **topic_row('a'*32, candidate(), request()), 'assigned_employee_email': 'someone@example.test'}
    store = Store(row)
    with pytest.raises(ValueError, match='owned'):
        publish_topic('a'*32, candidate(), request(), store, tmp_path)
    assert store.posts == 0 and store.rows == [row]


def test_direction_batches_preserve_scene_order_and_retry_only_bad_batch(monkeypatch):
    import scene_visual_director
    context = {'scenes': [{'scene_number': i, 'scene_text': f'locked {i}'} for i in range(1, 46)],
               'structure': {'scenes': ['old planning']}, 'script': 'complete final script',
               'direction_profile': {'id': 'standard'}}
    original = copy.deepcopy(context)
    calls = []
    def validate(scenes, result, **kwargs):
        if [r['number'] for r in result['scene_directions']] != [s['scene_number'] for s in scenes]:
            raise ValueError('Wrong scene coverage')
        return result['scene_directions']
    monkeypatch.setattr(scene_visual_director, 'validate_directorial_plans', validate)
    def stage(identity, name, data, task):
        numbers = [s['scene_number'] for s in data['scenes']]
        calls.append(numbers)
        assert len(numbers) <= 20 and data['structure']['scenes'] == data['scenes']
        assert data['script'] == original['script']
        # The middle group fails once. The successful first group must not rerun.
        output = numbers[:-1] if numbers[0] == 21 and calls.count(numbers) == 1 else numbers
        return {'topic_direction': {'shared': 'actual authored style'},
                'scene_directions': [{'number': n} for n in output]}
    result = chunked_direction(stage, 'test-no-saved-directions', '02f_scene_visual_director', context, 'author')
    assert [r['number'] for r in result['scene_directions']] == list(range(1, 46))
    assert [group[0] for group in calls] == [1, 21, 21, 41]
    assert context == original


def test_explicit_direction_templates_preserve_authored_overrides_and_reject_missing_references():
    raw = {'scene_direction_templates': {'quiet': {'execution_design': {'camera': {'kind': 'hold', 'reason': 'Read the clue'}, 'effects': []}}},
           'scene_directions': [{'scene_number': 21, 'template_id': 'quiet', 'execution_design': {'camera': {'reason': 'Examine the sealed letter'}}}]}
    original = copy.deepcopy(raw)
    expanded = expand_direction_templates(raw)['scene_directions'][0]
    assert expanded['execution_design']['camera'] == {'kind': 'hold', 'reason': 'Examine the sealed letter'}
    assert expanded['execution_design']['effects'] == [] and raw == original
    raw['scene_directions'][0]['template_id'] = 'absent'
    with pytest.raises(ValueError, match='Unknown'):
        expand_direction_templates(raw)
