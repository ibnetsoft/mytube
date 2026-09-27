"""Canonical longform scene durations shared by script-generation workers."""
from __future__ import annotations

from typing import Any


PACING_BANDS: tuple[tuple[int | None, int], ...] = (
    (18, 5),   # scenes 1-18
    (6, 7),    # scenes 19-24
    (6, 10),   # scenes 25-30
    (15, 12),  # scenes 31-45
    (15, 15),  # scenes 46-60
    (None, 18),  # scene 61 onward
)


def pacing_schedule(target_duration_seconds: Any) -> list[dict[str, int]]:
    """Return scene-relative durations summing exactly to the requested runtime."""
    try:
        remaining = max(1, int(float(target_duration_seconds)))
    except (TypeError, ValueError):
        return []
    schedule: list[dict[str, int]] = []
    number = 1
    for scene_limit, seconds in PACING_BANDS:
        used = 0
        while remaining > 0 and (scene_limit is None or used < scene_limit):
            duration = min(seconds, remaining)
            schedule.append({"scene_number": number, "duration_seconds": duration})
            number += 1
            used += 1
            remaining -= duration
        if remaining <= 0:
            break
    return schedule


def format_pacing_bands(schedule: list[dict[str, int]]) -> str:
    """Compactly describe consecutive equal-duration scene ranges for prompts."""
    if not schedule:
        return ""
    groups: list[str] = []
    start = previous = int(schedule[0]["scene_number"])
    duration = int(schedule[0]["duration_seconds"])
    for item in schedule[1:]:
        number = int(item["scene_number"])
        seconds = int(item["duration_seconds"])
        if number == previous + 1 and seconds == duration:
            previous = number
            continue
        label = str(start) if start == previous else f"{start}-{previous}"
        groups.append(f"{label}: {duration}s")
        start = previous = number
        duration = seconds
    label = str(start) if start == previous else f"{start}-{previous}"
    groups.append(f"{label}: {duration}s")
    return ", ".join(groups)
