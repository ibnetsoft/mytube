"""Atomic, input-scoped local checkpoints for long Adobe media jobs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()[:16]


class Checkpoint:
    def __init__(self, path: Path, identity: str):
        self.path = path
        self.identity = identity
        self.data: dict[str, Any] = {'identity': identity, 'stages': {}, 'updated_at': time.time()}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(existing, dict) and existing.get('identity') == identity:
                    self.data = existing
            except (OSError, ValueError):
                pass

    def get(self, stage: str) -> Any:
        return self.data.get('stages', {}).get(stage)

    def mark(self, stage: str, value: Any = True) -> None:
        self.data.setdefault('stages', {})[stage] = value
        self.data['updated_at'] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, self.path)


def valid_file(path: Path, minimum_bytes: int = 1024) -> bool:
    return path.is_file() and path.stat().st_size >= minimum_bytes


@lru_cache(maxsize=1024)
def _mp4_duration_with_first_frame(path: str, size: int, mtime_ns: int) -> float | None:
    try:
        import imageio_ffmpeg
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", path,
             "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=60,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if result.returncode or not match or not re.search(r"frame=\s*[1-9]", result.stderr):
            return None
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if duration > 1.5:
            end = subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-sseof", "-1", "-i", path,
                 "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"],
                capture_output=True, text=True, errors="replace", timeout=60,
            )
            if end.returncode or not re.search(r"frame=\s*[1-9]", end.stderr):
                return None
        return duration
    except (ImportError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return None


def valid_mp4(path: Path, minimum_seconds: float = 0.5) -> bool:
    if not valid_file(path):
        return False
    stat = path.stat()
    duration = _mp4_duration_with_first_frame(str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    return duration is not None and duration >= minimum_seconds


def verified_local_mp4(value: Any, root: Path, minimum_seconds: float = 0.5) -> Path | None:
    """Accept only a playable MP4 inside the worker-owned media directory."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        resolved_root = root.resolve()
        candidate = Path(value).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return candidate if valid_mp4(candidate, minimum_seconds) else None
