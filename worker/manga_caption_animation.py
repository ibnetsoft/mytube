"""Opt-in AE lettering bound to the approved, scene-relative voice timing."""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any


PRESETS = {"punctuation_pop", "brush_phrase", "headline_punch", "floating_dialogue"}
SFX_TEXT_PRESETS = {"sfx_impact", "sfx_whoosh", "sfx_emphasis"}
DEFAULT_POSITIONS = {
    "punctuation_pop": [0.76, 0.54], "brush_phrase": [0.5, 0.82],
    "headline_punch": [0.5, 0.80], "floating_dialogue": [0.73, 0.52],
}


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("caption timing must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("caption timing must be finite") from exc
    if not math.isfinite(number):
        raise ValueError("caption timing must be finite")
    return number


def _tokens(value: str) -> list[str]:
    return [re.sub(r"[^\w가-힣]", "", token).casefold()
            for token in value.split() if re.sub(r"[^\w가-힣]", "", token)]


def _matches(words: list[dict[str, Any]], phrase: str) -> list[tuple[int, int]]:
    tokens = _tokens(phrase)
    spoken = [_tokens(str(word.get("text") or "")) for word in words]
    if not tokens or any(len(item) != 1 for item in spoken):
        return []
    flat = [item[0] for item in spoken]
    return [(index, index + len(tokens) - 1) for index in range(len(flat) - len(tokens) + 1)
            if flat[index:index + len(tokens)] == tokens]


def prepare_caption_animation(*, audio_path: Path | str, words: list[dict[str, Any]],
                              captions: list[dict[str, Any]], duration: float,
                              fps: int = 24) -> dict[str, Any]:
    """Resolve exact spoken phrases to word spans; ambiguity requires editorial review."""
    path = Path(audio_path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("caption animation needs the approved nonempty voice file")
    duration = _seconds(duration)
    if duration <= 0 or fps < 12 or fps > 60 or not isinstance(words, list) or not words:
        raise ValueError("caption animation needs positive duration, fps, and words")
    previous = 0.0
    for word in words:
        if not isinstance(word, dict) or not _tokens(str(word.get("text") or "")):
            raise ValueError("caption word text is required")
        start, end = _seconds(word.get("start_seconds")), _seconds(word.get("end_seconds"))
        if start < previous - 1e-6 or end <= start or end >= duration:
            raise ValueError("caption words must be ordered, nonoverlapping, and inside the AE clip")
        previous = end
    if not isinstance(captions, list) or not 1 <= len(captions) <= 4:
        raise ValueError("select one to four animated captions per AE scene")
    resolved = []
    for index, cue in enumerate(captions, 1):
        if not isinstance(cue, dict) or cue.get("preset") not in PRESETS:
            raise ValueError(f"caption {index} needs a supported preset")
        phrase = str(cue.get("text") or "").strip()
        if not phrase or len(phrase) > 42 or "\n" in phrase:
            raise ValueError(f"caption {index} needs one short spoken line")
        matches = _matches(words, phrase)
        if len(matches) != 1:
            raise ValueError(f"caption {index} text must match exactly one spoken word sequence")
        first, last = matches[0]
        accent = str(cue.get("accent_text") or "").strip()
        if cue["preset"] in {"brush_phrase", "headline_punch"} and not accent:
            raise ValueError(f"caption {index} preset needs accent_text")
        accent_at = None
        if accent:
            accent_matches = _matches(words[first:last + 1], accent)
            if len(accent_matches) != 1 or accent not in phrase:
                raise ValueError(f"caption {index} accent must match one spoken substring")
            accent_at = _seconds(words[first + accent_matches[0][0]]["start_seconds"])
        position = cue.get("position", DEFAULT_POSITIONS[cue["preset"]])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError(f"caption {index} position must be normalized x,y")
        x, y = (_seconds(value) for value in position)
        if not (.12 <= x <= .88 and .12 <= y <= .88):
            raise ValueError(f"caption {index} position must stay in the safe frame")
        start = round(_seconds(words[first]["start_seconds"]), 6)
        end = round(_seconds(words[last]["end_seconds"]), 6)
        resolved.append({"preset": cue["preset"], "text": phrase, "accent_text": accent,
                         "start_seconds": start, "end_seconds": end,
                         "accent_at_seconds": round(accent_at, 6) if accent_at is not None else None,
                         "position": [x, y]})
    return {"enabled": True, "method": "approved_voice_word_timing", "audio_path": str(path),
            "audio_sha256": _digest(path), "words": words, "captions": resolved,
            "fps": fps, "review_required": True}


def validate_caption_animation(value: Any, *, duration: float, fps: int = 24) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict) or value.get("enabled") is not True:
        return ["caption animation must be enabled or omitted"]
    errors = []
    if value.get("method") != "approved_voice_word_timing" or value.get("review_required") is not True:
        errors.append("caption animation needs reviewed word timing")
    if value.get("fps") != fps:
        errors.append("caption frame rate must match AE")
    path = Path(str(value.get("audio_path") or ""))
    if not path.is_file() or path.stat().st_size == 0:
        errors.append("approved caption voice is unavailable")
    elif _digest(path) != value.get("audio_sha256"):
        errors.append("approved caption voice changed after timing")
    try:
        requested = [{"preset": cue["preset"], "text": cue["text"],
                      "accent_text": cue.get("accent_text"), "position": cue["position"]}
                     for cue in value["captions"]]
        expected = prepare_caption_animation(audio_path=path, words=value["words"],
                                             captions=requested, duration=duration, fps=fps)
        if expected["captions"] != value["captions"]:
            errors.append("caption cues do not match the approved word timestamps")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def prepare_sfx_text_animation(*, sfx_events: list[dict[str, Any]],
                               cues: list[dict[str, Any]], duration: float,
                               fps: int = 24) -> dict[str, Any]:
    """Bind onomatopoeia to explicit scene-relative sound-effect event times."""
    duration = _seconds(duration)
    if duration <= 0 or fps < 12 or fps > 60:
        raise ValueError("SFX text needs positive duration and a supported frame rate")
    if not isinstance(sfx_events, list) or not sfx_events:
        raise ValueError("SFX text needs at least one timed sound-effect event")
    events: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(sfx_events, 1):
        if not isinstance(event, dict):
            raise ValueError(f"sound-effect event {index} must be an object")
        event_id = str(event.get("id") or "").strip()
        label = str(event.get("label") or "").strip()
        start, end = _seconds(event.get("start_seconds")), _seconds(event.get("end_seconds"))
        if not event_id or event_id in events or not label:
            raise ValueError("sound-effect events need unique ids and descriptive labels")
        if start < 0 or end <= start or end > duration:
            raise ValueError("sound-effect event times must be ordered inside the scene")
        events[event_id] = {"id": event_id, "label": label,
                            "start_seconds": round(start, 6), "end_seconds": round(end, 6)}
    if not isinstance(cues, list) or not 1 <= len(cues) <= 4:
        raise ValueError("select one to four SFX text cues per AE scene")
    resolved = []
    for index, cue in enumerate(cues, 1):
        if not isinstance(cue, dict) or cue.get("preset") not in SFX_TEXT_PRESETS:
            raise ValueError(f"SFX text cue {index} needs a supported SFX text preset")
        event_id = str(cue.get("sfx_event_id") or "").strip()
        event = events.get(event_id)
        if event is None:
            raise ValueError(f"SFX text cue {index} must reference a known sound-effect event")
        text = str(cue.get("text") or "").strip()
        if not text or len(text) > 16 or "\n" in text:
            raise ValueError(f"SFX text cue {index} needs a short, single-line text")
        offset = _seconds(cue.get("offset_seconds", 0))
        hold = _seconds(cue.get("hold_seconds", .72))
        start = event["start_seconds"] + offset
        end = start + hold
        if offset < -.5 or offset > 1 or hold < .18 or hold > 2.5 or start < 0 or end > duration:
            raise ValueError(f"SFX text cue {index} must stay within the scene and use a brief hold")
        position = cue.get("position", [.5, .5])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError(f"SFX text cue {index} position must be normalized x,y")
        x, y = (_seconds(value) for value in position)
        if not (.12 <= x <= .88 and .12 <= y <= .88):
            raise ValueError(f"SFX text cue {index} position must stay in the safe frame")
        resolved.append({"text": text, "preset": cue["preset"], "sfx_event_id": event_id,
                         "sfx_label": event["label"], "sfx_start_seconds": event["start_seconds"],
                         "sfx_end_seconds": event["end_seconds"], "offset_seconds": offset,
                         "start_seconds": round(start, 6), "end_seconds": round(end, 6),
                         "position": [x, y]})
    return {"enabled": True, "method": "scene_sfx_event_timing", "sfx_events": list(events.values()),
            "cues": resolved, "fps": fps, "review_required": True}


def validate_sfx_text_animation(value: Any, *, duration: float, fps: int = 24) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict) or value.get("enabled") is not True:
        return ["SFX text animation must be enabled or omitted"]
    if value.get("method") != "scene_sfx_event_timing" or value.get("review_required") is not True:
        return ["SFX text animation needs reviewed sound-effect event timing"]
    if value.get("fps") != fps:
        return ["SFX text frame rate must match AE"]
    try:
        requested = [{"text": cue["text"], "preset": cue["preset"],
                      "sfx_event_id": cue["sfx_event_id"], "offset_seconds": cue["offset_seconds"],
                      "hold_seconds": round(cue["end_seconds"] - cue["start_seconds"], 6),
                      "position": cue["position"]} for cue in value["cues"]]
        expected = prepare_sfx_text_animation(sfx_events=value["sfx_events"], cues=requested,
                                              duration=duration, fps=fps)
        if expected["cues"] != value["cues"]:
            return ["SFX text cues do not match the approved sound-effect event times"]
    except (KeyError, TypeError, ValueError) as exc:
        return [str(exc)]
    return []
