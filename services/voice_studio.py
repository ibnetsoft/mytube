"""Voice Studio: official Vertex Gemini TTS, optional ElevenLabs, resumable audio.

No browser login or private Gemini endpoints. Character ceilings bound work,
not Cloud bills: billing credits/other project usage must be checked in Cloud.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import wave

from worker.cowork_narration import ffmpeg_path, wave_info

VOICES = frozenset('Zephyr Puck Charon Kore Fenrir Leda Orus Aoede Callirrhoe Autonoe Enceladus Iapetus Umbriel Algieba Despina Erinome Algenib Rasalgethi Laomedeia Achernar Alnilam Schedar Gacrux Pulcherrima Achird Zubenelgenubi Vindemiatrix Sadachbia Sadaltager Sulafat'.split())
MODELS = frozenset({'gemini-2.5-flash-tts', 'gemini-2.5-pro-tts'})


@dataclass(frozen=True)
class VoicePreset:
    provider: str = 'vertex'
    voice: str = 'Charon'
    model: str = 'gemini-2.5-flash-tts'
    language: str = 'ko-KR'
    direction: str = 'Read naturally and clearly, with a warm, restrained storytelling tone.'
    speed: float = 1.0
    pause_ms: int = 180
    stability: float = 0.62
    similarity_boost: float = 0.82
    style: float = 0.18

    def validate(self):
        if self.provider not in {'vertex', 'elevenlabs'}:
            raise ValueError('Unknown voice provider')
        if self.provider == 'vertex' and (self.voice not in VOICES or self.model not in MODELS):
            raise ValueError('Unsupported Gemini voice/model')
        if self.provider == 'elevenlabs' and not re.fullmatch(r'[A-Za-z0-9_-]+', self.voice):
            raise ValueError('Invalid ElevenLabs voice ID')
        if not self.voice or not .7 <= self.speed <= 1.3 or type(self.pause_ms) is not int or not 0 <= self.pause_ms <= 2000:
            raise ValueError('Invalid voice, speed or pause')
        if not 0 <= self.stability <= 1 or not 0 <= self.similarity_boost <= 1 or not 0 <= self.style <= 1:
            raise ValueError('Invalid ElevenLabs voice settings')
        if len(self.direction) > 1500 or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', self.language):
            raise ValueError('Invalid language or direction')


def atomic_json(path: Path, data: dict):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows scanners can briefly hold the manifest between checkpoints.
    # Retry the atomic rename only, never the billable synthesis request.
    for attempt in range(6):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if os.name != 'nt' or attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


@contextmanager
def job_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.voice.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def pcm_response_wav(payload: dict) -> bytes:
    candidates = payload.get('candidates') or []
    if not candidates or candidates[0].get('finishReason') != 'STOP':
        raise ValueError('Gemini audio is missing, blocked, or truncated')
    chunks = []
    for part in candidates[0].get('content', {}).get('parts', []):
        inline = part.get('inlineData')
        if not inline:
            continue
        mime = inline.get('mimeType', '').lower()
        if not mime.startswith(('audio/l16', 'audio/pcm')):
            raise ValueError('Unexpected Gemini audio format: ' + mime)
        rate = re.search(r'rate=(\d+)', mime)
        if rate and int(rate.group(1)) != 24000:
            raise ValueError('Unexpected PCM sample rate')
        chunks.append(base64.b64decode(inline.get('data', ''), validate=True))
    pcm = b''.join(chunks)
    if not pcm or len(pcm) % 2:
        raise ValueError('Empty or incomplete PCM audio')
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(pcm)
    return output.getvalue()


class VertexTTS:
    def __init__(self, project: str, location: str = 'us-central1', session=None):
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', project or ''):
            raise ValueError('Set GOOGLE_CLOUD_PROJECT to the credit-linked project ID')
        if not re.fullmatch(r'[a-z]+(?:-[a-z]+\d)?', location):
            raise ValueError('Invalid Vertex location')
        self.project, self.location, self.session = project, location, session

    def synthesize(self, text: str, preset: VoicePreset, direction: str):
        preset.validate()
        if not text.strip() or len(text) > 1200:
            raise ValueError('Gemini segment must contain 1–1200 characters')
        if self.session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'], quota_project_id=self.project)
            self.session = AuthorizedSession(credentials)
        host = 'aiplatform.googleapis.com' if self.location == 'global' else self.location + '-aiplatform.googleapis.com'
        url = f'https://{host}/v1beta1/projects/{self.project}/locations/{self.location}/publishers/google/models/{preset.model}:generateContent'
        prompt = f'Read only the transcript exactly as written. Do not read the direction labels.\nLanguage: {preset.language}\nDirection: {preset.direction}\nScene direction: {direction}\nTranscript:\n{text}'
        body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {
                    'languageCode': preset.language,
                    'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': preset.voice}}}}}
        # No automatic retries: a timeout can still represent a billable request.
        response = self.session.post(url, json=body, headers={'x-goog-user-project': self.project}, timeout=180)
        if not response.ok:
            raise RuntimeError(f'Vertex TTS HTTP {response.status_code}; check API enablement, project billing, IAM and quota')
        payload = response.json()
        return pcm_response_wav(payload), payload.get('usageMetadata', {})


class ElevenDialogue:
    def synthesize(self, text: str, preset: VoicePreset, direction: str, *, previous_text='', next_text=''):
        import requests
        key = os.environ.get('ELEVENLABS_API_KEY', '')
        if not key:
            raise ValueError('ELEVENLABS_API_KEY is required for dialogue')
        if direction:
            raise ValueError('ElevenLabs scene direction is not supported by this adapter; use transcript audio tags appropriate to the configured model')
        # Explicit provider only. Never send Gemini narration to ElevenLabs.
        response = requests.post('https://api.elevenlabs.io/v1/text-to-speech/' + preset.voice + '/with-timestamps',
                                 headers={'xi-api-key': key}, params={'output_format': 'mp3_44100_128'},
                                 json={
                                     'text': text,
                                     'model_id': preset.model,
                                     'previous_text': previous_text or None,
                                     'next_text': next_text or None,
                                     'voice_settings': {
                                         'stability': preset.stability,
                                         'similarity_boost': preset.similarity_boost,
                                         'style': preset.style,
                                         'use_speaker_boost': True,
                                         'speed': min(1.2, preset.speed),
                                     },
                                 }, timeout=180)
        if not response.ok:
            raise RuntimeError(f'ElevenLabs HTTP {response.status_code}')
        from services.speech_alignment import validate_alignment
        payload = response.json()
        alignment = validate_alignment(text, payload.get('alignment'))
        return base64.b64decode(payload['audio_base64'], validate=True), {
            'request_id': response.headers.get('request-id'), 'native_speed': min(1.2, preset.speed),
            'alignment': alignment,
        }


def normalize_audio(source: Path, target: Path, speed: float):
    # One-pass loudnorm target; verify final loudness for publication requirements.
    temp = target.with_suffix('.part.wav')
    try:
        filters = 'loudnorm=I=-18:TP=-2:LRA=7'
        if abs(float(speed or 1.0) - 1.0) > 0.01:
            filters = f'atempo={speed},{filters}'
        result = subprocess.run([ffmpeg_path(), '-nostdin', '-v', 'error', '-xerror', '-y', '-i', str(source),
                                 '-vn', '-af', filters,
                                 '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(temp)],
                                capture_output=True, timeout=180, check=False)
        if result.returncode:
            raise RuntimeError('Voice audio decode/normalization failed')
        wave_info(temp)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


class VoiceStudio:
    def __init__(self, presets: dict, providers: dict, limits: dict | None = None):
        self.presets = {name: VoicePreset(**value) for name, value in presets.items()}
        for preset in self.presets.values():
            preset.validate()
        self.providers = providers
        self.limits = limits or {'vertex': 30000, 'elevenlabs': 3000}
        if any(not isinstance(value, int) or value < 0 for value in self.limits.values()):
            raise ValueError('Provider character limits must be nonnegative integers')

    def run(self, segments: list[dict], directory: Path, regenerate=()):
        directory = directory.resolve()
        if not isinstance(segments, list) or any(not isinstance(segment, dict) for segment in segments):
            raise ValueError('Segments must be a list of objects')
        ids = [segment.get('id') for segment in segments]
        if not segments or any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', i) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Unique, safe segment IDs are required')
        if set(regenerate) - set(ids):
            raise ValueError('Unknown regeneration segment')
        plan = []
        for segment in segments:
            preset = self.presets[segment['preset']]
            text = segment['text']
            if not isinstance(text, str) or not text.strip() or len(text) > 1200:
                raise ValueError('Split segments at sentence boundaries to 1–1200 characters')
            direction = segment.get('direction', '')
            if not isinstance(direction, str) or len(direction) > 1500:
                raise ValueError('Scene direction exceeds limit')
            if preset.provider not in self.providers:
                raise ValueError('Provider is not configured')
            if preset.provider == 'elevenlabs' and (direction or preset.direction):
                raise ValueError('Freeform direction is supported for Gemini; ElevenLabs adapter requires an empty direction')
            pause_ms = segment.get('pause_ms', preset.pause_ms)
            if type(pause_ms) is not int or not 0 <= pause_ms <= 2000:
                raise ValueError('Invalid segment pause')
            context = {key: segment.get(key, '') for key in ('previous_text', 'next_text')}
            if any(not isinstance(value, str) or len(value) > 1200 for value in context.values()):
                raise ValueError('Invalid speech context')
            signature = hashlib.sha256(json.dumps({'text': text, 'preset': asdict(preset), 'direction': direction, 'context': context, 'processing': 3}, sort_keys=True).encode()).hexdigest()
            plan.append((segment, preset, signature))
        with job_lock(directory):
            path = directory / 'voice-studio.json'
            state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema': 'voice-studio/v1', 'attempts': [], 'segments': {}}
            state['status'] = 'generating'
            state.pop('error', None)
            state.pop('output', None)
            state.pop('timeline', None)
            atomic_json(path, state)
            try:
                for segment, preset, signature in plan:
                    sid = segment['id']
                    previous = state['segments'].get(sid, {})
                    cached = directory / previous.get('file', '__missing__')
                    if (sid not in regenerate and previous.get('signature') == signature and cached.is_file()
                            and cached.parent == directory and hashlib.sha256(cached.read_bytes()).hexdigest() == previous.get('sha256')):
                        continue
                    # Count reserved attempts even when response delivery failed.
                    charged_chars = len(segment['text']) + (len(preset.direction) + len(segment.get('direction', '')) if preset.provider == 'vertex' else 0)
                    used = sum(a['chars'] for a in state['attempts'] if a['provider'] == preset.provider)
                    if used + charged_chars > self.limits.get(preset.provider, 0):
                        raise RuntimeError(f'{preset.provider} job character limit reached; no request sent')
                    attempt = {'segment': sid, 'provider': preset.provider, 'chars': charged_chars, 'status': 'reserved', 'at': time.time()}
                    state['attempts'].append(attempt)
                    atomic_json(path, state)
                    provider = self.providers[preset.provider]
                    context = ({key: segment.get(key, '') for key in ('previous_text', 'next_text')}
                               if isinstance(provider, ElevenDialogue) else {})
                    audio, usage = provider.synthesize(segment['text'], preset, segment.get('direction', ''), **context)
                    attempt.update(status='received', usage=usage)
                    atomic_json(path, state)
                    version = uuid.uuid4().hex[:10]
                    raw = directory / f'{sid}-{version}.source'
                    output = directory / f'{sid}-{version}.wav'
                    raw.write_bytes(audio)
                    # ElevenLabs applies speed during synthesis; never stretch it twice.
                    native_speed = float(usage.get('native_speed') or 1.0)
                    normalize_audio(raw, output, preset.speed / native_speed)
                    state['segments'][sid] = {'signature': signature, 'file': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                              'preset': segment['preset'], 'provider': preset.provider,
                                              'voice': preset.voice, 'model': preset.model, 'speed': preset.speed,
                                              'usage': usage, **wave_info(output)}
                    atomic_json(path, state)
                timeline, frames = [], 0
                mixed = directory / ('mixed-' + uuid.uuid4().hex[:10] + '.wav')
                with wave.open(str(mixed), 'wb') as out:
                    out.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                    for index, (segment, preset, _) in enumerate(plan):
                        entry = state['segments'][segment['id']]
                        start = frames
                        with wave.open(str(directory / entry['file']), 'rb') as source:
                            while chunk := source.readframes(48000):
                                out.writeframesraw(chunk)
                                frames += len(chunk) // 2
                        timeline.append({'id': segment['id'], 'text': segment['text'], 'preset': segment['preset'], 'start': start / 48000, 'end': frames / 48000,
                                         'alignment': entry.get('usage', {}).get('alignment'),
                                         'alignment_speed_ratio': preset.speed / float(entry.get('usage', {}).get('native_speed') or 1.0)})
                        if index != len(plan) - 1:
                            silence_frames = segment.get('pause_ms', preset.pause_ms) * 48
                            out.writeframesraw(b'\0\0' * silence_frames)
                            frames += silence_frames
                state.update(status='complete', output=mixed.name, timeline=timeline, duration_seconds=frames / 48000)
                atomic_json(path, state)
                return {'audio_path': str(mixed), 'manifest_path': str(path), 'timeline': timeline, 'duration_seconds': frames / 48000}
            except Exception as exc:
                state.update(status='failed', error=str(exc))
                atomic_json(path, state)
                raise
