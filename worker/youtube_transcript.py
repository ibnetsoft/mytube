"""Read public YouTube captions for the local reference library."""
import re
from urllib.parse import urlsplit, parse_qs

import requests


YOUTUBE_HOSTS = {
    'youtu.be', 'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'music.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com',
}


def is_youtube_url(value):
    try:
        return urlsplit(str(value).strip()).hostname in YOUTUBE_HOSTS
    except ValueError:
        return False


def video_id_from_url(value):
    try:
        url = urlsplit(value.strip())
        if (url.scheme not in ('http', 'https') or url.username or url.password
                or url.port or url.hostname not in YOUTUBE_HOSTS):
            raise ValueError()
        parts = url.path.strip('/').split('/')
        if url.hostname == 'youtu.be' and len(parts) == 1:
            identity = parts[0]
        elif url.hostname in YOUTUBE_HOSTS - {'youtu.be'}:
            if url.path == '/watch':
                identity = parse_qs(url.query).get('v', [''])[0]
            elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
                identity = parts[1]
            else:
                raise ValueError()
        else:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', identity):
            raise ValueError()
        return identity
    except ValueError:
        raise ValueError('올바른 YouTube 영상 URL을 입력하세요.') from None


class TimeoutSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault('timeout', (5, 15))
        return super().request(*args, **kwargs)


def extract_transcript(url, preferred_language='auto'):
    identity = video_id_from_url(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
    except ImportError:
        raise RuntimeError('자막 모듈이 없습니다. 워커 Python에 pip install "youtube-transcript-api>=1.2,<2"로 설치하세요.') from None
    canonical = 'https://www.youtube.com/watch?v=' + identity
    try:
        with TimeoutSession() as session:
            tracks = YouTubeTranscriptApi(http_client=session).list(identity)
            available = list(tracks)
            if not available:
                track = None
            elif preferred_language and preferred_language != 'auto':
                try:
                    track = tracks.find_transcript([preferred_language])
                except NoTranscriptFound:
                    languages = ', '.join(dict.fromkeys(item.language_code for item in available))
                    raise ValueError(
                        f'선택한 자막 언어({preferred_language})가 없습니다. 사용 가능 언어: {languages}'
                    ) from None
            else:
                # Prefer a human-authored track while preserving the video's own
                # language order. Fall back to YouTube's generated captions.
                track = next((item for item in available if not item.is_generated), available[0])
            if track is None:
                raise ValueError('사용 가능한 자막이 없습니다. 자막을 직접 붙여넣거나 음성 전사가 필요합니다.')
            transcript = track.fetch()
            text = '\n'.join(item.text for item in transcript if item.text.strip())
            if not text.strip():
                raise ValueError('자막 내용이 비어 있습니다.')
            if len(text) > 40000:
                raise ValueError('자막이 자료당 40,000자 제한을 초과합니다. 원문을 나눠 직접 등록하세요. 자동으로 자르지 않았습니다.')
            title = 'YouTube ' + identity
            try:
                response = session.get('https://www.youtube.com/oembed', params={'url': canonical, 'format': 'json'}, timeout=5)
                response.raise_for_status()
                title = str(response.json().get('title') or title)[:200]
            except (requests.RequestException, ValueError):
                pass
            return {'title': title, 'text': text, 'url': canonical,
                    'video_id': identity, 'language': track.language_code,
                    'language_name': track.language, 'is_generated': track.is_generated,
                    'available_languages': [
                        {'code': item.language_code, 'name': item.language,
                         'is_generated': item.is_generated}
                        for item in available
                    ]}
    except ValueError:
        raise
    except Exception as exc:
        name = type(exc).__name__
        if name in ('TranscriptsDisabled', 'NoTranscriptFound'):
            message = '사용 가능한 자막이 없습니다. 자막을 직접 붙여넣거나 음성 전사가 필요합니다.'
        elif name in ('RequestBlocked', 'IpBlocked'):
            message = 'YouTube가 자막 요청을 차단했습니다. 잠시 후 다시 시도하거나 자막을 직접 붙여넣으세요.'
        elif name in ('VideoUnavailable', 'VideoUnplayable', 'AgeRestricted'):
            message = '접근할 수 없는 영상입니다. 비공개·삭제·연령 제한 여부를 확인하세요.'
        else:
            message = '자막을 가져오지 못했습니다. 네트워크를 확인하거나 자막을 직접 붙여넣으세요.'
        raise RuntimeError(message) from None
