from types import SimpleNamespace

import pytest
from worker import youtube_transcript as service


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=vLB3e-eH2j8&t=20',
    'https://youtu.be/vLB3e-eH2j8?si=abc',
    'https://m.youtube.com/shorts/vLB3e-eH2j8',
    'https://www.youtube.com/live/vLB3e-eH2j8',
    'https://www.youtube.com/embed/vLB3e-eH2j8',
])
def test_urls(url):
    assert service.video_id_from_url(url) == 'vLB3e-eH2j8'


@pytest.mark.parametrize('url', [
    'https://youtube.com.evil.test/watch?v=vLB3e-eH2j8',
    'https://youtube.com@localhost/watch?v=vLB3e-eH2j8',
    'http://127.0.0.1/', 'file:///etc/passwd',
    'https://youtu.be/short', 'https://youtube.com/playlist?list=abc',
])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        service.video_id_from_url(url)


def fake_track(monkeypatch, text):
    import youtube_transcript_api
    track = SimpleNamespace(language_code='ko', is_generated=True,
                            fetch=lambda: [SimpleNamespace(text=text)])
    tracks = SimpleNamespace(find_transcript=lambda languages: track)
    monkeypatch.setattr(youtube_transcript_api.YouTubeTranscriptApi, 'list', lambda self, identity: tracks)
    monkeypatch.setattr(service.TimeoutSession, 'get', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {'title': '테스트 영상'}))


def test_extract_preserves_content_and_origin(monkeypatch):
    fake_track(monkeypatch, '첫 장면\n다음 장면')
    result = service.extract_transcript('https://youtu.be/vLB3e-eH2j8')
    assert result['text'] == '첫 장면\n다음 장면'
    assert result['url'] == 'https://www.youtube.com/watch?v=vLB3e-eH2j8'
    assert result['title'] == '테스트 영상'
    assert result['is_generated'] is True


@pytest.mark.parametrize('text', ['', 'x' * 40001])
def test_reject_empty_and_oversize(monkeypatch, text):
    fake_track(monkeypatch, text)
    with pytest.raises(ValueError):
        service.extract_transcript('https://youtu.be/vLB3e-eH2j8')


def test_blocked_error_does_not_leak_details(monkeypatch):
    import youtube_transcript_api
    def blocked(*args):
        raise youtube_transcript_api.RequestBlocked('private-details')
    monkeypatch.setattr(youtube_transcript_api.YouTubeTranscriptApi, 'list', blocked)
    with pytest.raises(RuntimeError, match='차단') as error:
        service.extract_transcript('https://youtu.be/vLB3e-eH2j8')
    assert 'private-details' not in str(error.value)
