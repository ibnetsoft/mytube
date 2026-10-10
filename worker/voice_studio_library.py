"""Persistent voice choices shared by dashboard and resident worker."""
import hashlib
import json
import os
from pathlib import Path

from services.voice_studio import VOICES, VoicePreset, atomic_json

FEMALE = set('Achernar Aoede Autonoe Callirrhoe Despina Erinome Gacrux Kore Laomedeia Leda Pulcherrima Sulafat Vindemiatrix Zephyr'.split())
SAMPLE_TEXT = '조용한 아침, 창문 사이로 햇살이 들어왔다. 그는 천천히 문을 열고, 새로운 하루를 맞이했다.'


def library_root():
    from worker.worker_config import CONFIG_DIR
    return CONFIG_DIR / 'voice_studio'


def choice_path(key):
    return library_root() / (hashlib.sha256(key.encode()).hexdigest() + '.json')


def validate_choice(value):
    if not isinstance(value, dict):
        raise ValueError('목소리 설정이 필요합니다.')
    preset = VoicePreset(voice=value.get('voice', 'Charon'), direction=value.get('direction', ''),
                         speed=float(value.get('speed', 1)), pause_ms=200)
    preset.validate()
    mode = value.get('dialogue_mode', 'elevenlabs')
    if mode not in ('elevenlabs', 'narrator'):
        raise ValueError('대사 처리 방식을 확인해 주세요.')
    return {'voice': preset.voice, 'direction': preset.direction, 'speed': preset.speed, 'dialogue_mode': mode}


def read_choice(key):
    path = choice_path(key)
    if path.exists():
        return validate_choice(json.loads(path.read_text(encoding='utf-8')))
    return None


def save_choice(key, value):
    value = validate_choice(value)
    path = choice_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic unique writer: independent browser tabs cannot share a temp file.
    import uuid
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)
    return value


def config_with_choice(config, choice):
    config = json.loads(json.dumps(config))
    if choice:
        choice = validate_choice(choice)
        config['presets'][config['narrator_preset']].update(
            voice=choice['voice'], direction=choice['direction'], speed=choice['speed'])
        if choice['dialogue_mode'] == 'narrator':
            config['dialogue_preset'] = config['narrator_preset']
    return config


def package_key(package, fallback=''):
    topic = package.get('topic_queue_id')
    return 'topic_' + str(topic) if topic is not None and str(topic) else str(package.get('job_id') or fallback)


def catalog():
    return [{'name': name, 'gender': '여성' if name in FEMALE else '남성'} for name in sorted(VOICES)]
