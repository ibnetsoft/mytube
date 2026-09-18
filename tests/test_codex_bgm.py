from copy import deepcopy
from worker.codex_bgm import plan_package_bgm


def test_final_story_saved_separately_and_reused_until_text_changes():
    class Runner:
        calls = 0
        def _stage(self, job, stage, context, task):
            self.calls += 1
            assert stage == '07_bgm_prompt'
            assert context['final_script']
            return {'prompt_en': 'Gentle traditional strings and soft bamboo flute, slow tempo, moving from quiet tension to tender relief, sparse arrangement under narration.',
                    'description_ko': '사극의 긴장감에서 따뜻한 결말로 이어지는 감정을 잔잔한 현악기로 표현합니다.'}
    runner = Runner()
    package = {'script': '덕수는 조심스럽게 문을 열었다.', 'structure': {'scenes': [{'text': '대사'}]}}
    original = deepcopy(package)
    plan = plan_package_bgm(runner, 'test', package, enabled=True)
    assert plan['status'] == 'ready' and plan['audio_generated'] is False
    assert 'No vocals' in plan['prompt_en']
    assert package['script'] == original['script']
    assert package['structure']['scenes'] == original['structure']['scenes']
    assert package['structure']['bgm_prompt'] == plan
    plan_package_bgm(runner, 'test', package, enabled=True)
    assert runner.calls == 1
    package['script'] += ' 마침내 안도했다.'
    assert plan_package_bgm(runner, 'test', package, enabled=True)['script_version'] != plan['script_version']
    assert runner.calls == 2


def test_failure_does_not_discard_script_or_mark_prompt_ready():
    class Runner:
        def _stage(self, *args):
            return {'prompt_en': 'invalid'}
    package = {'script': '보존할 대본', 'structure': {}}
    plan = plan_package_bgm(Runner(), 'test', package, enabled=True)
    assert plan['status'] == 'failed' and 'prompt_en' not in plan
    assert package['script'] == '보존할 대본'


def test_default_off_never_calls_model_and_preserves_existing_prompt():
    class Runner:
        def _stage(self, *args):
            raise AssertionError('Must not call model')
    package = {'script': '대본', 'structure': {'bgm_prompt': {'status': 'ready', 'prompt_en': 'saved'}}}
    original = deepcopy(package)
    assert plan_package_bgm(Runner(), 'off', package)['status'] == 'skipped'
    for flag in (False, None, 'true', 1):
        assert plan_package_bgm(Runner(), 'off', package, enabled=flag)['status'] == 'skipped'
    assert package == original
