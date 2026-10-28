"""Verified visual render checkpoints; narration/captions/music are mixed only once."""
import json
from pathlib import Path

from worker.sermon_chapters import fingerprint, save
from worker.sermon_media_worker import file_hash, video_duration, concatenate


def groups(durations, seconds=900, transitions=None):
    start, elapsed = 0, 0.
    for index, duration in enumerate(durations):
        elapsed += float(duration)
        # A crossfade belongs to both adjacent scenes: never split that boundary.
        next_transition = str((transitions or [])[index + 1]).lower() if index + 1 < len(transitions or []) else 'none'
        if elapsed >= seconds and next_transition in ('none', '', 'cut'):
            yield start, index + 1
            start, elapsed = index + 1, 0.
    if start < len(durations):
        yield start, len(durations)


def render_visual_chapters(directory, images, durations, settings, render, *, seconds=900,
                           transitions=None, notify=lambda *_: None):
    root = Path(directory) / 'visual-chapters'
    root.mkdir(parents=True, exist_ok=True)
    sources = [file_hash(path) for path in images]
    outputs, entries, start_time = [], [], 0.
    for number, (start, end) in enumerate(groups(durations, seconds, transitions), 1):
        target = root / f'chapter-{number:03d}.mp4'
        receipt = target.with_suffix('.json')
        identity = fingerprint({'profile': 'chapter_visual/v1', 'sources': sources[start:end],
            'durations': durations[start:end], 'start_index': start, 'start_time': start_time, 'settings': settings})
        saved = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else {}
        duration = sum(float(value) for value in durations[start:end])
        reusable = (saved.get('fingerprint') == identity and target.is_file()
                    and saved.get('sha256') == file_hash(target))
        if reusable:
            actual = video_duration(target)
            if abs(actual - duration) > .25:
                reusable = False
        if not reusable:
            notify(35 + round(45 * start / len(images)), f'장편 영상 {number}구간 · 렌더링')
            partial = root / f'chapter-{number:03d}.partial.mp4'
            render(start, end, start_time, duration, partial)
            actual = video_duration(partial)
            if abs(actual - duration) > .25:
                raise ValueError('장편 렌더 구간의 실제 길이가 씬 시간과 다릅니다. 완료 구간은 보존됩니다.')
            partial.replace(target)
            saved = {'fingerprint': identity, 'sha256': file_hash(target), 'duration_seconds': actual}
            save(receipt, saved)
        else:
            notify(35 + round(45 * start / len(images)), f'장편 영상 {number}구간 · 완료 파일 재사용')
        outputs.append(target)
        entries.append({**saved, 'scene_start_index': start, 'scene_end_index': end})
        start_time += duration
    combined = root / 'combined.mp4'
    combined_receipt = root / 'combined.json'
    signature = fingerprint(entries)
    prior = json.loads(combined_receipt.read_text(encoding='utf-8')) if combined_receipt.exists() else {}
    if not (prior.get('fingerprint') == signature and combined.is_file() and prior.get('sha256') == file_hash(combined)):
        partial = root / 'combined.partial.mp4'
        concatenate(outputs, partial)
        actual = video_duration(partial)
        if abs(actual - sum(durations)) > max(.25, len(outputs) / 24):
            raise ValueError('장편 영상 결합 후 길이 검증에 실패했습니다. 완료 구간은 보존됩니다.')
        partial.replace(combined)
        save(combined_receipt, {'fingerprint': signature, 'sha256': file_hash(combined), 'chapters': entries})
    return str(combined)
