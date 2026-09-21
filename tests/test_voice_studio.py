import base64
import io
import json
import wave

import pytest

from services.voice_studio import VertexTTS, VoicePreset, VoiceStudio, pcm_response_wav
from worker.voice_studio_runner import segments_from_script, maybe_generate_voice_studio


def sample_wav():
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x00\x01' * 12000)
    return out.getvalue()


def test_vertex_uses_explicit_billing_project_and_voice():
    class Response:
        ok = True
        def json(self):
            return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {
                'mimeType': 'audio/L16;codec=pcm;rate=24000', 'data': base64.b64encode(b'\0\0'*24).decode()}}]}}]}
    class Session:
        def post(self, url, **kwargs):
            self.url, self.kwargs = url, kwargs
            return Response()
    session = Session()
    audio, _ = VertexTTS('credit-project', session=session).synthesize('안녕하세요.', VoicePreset(), '조용하게')
    assert '/projects/credit-project/' in session.url
    assert session.kwargs['headers']['x-goog-user-project'] == 'credit-project'
    assert session.kwargs['json']['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Charon'
    with wave.open(io.BytesIO(audio), 'rb') as result:
        assert result.getframerate() == 24000 and result.getnframes() == 24


@pytest.mark.parametrize('finish', ['MAX_TOKENS', 'SAFETY', None])
def test_truncated_audio_is_rejected(finish):
    with pytest.raises(ValueError):
        pcm_response_wav({'candidates': [{'finishReason': finish}]})


class FakeProvider:
    def __init__(self):
        self.calls = []
    def synthesize(self, text, preset, direction):
        self.calls.append(text)
        return sample_wav(), {'totalTokenCount': 10}


def studio(provider, limit=1000):
    return VoiceStudio({'n': {'direction': '', 'pause_ms': 100}}, {'vertex': provider}, {'vertex': limit})


def test_cache_and_partial_regeneration_keep_other_segments(tmp_path):
    provider = FakeProvider()
    engine = studio(provider)
    segments = [{'id': 'a', 'text': '첫 문장', 'preset': 'n'}, {'id': 'b', 'text': '두 번째', 'preset': 'n'}]
    first = engine.run(segments, tmp_path)
    assert provider.calls == ['첫 문장', '두 번째']
    engine.run(segments, tmp_path)
    assert len(provider.calls) == 2
    old = json.loads((tmp_path/'voice-studio.json').read_text(encoding='utf-8'))['segments']['b']['file']
    result = engine.run(segments, tmp_path, regenerate=['a'])
    assert provider.calls == ['첫 문장', '두 번째', '첫 문장']
    assert json.loads((tmp_path/'voice-studio.json').read_text(encoding='utf-8'))['segments']['b']['file'] == old
    assert result['timeline'][1]['start'] == pytest.approx(result['timeline'][0]['end'] + .1)


def test_changed_scene_direction_invalidates_only_that_segment(tmp_path):
    provider = FakeProvider()
    engine = studio(provider)
    segments = [{'id': 'a', 'text': '첫 문장', 'preset': 'n'}, {'id': 'b', 'text': '두 번째', 'preset': 'n'}]
    engine.run(segments, tmp_path)
    segments[1]['direction'] = '슬프게'
    engine.run(segments, tmp_path)
    assert provider.calls == ['첫 문장', '두 번째', '두 번째']


def test_limit_stops_before_provider_and_failed_attempt_stays_reserved(tmp_path):
    class Failing(FakeProvider):
        def synthesize(self, *args):
            self.calls.append('attempt')
            raise TimeoutError('uncertain delivery')
    provider = Failing()
    engine = studio(provider, limit=3)
    segments = [{'id':'a', 'text':'abc', 'preset':'n'}]
    with pytest.raises(TimeoutError):
        engine.run(segments, tmp_path)
    with pytest.raises(RuntimeError, match='limit'):
        engine.run(segments, tmp_path)
    assert len(provider.calls) == 1


def test_script_routing_and_disabled_worker(monkeypatch, tmp_path):
    result = segments_from_script('그가 물었다. “누구세요?” 바람이 불었다.')
    assert [s['preset'] for s in result] == ['narrator','dialogue','narrator']
    monkeypatch.setenv('VOICE_STUDIO_ENABLED', '0')
    package = {'script': '아침이다.'}
    maybe_generate_voice_studio(package, {}, tmp_path / 'disabled')
    assert 'narration_audio' not in package
    assert not (tmp_path / 'disabled').exists()


def test_invalid_inputs_are_rejected_before_synthesis(tmp_path):
    provider = FakeProvider()
    with pytest.raises(ValueError):
        studio(provider).run([{'id': [], 'text': 'hello', 'preset': 'n'}], tmp_path)
    with pytest.raises(ValueError):
        VoicePreset(pause_ms=1.5).validate()
    assert provider.calls == []


def test_each_segment_keeps_its_own_pause(tmp_path):
    engine = studio(FakeProvider())
    result = engine.run([
        {'id': 'a', 'text': '문장 중간', 'preset': 'n', 'pause_ms': 0},
        {'id': 'b', 'text': '끝입니다.', 'preset': 'n', 'pause_ms': 260},
        {'id': 'c', 'text': '다음 문장', 'preset': 'n', 'pause_ms': 0},
    ], tmp_path)
    timeline = result['timeline']
    assert timeline[1]['start'] == timeline[0]['end']
    assert timeline[2]['start'] - timeline[1]['end'] == pytest.approx(.260)


def test_elevenlabs_context_and_native_speed_are_sent(monkeypatch):
    from services.voice_studio import ElevenDialogue
    calls = []
    class Response:
        ok = True
        content = b'audio'
        headers = {'request-id': 'request-123'}
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        return Response()
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'test-only')
    monkeypatch.setattr('requests.post', post)
    preset = VoicePreset(provider='elevenlabs', voice='narrator', model='eleven_multilingual_v2', direction='', speed=.9)
    _, usage = ElevenDialogue().synthesize('보따리를 들었습니다.', preset, '', previous_text='그는', next_text='그리고 걸었습니다.')
    assert calls[0]['voice_settings']['speed'] == .9
    assert calls[0]['previous_text'] == '그는'
    assert calls[0]['next_text'] == '그리고 걸었습니다.'
    assert usage['native_speed'] == .9


def test_native_speed_is_not_applied_twice(tmp_path, monkeypatch):
    from services.voice_studio import ElevenDialogue
    import services.voice_studio as module
    speeds = []
    original = module.normalize_audio
    def normalize(source, target, speed):
        speeds.append(speed)
        return original(source, target, speed)
    monkeypatch.setattr(module, 'normalize_audio', normalize)
    monkeypatch.setattr(ElevenDialogue, 'synthesize', lambda *a, **kw: (sample_wav(), {'native_speed': .9}))
    engine = VoiceStudio({'n': {'provider': 'elevenlabs', 'voice': 'narrator', 'direction': '', 'speed': .9}}, {'elevenlabs': ElevenDialogue()})
    engine.run([{'id': 'a', 'text': 'hello', 'preset': 'n'}], tmp_path)
    assert speeds == [1.0]


def test_enabled_worker_checkpoints_and_propagates_failure(monkeypatch, tmp_path):
    def fail(package, directory):
        assert json.loads((directory / 'content-package.json').read_text(encoding='utf-8')) == package
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr('worker.voice_studio_runner.generate', fail)
    package = {'script': '아침이다.'}
    with pytest.raises(RuntimeError, match='provider unavailable'):
        maybe_generate_voice_studio(package, {'generate_voice_studio': True}, tmp_path)
    assert 'narration_audio' not in package
