"""Shared narration pacing policy for script, scene, and subtitle timing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_NARRATION_PACE = "senior"


@dataclass(frozen=True)
class NarrationPacePolicy:
    key: str
    label: str
    chars_per_second: float
    subtitle_max_chars: int
    short_scene_min_chars: int
    short_scene_max_chars: int
    description: str

    @property
    def chars_per_minute(self) -> int:
        return round(self.chars_per_second * 60)


NARRATION_PACE_POLICIES: dict[str, NarrationPacePolicy] = {
    "senior": NarrationPacePolicy(
        key="senior",
        label="시니어 기본",
        chars_per_second=5.0,
        subtitle_max_chars=20,
        short_scene_min_chars=18,
        short_scene_max_chars=34,
        description="시니어 대상 기본 속도. 또박또박 읽을 수 있도록 여백을 둡니다.",
    ),
    "normal": NarrationPacePolicy(
        key="normal",
        label="일반 속도",
        chars_per_second=6.2,
        subtitle_max_chars=24,
        short_scene_min_chars=24,
        short_scene_max_chars=42,
        description="일반 롱폼 내레이션 속도입니다.",
    ),
    "fast": NarrationPacePolicy(
        key="fast",
        label="약간 빠름",
        chars_per_second=7.0,
        subtitle_max_chars=28,
        short_scene_min_chars=28,
        short_scene_max_chars=48,
        description="정보량을 조금 더 담는 빠른 내레이션 속도입니다.",
    ),
}


def normalize_narration_pace(value: Any) -> str:
    key = str(value or "").strip().lower()
    aliases = {
        "slow": "senior",
        "senior_slow": "senior",
        "default": "senior",
        "standard": "normal",
        "regular": "normal",
        "quick": "fast",
        "slightly_fast": "fast",
    }
    key = aliases.get(key, key)
    if key not in NARRATION_PACE_POLICIES:
        return DEFAULT_NARRATION_PACE
    return key


def get_narration_policy(value: Any = None) -> NarrationPacePolicy:
    return NARRATION_PACE_POLICIES[normalize_narration_pace(value)]


def get_project_narration_policy(settings: dict | None = None) -> NarrationPacePolicy:
    settings = settings or {}
    return get_narration_policy(settings.get("narration_pace"))


def estimated_duration_seconds_for_text(text: str, pace: Any = None) -> int:
    policy = get_narration_policy(pace)
    char_count = len(str(text or ""))
    return max(5, int(round(char_count / policy.chars_per_second)))
