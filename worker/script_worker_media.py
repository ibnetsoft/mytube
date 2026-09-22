"""Summarize saved media links, without treating prompts as generated images."""
from urllib.parse import urlsplit


def obj(value):
    return value if isinstance(value, dict) else {}


def image_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def thumbnail(*sources):
    sources = [obj(s) for s in sources]
    for key, label in [('thumbnail_url', '썸네일'), ('thumbnail_final_url', '썸네일'),
                       ('thumbnail_bg_url', '썸네일 배경')]:
        for source in sources:
            url = image_url(source.get(key))
            if url:
                return {'url': url, 'label': label}
    return {'url': '', 'label': '썸네일 없음'}


def state_summary(count, total, states, *, available=True):
    states = {str(s or '').lower() for s in states}
    if not available:
        status = 'unknown'
    elif states & {'running', 'generating', 'processing', 'in_progress', 'pending', 'queued'}:
        status = 'running'
    elif states & {'failed', 'error'}:
        status = 'failed'
    elif count and count >= total:
        status = 'ready'
    elif count:
        status = 'partial'
    elif states & {'ready', 'completed'}:
        status = 'unverified'
    else:
        status = 'not_started'
    return {'status': status, 'count': count, 'total': total}


def media_summary(payload, progress=None, registry=None, *, registry_available=True):
    payload, progress = obj(payload), obj(progress)
    structure = obj(payload.get('structure') or payload.get('pregenerated_structure'))
    anchors = obj(payload.get('character_anchors') or structure.get('character_anchors') or progress.get('character_anchors'))
    main = obj(anchors.get('main_character') or structure.get('main_character') or payload.get('main_character') or progress.get('main_character'))
    supporting = anchors.get('supporting_characters') or structure.get('supporting_characters') or payload.get('supporting_characters') or progress.get('supporting_characters') or []
    planned = ([main] if main else []) + ([s for s in supporting if isinstance(s, dict)] if isinstance(supporting, list) else [])
    registry = [r for r in (registry or []) if isinstance(r, dict)]
    unique = {}
    for i, char in enumerate(planned):
        unique[str(char.get('character_key') or char.get('name') or i)] = char
    planned = list(unique.values())
    characters = planned or registry
    count = 0
    for char in characters:
        matches = [r for r in registry if any(char.get(k) and char.get(k) == r.get(k) for k in ('character_key', 'name'))]
        count += bool(image_url(char.get('image_url')) or any(image_url(r.get('image_url')) for r in matches))
    char_states = [structure.get('character_reference_status'), obj(anchors.get('character_image_generation')).get('status')]
    char_states.extend(c.get('image_generation_status') for c in characters)
    scenes = [s for s in structure.get('scenes', []) if isinstance(s, dict)]
    image_count = sum(bool(image_url(s.get('image_url'))) for s in scenes)
    image_states = [progress.get('image_generation_status'), structure.get('image_generation_status')]
    image_states.extend(s.get('image_generation_status') for s in scenes)
    return {'thumbnail': thumbnail(payload, progress, structure, obj(payload.get('render_settings'))),
            'characters': state_summary(count, len(characters), char_states, available=registry_available or bool(count)),
            'images': state_summary(image_count, len(scenes), image_states),
            'basis': '저장된 이미지 링크 기준'}


def unknown_media(reason='연결 자료 없음'):
    return {'thumbnail': {'url': '', 'label': '썸네일 미확인'},
            'characters': state_summary(0, 0, [], available=False),
            'images': state_summary(0, 0, [], available=False), 'basis': reason}
