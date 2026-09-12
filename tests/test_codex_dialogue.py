import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from codex_dialogue import validate_dialogue, ASTRA_MODEL

def test_ai_spans_preserve_exact_source_and_uncertainty():
    text = '문서에는 돌아오라 적혀 있었다. 이제 돌아오라. 그가 말했다.'
    result = validate_dialogue({'scenes': [{'scene_number': 1, 'spans': [
        {'text': '돌아오라.', 'occurrence': 1, 'speaker': '아버지', 'status': 'confirmed', 'reason': '아버지가 직접 말함'},
        {'text': '문서에는', 'occurrence': 1, 'speaker': '', 'status': 'uncertain', 'reason': '발화 불확실'}]}]}, [{'scene_text': text}])
    assert result['model'] == ASTRA_MODEL
    for span in result['scenes'][0]['spans']:
        assert text[span['start']:span['end']] == span['text']

@pytest.mark.parametrize('spans', [
    [{'text': '없는 대사', 'occurrence': 1}],
    [{'text': '같은 말', 'occurrence': 3}],
    [{'text': '같은 말', 'occurrence': 1, 'status': 'confirmed', 'speaker': '', 'reason': 'x'}],
])
def test_rejects_invalid_ai_output(spans):
    with pytest.raises(ValueError):
        validate_dialogue({'scenes': [{'scene_number': 1, 'spans': spans}]}, [{'scene_text': '같은 말 같은 말'}])

def test_no_dialogue_is_valid_but_missing_analysis_is_not():
    assert validate_dialogue({'scenes': [{'scene_number': 1, 'spans': []}]}, [{'scene_text': '말했습니다.'}])['scenes'][0]['spans'] == []
    with pytest.raises(ValueError): validate_dialogue({}, [{'scene_text': '말했습니다.'}])

def test_script_stage_pins_astra_even_if_other_model_configured(monkeypatch, tmp_path):
    import json
    import subprocess
    import codex_content_runner as runner
    monkeypatch.setattr(runner, 'OUTPUT_DIR', tmp_path)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps({'ok': True}), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(runner.subprocess, 'run', run)
    stage = runner.CodexStagedContentRunner(runner.CodexContentConfig('codex', 'other-model', 60))
    for name in ['02_script', '02b_script_qa', '02c_senior_review', '02e_dialogue']:
        stage._stage('test', name, {}, 'test')
        assert calls[-1][calls[-1].index('--model') + 1] == ASTRA_MODEL
    stage._stage('test', '01_plan', {}, 'test')
    assert calls[-1][calls[-1].index('--model') + 1] == 'other-model'
