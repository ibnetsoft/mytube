from copy import deepcopy
from worker import codex_sfx as sfx
from worker.codex_local_workflow import finalize_sfx


class Runner:
    def __init__(self):
        self.context = None

    def _stage(self, job, stage, context, task):
        self.context = context
        assert stage == '06_sfx_plan'
        return {'cues': [{'unit_index': 0, 'asset_id': 'door', 'word_boundary': 1,
                          'confidence': .95, 'reason': '문이 열리는 장면'}]}


def test_new_final_script_gets_sfx_without_text_or_voice_changes(monkeypatch):
    monkeypatch.setattr(sfx, 'load_catalog', lambda: [{'id': 'door', 'file_name': 'door.mp3'}])
    package = {'script': '문을 열었다.', 'structure': {'scenes': [{'scene_order': 1, 'scene_text': '문을 열었다.'}]}}
    original = deepcopy(package)
    runner = Runner()
    result = finalize_sfx(runner, 'new', package, lambda _: None)
    assert result['sfx_plan']['status'] == 'ready'
    assert len(result['sfx_cues']) == 1
    assert result['script'] == original['script']
    assert result['structure']['scenes'] == original['structure']['scenes']
    assert runner.context['units'][0]['text'] == original['script']


def test_repair_preserves_manual_deletions_and_marks_lost_anchors(monkeypatch):
    monkeypatch.setattr(sfx, 'load_catalog', lambda: [{'id': 'door', 'file_name': 'door.mp3'}])
    cues = [{'id': 'manual', 'asset_id': 'door', 'source': 'manual', 'scene_number': 1,
             'subtitle_text': '문을 열었다.', 'word_boundary': 0, 'enabled': True},
            {'id': 'deleted', 'asset_id': 'door', 'scene_number': 2, 'enabled': False}]
    snapshot = {'row': {'project_payload': {'render_settings': {'sfx_cues': cues}}}, 'structure': {}}
    package = {'script': '조용히 앉았다.', 'structure': {'scenes': [{'scene_order': 1, 'scene_text': '조용히 앉았다.'}]}}
    runner = Runner()
    result = finalize_sfx(runner, 'repair', package, lambda _: None, snapshot)
    assert runner.context is None  # Manual scene is protected, including invalid anchors.
    assert result['sfx_cues'][0]['needs_review'] and result['sfx_cues'][0]['enabled'] is False
    assert result['sfx_cues'][1] == cues[1]
    assert cues[0]['enabled'] is True  # Original snapshot remains intact.


def test_valid_ai_is_reused_and_catalog_failure_is_visible(monkeypatch):
    cue = {'id': 'ai', 'asset_id': 'door', 'source': sfx.VERSION, 'scene_number': 1,
           'anchor_scope': 'scene', 'anchor_source_text': '문을 열었다.', 'anchor_offset': 0}
    units = [{'scene_number': 1, 'text': '문을 열었다.'}]
    assert sfx.repair_existing_cues([cue], units)[0]['keep_ai'] is True
    def fail():
        raise RuntimeError('private backend details')
    monkeypatch.setattr(sfx, 'load_catalog', fail)
    package = {'script': '문을 열었다.', 'structure': {'scenes': [{'scene_order': 1, 'scene_text': '문을 열었다.'}]}}
    result = finalize_sfx(Runner(), 'fail', package, lambda _: None)
    assert result['sfx_plan']['status'] == 'failed'
    assert any('재시도' in item for item in result['remaining'])
    assert 'private' not in result['sfx_plan']['error']
