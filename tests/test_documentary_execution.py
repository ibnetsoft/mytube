"""Exercise CLI boundaries and block ungrounded generation before planning."""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import codex_content_runner as module
from worker.japanese_historical_documentary import PROFILE, prepare_request


@pytest.mark.parametrize('name,search', [('00_documentary_research', True),
                                        ('02j_documentary_evidence_review', False),
                                        ('02_subtitle_translation', False)])
def test_live_search_is_confined_to_historical_research(monkeypatch, tmp_path, name, search):
    monkeypatch.setattr(module, 'OUTPUT_DIR', tmp_path)
    captured = {}
    def run(command, **kwargs):
        captured['command'] = command
        captured['prompt'] = kwargs['stdin'].read().decode('utf-8')
        path = pathlib.Path(command[command.index('--output-last-message') + 1])
        path.write_text('{"ok":true}', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(module.subprocess, 'run', run)
    runner = module.CodexStagedContentRunner(module.CodexContentConfig('codex', '', 60))
    runner._stage('documentary', name, {'script_style': PROFILE['key']}, 'Review supplied evidence.')
    assert ('--search' in captured['command']) is search
    assert captured['command'][captured['command'].index('--sandbox') + 1] == 'read-only'
    assert 'Historical documentary overrides all generic fiction instructions' in captured['prompt']
    if search:
        assert 'do not web-search' not in captured['prompt']
    else:
        assert 'do not web-search' in captured['prompt']


def test_missing_sources_stop_before_a_plan_or_script_is_created(monkeypatch):
    called = []
    def stage(self, job, name, context, task):
        called.append(name)
        return {'historical_sources': [], 'missing_evidence': []}
    monkeypatch.setattr(module.CodexStagedContentRunner, '_stage', stage)
    runner = module.CodexStagedContentRunner(module.CodexContentConfig('codex', '', 60))
    with pytest.raises(ValueError, match='최소 2개'):
        runner.generate('missing-evidence', {'script_style': PROFILE['key']}, script_only=True)
    assert called == ['00_documentary_research', '00_documentary_research']


def test_legacy_assigned_style_becomes_canonical_and_does_not_duplicate_notes():
    request = prepare_request({'assigned_script_style': PROFILE['key'], 'notes': 'Focus on documented decisions.'})
    twice = prepare_request(request)
    assert twice['script_style'] == PROFILE['key']
    assert twice['notes'] == request['notes']
    assert twice['direction_profile'] == 'standard'
