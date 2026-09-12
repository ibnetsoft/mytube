import asyncio
import base64

import pytest

from worker import gemini_web_narration as audio


def test_split_keeps_narration_free_and_dialogue_on_configured_voice():
    segments = audio.split_script('문이 열렸다. “누구세요?” 대답은 없었다.', 'actor')
    assert [s['kind'] for s in segments] == ['narration', 'dialogue', 'narration']
    assert segments[1]['voice_id'] == 'actor'
    assert all(not s.get('voice_id') for s in segments if s['kind'] == 'narration')


def test_quotes_without_voice_fail_before_any_paid_request():
    with pytest.raises(ValueError, match='VOICE_ID'):
        audio.split_script('그는 말했다. "안녕."')


def test_long_narration_has_no_dropped_characters():
    text = '가나다라마바사아자차카타파하' * 200
    segments = audio.split_script(text)
    assert ''.join(s['text'] for s in segments) == text
    assert max(len(s['text']) for s in segments) <= 1200


def test_invalid_capture_is_never_accepted_as_audio():
    with pytest.raises(RuntimeError):
        audio.decode_audio_result({'error': 'stream unsupported'})
    with pytest.raises(ValueError):
        audio.decode_audio_result({'value': 'https://example.com/audio'})
    data = b'ID3test'
    assert audio.decode_audio_result({'value': 'data:audio/mpeg;base64,' + base64.b64encode(data).decode()}) == data


def test_disabled_stage_never_starts_browser(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_WEB_NARRATION_ENABLED', '0')
    async def unexpected(*args):
        raise AssertionError('browser started')
    monkeypatch.setattr(audio, 'run_audio_stage', unexpected)
    package = {'script':'hello'}
    audio.maybe_generate_audio(package, {}, tmp_path)
    assert 'narration_audio' not in package


def test_requested_audio_failure_propagates_instead_of_marking_complete(monkeypatch, tmp_path):
    async def login_required(*args):
        raise RuntimeError('login required')
    monkeypatch.setattr(audio, 'run_audio_stage', login_required)
    with pytest.raises(RuntimeError, match='login required'):
        audio.maybe_generate_audio({'script':'hello'}, {'generate_gemini_narration': True}, tmp_path)


def test_guest_gemini_composer_does_not_count_as_logged_in(tmp_path):
    class Login:
        @property
        def first(self):
            return self
        async def count(self):
            return 1
        async def is_visible(self):
            return True
    class GuestPage:
        async def goto(self, *args, **kwargs):
            pass
        def get_by_role(self, role, **kwargs):
            assert role in {'button', 'link'}, 'must stop before typing into guest composer'
            return Login()
    browser = audio.GeminiBrowser(None)
    browser.page = GuestPage()
    with pytest.raises(RuntimeError, match='signed out'):
        asyncio.run(browser.generate('Do not send this text', tmp_path / 'audio'))


def test_rejected_setup_never_reopens_login_browser():
    with pytest.raises(RuntimeError, match='setup path is disabled'):
        asyncio.run(audio.setup())
