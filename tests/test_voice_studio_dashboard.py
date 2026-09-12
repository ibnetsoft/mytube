import json
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from worker import voice_studio_dashboard as dashboard
from worker import voice_studio_library as library
from worker.voice_studio_runner import DEFAULT_CONFIG


def client(tmp_path):
    app = FastAPI()
    app.include_router(dashboard.create_router(tmp_path))
    return TestClient(app)


def test_catalog_selection_and_cross_site_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'library_root', lambda: tmp_path / 'choices')
    api = client(tmp_path)
    voices = api.get('/api/voice-studio/voices').json()['voices']
    assert len(voices) == len({v['name'] for v in voices}) == 30
    assert sum(v['gender'] == '여성' for v in voices) == 14
    value = {'voice': 'Kore', 'speed': .95, 'direction': '차분하게', 'dialogue_mode': 'narrator'}
    assert api.put('/api/voice-studio/choice/topic_42', json=value).status_code == 403
    assert api.put('/api/voice-studio/choice/topic_42', json=value, headers={'X-Voice-Studio':'1','Origin':'https://evil.example'}).status_code == 403
    assert api.put('/api/voice-studio/choice/topic_42', json=value, headers={'X-Voice-Studio':'1'}).status_code == 200
    choice = library.read_choice(library.package_key({'topic_queue_id':42}))
    config = library.config_with_choice(DEFAULT_CONFIG, choice)
    assert config['presets']['narrator']['voice'] == 'Kore'
    assert config['dialogue_preset'] == 'narrator'
    assert DEFAULT_CONFIG['presets']['narrator']['voice'] == 'Charon'
    assert library.read_choice('topic_43') is None
    assert api.post('/api/voice-studio/sample/Invalid', headers={'X-Voice-Studio':'1'}).status_code == 400


def test_sample_job_audio_and_generation_choice(tmp_path, monkeypatch):
    calls = []
    def fake(package, directory, config):
        calls.append((package, config))
        directory.mkdir(parents=True, exist_ok=True)
        audio = directory / 'test.wav'
        audio.write_bytes(b'RIFFtest')
        return {'audio_path': str(audio), 'duration_seconds': 1}
    monkeypatch.setattr(dashboard, 'generate', fake)
    api = client(tmp_path)
    job = api.post('/api/voice-studio/sample/Kore', headers={'X-Voice-Studio':'1'}).json()
    for _ in range(100):
        job = api.get('/api/voice-studio/jobs/' + job['id']).json()
        if job['status'] == 'complete':
            break
        time.sleep(.01)
    assert job['status'] == 'complete'
    assert api.get(job['audio_url']).content == b'RIFFtest'
    assert calls[0][1]['presets']['narrator']['voice'] == 'Kore'
    assert calls[0][0]['voice_segments'][0]['text'] == library.SAMPLE_TEXT
    assert api.get('/api/voice-studio/audio/%2e%2e%2fsecret.wav').status_code == 404


def test_saved_choice_is_read_by_worker(tmp_path, monkeypatch):
    from worker import voice_studio_runner as runner
    monkeypatch.setattr(library, 'library_root', lambda: tmp_path / 'choices')
    library.save_choice('topic_77', {'voice':'Sulafat','direction':'조용하게','dialogue_mode':'narrator'})
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    def run(self, segments, directory, regenerate):
        assert self.presets['narrator'].voice == 'Sulafat'
        assert all(s['preset'] == 'narrator' for s in segments)
        return {'ok':True}
    monkeypatch.setattr(runner.VoiceStudio, 'run', run)
    assert runner.generate({'topic_queue_id':77,'script':'그가 말했다. “안녕.”'}, tmp_path)['ok']


def test_ui_script_is_in_inline_block_not_external_script():
    from worker.voice_studio_ui import inject
    html = '<script src="external.js"></script><script>function switchTab(){}</script>'
    result = inject(html)
    assert '<script src="external.js"></script>' in result
    assert result.index('let vsVoices') > result.index('<script>')
