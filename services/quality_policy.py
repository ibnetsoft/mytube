"""Validated runtime quality policy shared by Hermes quality gates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

POLICY_KEY = "hermes_generation"
DEFAULT_QUALITY_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "topic": {"enabled": True, "min_title_chars": 12},
    "plan": {"enabled": True, "min_scenes": 1, "require_media_status_ready": True},
    "script": {
        "enabled": True, "min_quality_score": 78, "min_hangul_chars": 1000,
        "max_latin_ratio": 0.05, "max_repeated_paragraph_opener": 2,
        "prohibit_fallback": True, "prohibit_off_category": True,
    },
    "media": {
        "enabled": True, "min_image_prompt_chars": 120, "min_video_prompt_chars": 260,
        "max_video_prompt_scenes": 12, "required_camera_movements": 1,
        "require_video_guardrails": True, "prohibit_duplicate_prompts": True,
        "prohibit_duplicate_scene_summaries": True,
        "prohibit_duplicate_retention_hooks": True, "require_image_grids": True,
    },
    "publish": {
        "enabled": True, "min_description_chars": 120,
        "require_language_match": True, "prohibit_internal_terms": True,
    },
    "delivery": {
        "enabled": True, "require_all_prior_stages": True,
        "require_quality_report_pass": True, "block_scene_count_mismatch": True,
    },
}
_active_policy = deepcopy(DEFAULT_QUALITY_POLICY)
_active_version = 0


def _merge_known(defaults: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, default in defaults.items():
        value = candidate.get(key, default)
        if isinstance(default, Mapping):
            merged[key] = _merge_known(default, value if isinstance(value, Mapping) else {})
        elif isinstance(default, bool):
            merged[key] = value if isinstance(value, bool) else default
        elif isinstance(default, int):
            merged[key] = value if isinstance(value, int) and not isinstance(value, bool) else default
        elif isinstance(default, float):
            merged[key] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default
        else:
            merged[key] = value if isinstance(value, type(default)) else default
    return merged


def normalize_quality_policy(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    policy = _merge_known(DEFAULT_QUALITY_POLICY, candidate or {})
    policy["script"]["min_quality_score"] = max(0, min(100, policy["script"]["min_quality_score"]))
    policy["script"]["min_hangul_chars"] = max(0, policy["script"]["min_hangul_chars"])
    policy["script"]["max_latin_ratio"] = max(0.0, min(1.0, policy["script"]["max_latin_ratio"]))
    policy["script"]["max_repeated_paragraph_opener"] = max(1, policy["script"]["max_repeated_paragraph_opener"])
    policy["plan"]["min_scenes"] = max(1, policy["plan"]["min_scenes"])
    policy["media"]["min_image_prompt_chars"] = max(1, policy["media"]["min_image_prompt_chars"])
    policy["media"]["min_video_prompt_chars"] = max(1, policy["media"]["min_video_prompt_chars"])
    policy["media"]["max_video_prompt_scenes"] = max(0, policy["media"]["max_video_prompt_scenes"])
    policy["media"]["required_camera_movements"] = max(0, policy["media"]["required_camera_movements"])
    policy["publish"]["min_description_chars"] = max(0, policy["publish"]["min_description_chars"])
    policy["script"]["prohibit_fallback"] = True
    policy["media"]["prohibit_duplicate_prompts"] = True
    policy["media"]["prohibit_duplicate_scene_summaries"] = True
    policy["media"]["prohibit_duplicate_retention_hooks"] = True
    policy["delivery"]["require_all_prior_stages"] = True
    policy["delivery"]["require_quality_report_pass"] = True
    return policy


def set_active_quality_policy(candidate: Mapping[str, Any] | None, version: int = 0) -> dict[str, Any]:
    global _active_policy, _active_version
    _active_policy = normalize_quality_policy(candidate)
    _active_version = max(0, int(version or 0))
    return quality_policy_snapshot()


def quality_policy_snapshot() -> dict[str, Any]:
    return {"key": POLICY_KEY, "version": _active_version, "policy": deepcopy(_active_policy)}


def active_quality_policy() -> dict[str, Any]:
    return deepcopy(_active_policy)
