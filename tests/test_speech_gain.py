import math
import wave
from array import array

import pytest

from services.speech_gain import balance_speech_wav, subtitle_gain, speech_normalization, prepare_speech_audio


def test_volume_range_and_legacy_mute():
    assert subtitle_gain({'volume': 200}) == 2
    assert subtitle_gain({'volume_ratio': 0}) == 0
    assert subtitle_gain({'volume': 0, 'volume_ratio': 2}) == 0
    assert subtitle_gain({'volume': 'bad'}) == 1
    assert subtitle_gain({'volume': float('nan')}) == 1
    assert speech_normalization([0] * 100) == 1


def test_quiet_speaker_balanced_then_manual_gain_without_timing_change(tmp_path):
    rate = 48000
    source, target = tmp_path / 'source.wav', tmp_path / 'balanced.wav'
    # Same speech-like signal at two input levels, then boosted and muted copies.
    tones = [array('h', (round(amplitude * math.sin(i * 2 * math.pi * 440 / rate))
                        for i in range(rate))) for amplitude in (8000, 2000, 2000, 2000)]
    with wave.open(str(source), 'wb') as writer:
        writer.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        for tone in tones:
            writer.writeframes(tone.tobytes())
    duration = balance_speech_wav(source, target, [
        {'start': i, 'end': i + 1, 'volume': volume}
        for i, volume in enumerate((100, 100, 200, 0))
    ])
    with wave.open(str(target), 'rb') as reader:
        assert reader.getnframes() == 4 * rate
        samples = array('h', reader.readframes(reader.getnframes()))
    rms = [math.sqrt(sum(x*x for x in samples[i*rate:(i+1)*rate]) / rate) for i in range(4)]
    assert duration == 4
    assert rms[1] == pytest.approx(rms[0], rel=0.03)
    assert rms[2] == pytest.approx(rms[1] * 2, rel=0.001)
    assert rms[3] == 0
    assert max(abs(x) for x in samples) < 32767


def test_ffmpeg_preparation_preserves_stereo_gaps_and_mute(tmp_path):
    import imageio_ffmpeg
    rate = 24000
    source = tmp_path / 'stereo.wav'
    with wave.open(str(source), 'wb') as writer:
        writer.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(array('h', [2000, -1000] * rate).tobytes())
    output, duration = prepare_speech_audio(source, tmp_path, imageio_ffmpeg.get_ffmpeg_exe(),
        [{'start': 0.25, 'end': 0.75, 'volume_ratio': 0}])
    with wave.open(output, 'rb') as reader:
        assert reader.getnchannels() == 2
        assert reader.getnframes() == 48000
        reader.setpos(24000)
        assert set(array('h', reader.readframes(100))) == {0}
        reader.setpos(100)
        assert max(array('h', reader.readframes(100))) > 1000
    assert duration == 1


def test_render_sanitizer_preserves_gain():
    # Load this pure function without starting app/database services.
    import ast
    import re
    from pathlib import Path
    module = ast.parse((Path(__file__).parents[1] / 'services/remote_render_service.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == '_sanitize_subtitles_for_render')
    namespace = {'re': re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<sanitizer>', 'exec'), namespace)
    clean = namespace['_sanitize_subtitles_for_render']([
        {'start': 0, 'end': 1, 'text': '대사', 'volume': 200},
        {'start': 1, 'end': 2, 'text': '음소거', 'volume_ratio': 0},
    ])
    assert clean[0]['volume'] == 200
    assert clean[1]['volume_ratio'] == 0
