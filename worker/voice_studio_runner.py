"""Worker/CLI entry point for credit-linked Vertex Gemini Voice Studio."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from services.voice_studio import ElevenDialogue, VertexTTS, VoiceStudio

DEFAULT_CONFIG = {
    'presets': {
        'narrator': {'provider': 'vertex', 'voice': 'Charon', 'model': 'gemini-2.5-flash-tts', 'language': 'ko-KR',
                     'direction': 'Warm Korean oral storytelling. Calm, clear diction, restrained emotion. Read only the transcript.', 'speed': 1.0, 'pause_ms': 200},
        'narrator_soft': {'provider': 'vertex', 'voice': 'Sulafat', 'model': 'gemini-2.5-flash-tts', 'language': 'ko-KR',
                          'direction': 'Gentle, intimate Korean narration. Natural breathing and restrained emotion.', 'speed': .95, 'pause_ms': 240},
        'dialogue': {'provider': 'elevenlabs', 'voice': '4JJwo477JUAx3HV0T7n7', 'model': 'eleven_multilingual_v2', 'language': 'ko-KR',
                     'direction': '', 'speed': 1.0, 'pause_ms': 160},
        'dialogue_gemini': {'provider': 'vertex', 'voice': 'Puck', 'model': 'gemini-2.5-flash-tts', 'language': 'ko-KR',
                            'direction': 'Natural Korean character dialogue. Conversational, expressive without exaggeration.', 'speed': 1.0, 'pause_ms': 160}
    },
    'narrator_preset': 'narrator', 'dialogue_preset': 'dialogue',
    'limits': {'vertex': 30000, 'elevenlabs': 3000}
}


def segments_from_script(script: str, narrator='narrator', dialogue='dialogue') -> list[dict]:
    """Basic quotation parser; use voice_segments for explicit speaker assignment.

    Text outside paired double quotes is narration. Single quotes and inline
    parentheticals are preserved; no speculative removal of story content.
    """
    segments = []
    def append(text, preset):
        text = text.strip()
        while text:
            size = min(1200, len(text))
            if len(text) > size:
                cut = max(text.rfind('. ', 0, size), text.rfind('\n', 0, size))
                if cut < 0:
                    cut = text.rfind(' ', 0, size)
                if cut >= 0:
                    size = cut + 1
            segments.append({'id': f'segment-{len(segments)+1:04d}', 'text': text[:size].strip(), 'preset': preset})
            text = text[size:].strip()
    cursor = 0
    for match in re.finditer(r'“([^”]+)”|"([^"\n]+)"', script):
        append(script[cursor:match.start()], narrator)
        append(match.group(1) or match.group(2), dialogue)
        cursor = match.end()
    append(script[cursor:], narrator)
    return segments


def load_config(path=None):
    path = path or os.environ.get('VOICE_STUDIO_CONFIG')
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else json.loads(json.dumps(DEFAULT_CONFIG))


def generate(package: dict, directory: Path, config=None, regenerate=()):
    if config is None:
        from worker.voice_studio_library import read_choice, package_key, config_with_choice
        config = config_with_choice(load_config(), read_choice(package_key(package, directory.name)))
    segments = package.get('voice_segments') or segments_from_script(str(package.get('script') or ''), config['narrator_preset'], config['dialogue_preset'])
    vertex = VertexTTS(os.environ.get('GOOGLE_CLOUD_PROJECT', ''), os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1'))
    studio = VoiceStudio(config['presets'], {'vertex': vertex, 'elevenlabs': ElevenDialogue()}, config.get('limits'))
    return studio.run(segments, directory, regenerate)


def maybe_generate_voice_studio(package: dict, payload: dict, directory: Path):
    enabled = payload.get('generate_voice_studio', os.environ.get('VOICE_STUDIO_ENABLED', '0') == '1')
    if enabled is not True:
        return
    directory.mkdir(parents=True, exist_ok=True)
    if payload.get('voice_segments'):
        package['voice_segments'] = payload['voice_segments']
    if payload.get('topic_queue_id') is not None:
        package.setdefault('topic_queue_id', payload['topic_queue_id'])
    # Checkpoint survives a missing credential/failed generation; no need to
    # regenerate the script simply to retry its audio stage.
    (directory / 'content-package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
    package['narration_audio'] = generate(package, directory)


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cmd = sub.add_parser('presets')
    cmd.add_argument('--out', type=Path)
    cmd = sub.add_parser('run')
    cmd.add_argument('--package', required=True, type=Path)
    cmd.add_argument('--out', required=True, type=Path)
    cmd.add_argument('--config', type=Path)
    cmd.add_argument('--regenerate', action='append', default=[])
    sub.add_parser('check')
    args = parser.parse_args()
    if args.command == 'presets':
        text = json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(text, encoding='utf-8')
        else:
            print(text)
    elif args.command == 'check':
        import google.auth
        project = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
        VertexTTS(project)
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'], quota_project_id=project)
        print(json.dumps({'project': project, 'credential_type': type(credentials).__name__,
                          'billing_credit_application': 'not verified; confirm billing account and SKU eligibility in Google Cloud'}, ensure_ascii=False))
    else:
        print(json.dumps(generate(json.loads(args.package.read_text(encoding='utf-8-sig')), args.out,
                                  load_config(args.config) if args.config else None, args.regenerate), ensure_ascii=False))


if __name__ == '__main__':
    main()
