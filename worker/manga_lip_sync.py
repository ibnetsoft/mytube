"""Opt-in, scene-relative mouth cues for a reviewed manga dialogue close-up.

Word timestamps give a rhythmic open/close animation, not phoneme-accurate
visemes. The final mixed voice file is deliberately required so a stale TTS
revision cannot silently drive a newly rendered face.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any


MOUTH_ROLES = ("mouth_closed", "mouth_half", "mouth_open")
TEMPLATE = "dialogue_closeup"
FPS = 24


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("lip sync time must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("lip sync time must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError("lip sync time must be a finite number")
    return number


def _frame(value: float, fps: int) -> int:
    return round(value * fps)


def build_cues(words: list[dict[str, Any]], duration: float, *, fps: int = FPS) -> list[dict[str, Any]]:
    """Convert verified word spans into stepped closed/half/open animation.

    Silence stays closed. Speech is intentionally stylized and does not claim
    to recover Korean phonemes from word timestamps.
    """
    duration = _seconds(duration)
    if duration <= 0 or fps < 12 or fps > 60 or not words:
        raise ValueError("lip sync needs a positive clip, frame rate, and spoken words")
    last_end = -1
    keyframes: dict[int, str] = {0: "closed"}
    last_frame = _frame(duration, fps)
    for item in words:
        if not isinstance(item, dict):
            raise ValueError("lip sync word timing must be an object")
        start, end = _frame(_seconds(item.get("start_seconds")), fps), _frame(_seconds(item.get("end_seconds")), fps)
        if start < 0 or start < last_end or end <= start or end >= last_frame:
            raise ValueError("lip sync words must be ordered, nonoverlapping, and inside the AE clip")
        if not str(item.get("text") or "").strip():
            raise ValueError("lip sync word text is required")
        span = end - start
        if span >= 4:
            keyframes[start] = "half"
            keyframes[start + 1] = "open"
            keyframes[end - 1] = "half"
        else:
            keyframes[start] = "open" if span >= 2 else "half"
        keyframes[end] = "closed"
        last_end = end
    return [{"at_seconds": round(frame / fps, 6), "pose": pose}
            for frame, pose in sorted(keyframes.items())]


def prepare_lip_sync(*, audio_path: Path | str, words: list[dict[str, Any]],
                     speaker_key: str, mouth_box: list[float], duration: float,
                     fps: int = FPS) -> dict[str, Any]:
    """Bind one visible speaker to the exact voice bytes used by final edit."""
    path = Path(audio_path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("lip sync needs the final nonempty dialogue audio file")
    if not str(speaker_key).strip():
        raise ValueError("lip sync needs an explicit speaker character_key")
    if not isinstance(words, list) or any(
        not isinstance(item, dict) or item.get("speaker_key") != speaker_key.strip()
        for item in words
    ):
        raise ValueError("every lip sync word must identify the same visible speaker_key")
    if not isinstance(mouth_box, list) or len(mouth_box) != 4:
        raise ValueError("lip sync mouth_box must be [left, top, right, bottom]")
    box = [_seconds(value) for value in mouth_box]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1
            and .015 <= box[2] - box[0] <= .3 and .01 <= box[3] - box[1] <= .2):
        raise ValueError("lip sync mouth_box must be a small normalized face region")
    cues = build_cues(words, duration, fps=fps)
    return {
        "enabled": True, "speaker_role": "character", "speaker_key": speaker_key.strip(),
        "audio_path": str(path), "audio_sha256": _sha256(path),
        "mouth_box": box, "words": words, "cues": cues, "fps": fps,
        "method": "word_timing_3_pose", "voice_source": "approved_dialogue",
        "review_required": True,
    }


def validate_lip_sync(value: Any, *, template: str, character_key: str,
                      duration: float, fps: int = FPS) -> list[str]:
    """Reject unsupported/stale opt-ins before asset generation or AE render."""
    if value is None or (isinstance(value, dict) and value.get("enabled") is False):
        return []
    if not isinstance(value, dict) or value.get("enabled") is not True:
        return ["lip_sync must be an enabled plan or be omitted"]
    errors: list[str] = []
    if template != TEMPLATE:
        errors.append("lip sync is supported only on explicit dialogue_closeup AE scenes")
    if value.get("speaker_role") != "character" or not character_key or value.get("speaker_key") != character_key:
        errors.append("lip sync speaker_key must match the approved visible character")
    if (value.get("method") != "word_timing_3_pose"
            or value.get("voice_source") != "approved_dialogue"
            or value.get("review_required") is not True):
        errors.append("lip sync must use reviewed three-pose word timing")
    if value.get("fps") != fps:
        errors.append("lip sync cue frame rate must match the AE composition")
    box = value.get("mouth_box")
    try:
        coordinates = [_seconds(item) for item in box] if isinstance(box, list) and len(box) == 4 else []
        if not (len(coordinates) == 4 and 0 <= coordinates[0] < coordinates[2] <= 1
                and 0 <= coordinates[1] < coordinates[3] <= 1
                and .015 <= coordinates[2] - coordinates[0] <= .3
                and .01 <= coordinates[3] - coordinates[1] <= .2):
            errors.append("lip sync mouth_box must be a small normalized face region")
    except ValueError:
        errors.append("lip sync mouth_box must be finite")
    path = Path(str(value.get("audio_path") or ""))
    digest = str(value.get("audio_sha256") or "")
    if not path.is_file() or path.stat().st_size == 0:
        errors.append("lip sync final dialogue audio is unavailable")
    elif _sha256(path) != digest:
        errors.append("lip sync final dialogue audio changed after cue generation")
    try:
        words = value.get("words")
        if not isinstance(words, list) or any(
            not isinstance(item, dict) or item.get("speaker_key") != character_key
            for item in words
        ):
            errors.append("every lip sync word must identify the approved visible speaker")
        expected = build_cues(words, duration, fps=fps)
        if value.get("cues") != expected:
            errors.append("lip sync cues do not match the approved word timestamps")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors
