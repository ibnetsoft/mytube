import sys
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))

from services.video_prompt_contract import silent_video_prompt
from codex_content_runner import _validate_video_prompt, CodexContentError
from hermes_worker import _sanitize_video_prompt_text, _validate_video_prompt_quality


def prompt(guard):
    return (
        'Osuzu silently speaks to her mother with natural repeated lip opening and closing and subtle '
        'jaw movement. Her mother listens with her mouth closed. Their faces and Edo-period clothes '
        'remain stable, lantern light flickers softly, and both settle into a closed-mouth end pose. '
        'Camera: slow push-in. ' + guard + ', no narration, no subtitles, no captions, no music, '
        'no sound effects, no audio.'
    )


def test_visible_speech_passes_both_generation_validators():
    text = prompt('no audible dialogue')
    _validate_video_prompt(text, 1)
    _validate_video_prompt_quality({'video_prompt': text}, '1')


def test_legacy_prompt_remains_valid_and_new_sanitization_is_idempotent():
    original = prompt('no dialogue')
    _validate_video_prompt(original, 1)
    cleaned = _sanitize_video_prompt_text(original)
    assert 'no dialogue' not in cleaned
    assert 'no audible dialogue' in cleaned
    assert 'repeated lip opening and closing' in cleaned
    assert _sanitize_video_prompt_text(cleaned) == cleaned
    assert silent_video_prompt(cleaned) == cleaned


def test_visible_speech_does_not_allow_generated_audio():
    with pytest.raises(ValueError, match='positive audio'):
        _validate_video_prompt_quality({'video_prompt': prompt('no audible dialogue') + ' Add audio.'}, '1')
    with pytest.raises(CodexContentError, match='no audible dialogue'):
        _validate_video_prompt(prompt('silent performance'), 1)


def test_publish_gate_accepts_silent_visual_speech_without_new_errors():
    from services.generation_quality_gate import validate_generation_package
    package = runpy.run_path(str(ROOT / 'tests/test_generation_quality_gate.py'))['_valid_payload']()
    before = validate_generation_package(package)
    for scene in package['structure']['scenes']:
        if scene.get('video_prompt'):
            scene['video_prompt'] = silent_video_prompt(scene['video_prompt'])
    assert validate_generation_package(package) == before
