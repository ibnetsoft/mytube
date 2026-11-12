"""Isolated local 2D motion prototype. No network calls or production integration.

Input: a JSON manifest describing a source image, narration, manually prepared
full-canvas RGBA mouth/eye sprites and an optional full-canvas hair layer.
Run: python worker/motion2d_mvp.py manifest.json output.mp4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image

FPS = 24
FRAMES = 96
DURATION = FRAMES / FPS


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_rgba(path: Path, size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        if image.size != size:
            raise ValueError(f'Layer dimensions differ from source: {path}')
        return np.asarray(image.convert('RGBA')).copy()


def composite(base: np.ndarray, layer: np.ndarray) -> np.ndarray:
    alpha = layer[..., 3:4].astype(np.float32) / 255.0
    return np.clip(layer[..., :3] * alpha + base * (1 - alpha), 0, 255).astype(np.uint8)


def pose_at(cues: list[dict], t: float) -> str:
    for cue in cues:
        if cue['start'] <= t < cue['end']:
            return cue['pose']
    return 'closed'


def rhubarb_cues(executable: str, audio: Path, start: float, ffmpeg: str) -> list[dict]:
    """Analyze the exact four-second audio interval with the local CLI."""
    import tempfile
    binary = shutil.which(executable) or (str(Path(executable).resolve()) if Path(executable).is_file() else None)
    if not binary:
        raise ValueError('Rhubarb executable not found; install it or provide mouth_cues')
    if not binary.isascii():
        raise ValueError('Rhubarb and its bundled files must be installed in an ASCII-only path on Windows')
    with tempfile.TemporaryDirectory(prefix='air-motion2d-') as tmp:
        if not tmp.isascii():
            raise ValueError('Rhubarb needs an ASCII-only temporary directory; configure TEMP and TMP')
        wav = Path(tmp) / 'voice.wav'
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-ss', str(start), '-i', str(audio), '-t', str(DURATION), '-ac', '1', '-ar', '16000', str(wav)], check=True, timeout=120)
        result = subprocess.run([binary, '-r', 'phonetic', '-f', 'json', str(wav)], capture_output=True, check=True, timeout=120)
        payload = json.loads(result.stdout.decode('utf-8-sig'))
    # Rhubarb's English-derived shapes are an approximation for Korean.
    mapping = {'A': 'closed', 'B': 'half', 'C': 'half', 'D': 'open', 'E': 'open', 'F': 'open', 'G': 'half', 'H': 'open', 'X': 'closed'}
    return [{'start': max(0., float(c['start'])), 'end': min(DURATION, float(c['end'])), 'pose': mapping[c['value']]} for c in payload['mouthCues'] if float(c['start']) < DURATION and float(c['end']) > 0]


def hair_at(layer: np.ndarray, t: float, amplitude: float, anchor_y: float, period: float) -> np.ndarray:
    h, w = layer.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    weight = np.clip((y - anchor_y * h) / max(1.0, h * (1 - anchor_y)), 0, 1)
    dx = amplitude * weight * np.sin(2 * math.pi * t / period)
    return cv2.remap(layer, (x - dx).astype(np.float32), y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def render(manifest_path: Path, output: Path) -> dict:
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    root = manifest_path.parent
    def path(value):
        p = Path(value)
        return p if p.is_absolute() else root / p
    source, audio = path(data['source']), path(data['audio'])
    if output.exists():
        raise ValueError('Output already exists; choose a new path')
    with Image.open(source) as image:
        size = image.size
        base = np.asarray(image.convert('RGB')).copy()
    if size[0] % 2 or size[1] % 2:
        raise ValueError('Source dimensions must be even for yuv420p')
    mouths = {name: load_rgba(path(filename), size) for name, filename in data['mouths'].items()}
    if 'closed' not in mouths:
        raise ValueError('A closed mouth sprite is required')
    blink = load_rgba(path(data['blink']['sprite']), size)
    blink_start, blink_end = float(data['blink']['start']), float(data['blink']['end'])
    if not 0 <= blink_start < blink_end <= DURATION:
        raise ValueError('Blink must fall inside the clip')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    start = float(data.get('audio_start', 0))
    if not math.isfinite(start) or start < 0:
        raise ValueError('Invalid audio start')
    output.parent.mkdir(parents=True, exist_ok=True)
    rhubarb = data.get('rhubarb_executable')
    if rhubarb and 'mouth_cues' in data:
        raise ValueError('Provide mouth_cues or rhubarb_executable, not both')
    cues = rhubarb_cues(rhubarb, audio, start, ffmpeg) if rhubarb else data['mouth_cues']
    last = 0.0
    for cue in cues:
        cue_start, end = float(cue['start']), float(cue['end'])
        if not last <= cue_start < end <= DURATION or cue['pose'] not in mouths:
            raise ValueError('Mouth cues must be ordered, non-overlapping, in range and use known poses')
        last = end
    hair_config = data.get('hair')
    hair = load_rgba(path(hair_config['sprite']), size) if hair_config else None
    if hair_config and (not 0 <= float(hair_config['anchor_y']) < 1 or not 0 <= float(hair_config['amplitude_px']) <= 50 or float(hair_config['period']) <= 0):
        raise ValueError('Invalid hair settings')
    # Decode first so insufficient source audio cannot silently produce a short result.
    pcm = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(start), '-i', str(audio), '-t', str(DURATION), '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'], capture_output=True, check=True, timeout=120).stdout
    if len(pcm) < 48000 * 2 * DURATION:
        raise ValueError('Narration does not contain four full seconds at the requested offset')
    temporary = output.with_name(output.stem + '.motion2d-partial.mp4')
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', str(FPS), '-i', 'pipe:0', '-ss', str(start), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0', '-frames:v', str(FRAMES), '-t', str(DURATION), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(temporary)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for n in range(FRAMES):
            t = n / FPS
            frame = composite(base, mouths[pose_at(cues, t)])
            if blink_start <= t < blink_end:
                frame = composite(frame, blink)
            if hair is not None:
                frame = composite(frame, hair_at(hair, t, float(hair_config['amplitude_px']), float(hair_config['anchor_y']), float(hair_config['period'])))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        stderr = proc.stderr.read().decode('utf-8', 'replace')
        if proc.wait(timeout=120):
            raise RuntimeError(f'FFmpeg failed: {stderr}')
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(temporary), '-f', 'null', '-'], check=True, timeout=120)
        temporary.replace(output)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        temporary.unlink(missing_ok=True)
    return {'frames': FRAMES, 'fps': FPS, 'duration': DURATION, 'source_sha256': sha256(source), 'audio_sha256': sha256(audio), 'output_sha256': sha256(output), 'encoder': 'libx264', 'mouth_timing': 'rhubarb phonetic' if rhubarb else 'provided cues'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(render(args.manifest, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
