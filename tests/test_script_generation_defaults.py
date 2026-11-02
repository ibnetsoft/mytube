import copy
import json
import pytest
from worker import codex_local_console as console
from worker import codex_publish_package as publishing


def raw_package():
    return {'publish_metadata': {'titles': ['Title one', 'Title two', 'Title three'],
            'description': 'A faithful description of the final story. ' * 5,
            'tags': ['one', 'two', 'three', 'four', 'five'], 'hashtags': ['#one', '#two', '#three']},
            'thumbnail_hook_texts': ['A reveal', 'A question', 'A contrast'],
            'thumbnail_image_prompt': 'A detailed faithful period illustration with one expressive face, clear dramatic contrast and a text-free landscape composition.',
            'thumbnail_text_layers': [{'text': 'A reveal'}]}


@pytest.mark.parametrize('retry', [False, True])
def test_new_default_reservation_does_not_migrate_old_retries(tmp_path, monkeypatch, retry):
    jobs = console.Jobs(tmp_path)
    monkeypatch.setattr(jobs, 'connect', lambda: None)
    monkeypatch.setattr(jobs, 'sync', lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs.pool, 'submit', lambda *args: None)
    try:
        request = console.StartRequest(mode='new', title='Test', category='story')
        result = jobs.start(request, None, retry_of='old' if retry else None)
        saved = json.loads((tmp_path/result['id']/'request.json').read_text())
        assert saved['required_video_scene_count'] == (18 if retry else 0)
        assert saved['generation_defaults_profile'] == (None if retry else 'efficient_v1')
        assert saved['generate_publish_package'] == (None if retry else True)
        assert saved['image_layer_scene_start'] is None
        assert saved['image_layer_scene_end'] is None
        assert saved['concentrated_scene_effects'] is False
    finally:
        jobs.pool.shutdown()


def test_saved_defaults_keep_work_specific_settings_and_explicit_overrides():
    settings = console.normalize_script_settings({'language': 'ja', 'setting_country': '일본',
        'era_region': '江戸', 'image_style': '일러스트', 'duration_minutes': 30})
    assert settings['required_video_scene_count'] == 0
    assert settings['generate_publish_package'] is True
    assert settings['language'] == 'ja' and settings['duration_minutes'] == 30
    override = console.normalize_script_settings({**settings, 'required_video_scene_count': 8,
                                                  'generate_publish_package': False})
    assert override['required_video_scene_count'] == 8
    assert override['generate_publish_package'] is False


def test_packaging_uses_final_script_and_reuses_unchanged_source_only():
    calls = []
    package = {'script': 'Final narration', 'language': 'ja', 'generated_title': 'Selected title',
               'content_setting': {'setting_country': '일본', 'era_region': '江戸'}, 'image_style': '일러스트',
               'remaining': ['메타데이터·썸네일 기획', '전체 장면 이미지 실제 생성·게시']}
    def stage(job, name, context, task):
        calls.append(copy.deepcopy(context)); return raw_package()
    publishing.plan_package(stage, 'new-job', package)
    assert calls[0]['final_script'] == 'Final narration' and calls[0]['language'] == 'ja'
    assert package['thumbnail_completed'] is False
    assert package['thumbnail_design']['render_status'] == 'awaiting_background'
    assert package['publish_package']['uploaded'] is False
    assert package['remaining'] == ['전체 장면 이미지 실제 생성·게시']
    publishing.plan_package(stage, 'new-job', package)
    assert len(calls) == 1
    package['script'] = 'Revised final narration'
    publishing.plan_package(stage, 'new-job', package)
    assert len(calls) == 2


def test_invalid_packaging_retries_with_feedback_without_changing_narration():
    calls = []
    package = {'script': 'Keep this final narration', 'language': 'ko'}
    def stage(job, name, context, task):
        calls.append(context)
        raw = raw_package()
        if len(calls) == 1: raw['publish_metadata']['description'] = 'too short'
        return raw
    publishing.plan_package(stage, 'new-job', package)
    assert len(calls) == 2 and calls[1]['validation_retry']['error']
    assert package['script'] == 'Keep this final narration'


@pytest.mark.parametrize('enabled', [True, False])
def test_new_workflow_profile_sets_production_policy_and_optional_packaging(tmp_path, monkeypatch, enabled):
    from worker import codex_local_workflow as workflow, script_guidelines, script_worker_store
    from worker import elevenlabs_performance, codex_content_runner
    source = {'script': 'Final script', 'language': 'ja', 'structure': {'scenes': []}}
    monkeypatch.setattr(workflow, '_produce', lambda *args: copy.deepcopy(source))
    monkeypatch.setattr(script_worker_store, 'ScriptStore', lambda: object())
    monkeypatch.setattr(script_guidelines, 'approved_guidelines', lambda *args: ([], ''))
    monkeypatch.setattr(elevenlabs_performance, 'annotate_new_package', lambda p, *args: p)
    calls = []
    def stage(self, job, name, context, task):
        calls.append(name); return raw_package()
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, '_stage', stage)
    package = workflow.produce('new', {'mode': 'new', 'generation_defaults_profile': 'efficient_v1',
        'generate_publish_package': enabled}, None, tmp_path, lambda text: None)
    assert package['structure']['layer_production_stage'] == 'post_submission'
    assert package['structure']['camera_policy'] == 'fixed_preferred_no_slow_zoom'
    assert len(calls) == int(enabled)
    assert ('publish_metadata' in package) == enabled
    assert source == {'script': 'Final script', 'language': 'ja', 'structure': {'scenes': []}}


def test_nonverbal_packaging_uses_actions_without_creating_spoken_script():
    seen = []
    package = {'script': '', 'action_script': 'A child points at a red ball and smiles.', 'language': 'ko'}
    def stage(job, name, context, task):
        seen.append(context); return raw_package()
    publishing.plan_package(stage, 'nonverbal', package)
    assert seen[0]['source_kind'] == 'nonverbal_action_script'
    assert seen[0]['final_script'] == package['action_script']
    assert package['script'] == ''
