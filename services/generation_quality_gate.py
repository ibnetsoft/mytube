"""Deterministic quality gates for worker pre-generated longform assets."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any


DEFAULT_MIN_SCRIPT_HANGUL = 1000
DEFAULT_MAX_LATIN_RATIO = 0.05
DEFAULT_MIN_IMAGE_PROMPT_CHARS = 220
DEFAULT_MIN_VIDEO_PROMPT_CHARS = 260
APPROVED_VIDEO_CAMERA_MOVEMENTS = (
    "slow push-in",
    "slow pull-back",
    "gentle pan",
    "gentle tilt",
    "slow dolly",
    "slow tracking shot",
    "locked-off shot",
    "subtle crane movement",
    "slow drift",
)

_FALLBACK_SCRIPT_MARKERS = (
    "At first",
    "One small clue",
    "As time passed",
    "Auto-generated longform",
    "intro scene",
    "development scene",
)
_SCRATCH_IMAGE_MARKERS = (
    "Korean longform storytelling scene",
    "high quality image",
    "cinematic scene",
    "beautiful scene",
)
_ECONOMY_TERMS = (
    "금값",
    "코스피",
    "환율",
    "금리",
    "주가",
    "ETF",
    "부동산",
    "PF",
    "경제",
    "물가",
    "인플레이션",
    "유가",
    "달러",
    "원화",
    "투자",
    "매수",
    "매도",
    "주식",
    "채권",
    "나스닥",
    "비트코인",
)
_METADATA_INTERNAL_TERMS = (
    "AI",
    "worker",
    "prompt",
    "benchmark",
    "QA",
    "quality gate",
    "learning_profile",
    "scene plan",
    "narrative_blueprint",
    "script_quality_report",
    "자동 생성",
    "프롬프트",
    "벤치마크",
    "품질 게이트",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _scene_number(scene: Mapping[str, Any], fallback: int) -> int | str:
    value = scene.get("scene_order") or scene.get("scene_number") or fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _similarity(left: str, right: str) -> float:
    a = re.sub(r"\s+", "", left.lower())
    b = re.sub(r"\s+", "", right.lower())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _duplicate_or_near_duplicate_errors(values: list[tuple[str, str]], label: str) -> list[str]:
    errors: list[str] = []
    exact_counter = Counter(value for _scene, value in values if value)
    for value, count in exact_counter.items():
        if count > 1:
            scenes = [scene for scene, prompt in values if prompt == value]
            errors.append(f"duplicate {label}: scenes {', '.join(scenes)}")

    for index, (left_scene, left_value) in enumerate(values):
        if not left_value:
            continue
        for right_scene, right_value in values[index + 1 :]:
            if not right_value or left_value == right_value:
                continue
            if _similarity(left_value, right_value) >= 0.998:
                errors.append(f"near-duplicate {label}: scenes {left_scene} and {right_scene}")
    return errors


def _hangul_ratio(value: str) -> float:
    hangul = len(re.findall(r"[\uac00-\ud7a3]", value or ""))
    latin = len(re.findall(r"[A-Za-z]", value or ""))
    if hangul + latin == 0:
        return 0.0
    return hangul / (hangul + latin)


def _metadata_title_matches_script(title: str, script: str) -> bool:
    def variants(token: str) -> set[str]:
        result = {token}
        for suffix in ("에서", "으로", "에게", "에게서", "부터", "까지", "은", "는", "이", "가", "을", "를", "과", "와", "도", "만"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                result.add(token[: -len(suffix)])
        return result

    tokens = [
        token for token in re.findall(r"[\uac00-\ud7a3A-Za-z0-9]{2,}", str(title or ""))
        if token not in {"그리고", "하지만", "그런데", "이야기", "사연"}
    ]
    if not tokens:
        return True
    matched = sum(1 for token in tokens[:8] if any(variant in script for variant in variants(token)))
    return matched >= max(1, min(2, len(tokens[:8]) // 3))


def validate_generation_package(
    payload: Mapping[str, Any],
    *,
    category: str = "",
    require_korean_script: bool = True,
) -> list[str]:
    """Return blocking quality errors for a completed worker generation package.

    This intentionally checks only objective failures. It does not try to judge
    taste; it prevents the worker from marking incomplete or obviously broken
    data as ready.
    """
    errors: list[str] = []
    structure = payload.get("structure") if isinstance(payload.get("structure"), Mapping) else {}
    scenes = structure.get("scenes") if isinstance(structure, Mapping) else None
    script = _text(payload.get("script"))
    metadata = payload.get("publish_metadata") if isinstance(payload.get("publish_metadata"), Mapping) else {}
    category = _text(category or payload.get("category"))
    script_quality = payload.get("script_quality_report")

    if not isinstance(script_quality, Mapping):
        errors.append("missing script_quality_report")
    else:
        verdict = _text(script_quality.get("verdict")).lower()
        try:
            score = int(float(script_quality.get("score") or 0))
        except (TypeError, ValueError):
            score = 0
        if verdict != "pass" or score < 78:
            errors.append(f"script_quality_report not passing: verdict={verdict or 'missing'}, score={score}")

    if not isinstance(scenes, list) or not scenes:
        errors.append("missing structure.scenes")
        scenes = []

    if require_korean_script:
        hangul = len(re.findall(r"[\uac00-\ud7a3]", script))
        latin = len(re.findall(r"[A-Za-z]", script))
        max_latin = max(80, int(hangul * DEFAULT_MAX_LATIN_RATIO))
        if hangul < DEFAULT_MIN_SCRIPT_HANGUL:
            errors.append(f"script too short or not Korean enough: hangul={hangul}, chars={len(script)}")
        if latin > max_latin:
            errors.append(f"script has too much Latin text: latin={latin}, max={max_latin}")

    if any(marker in script for marker in _FALLBACK_SCRIPT_MARKERS):
        errors.append("script contains fallback/scratch English template text")

    if category == "옛날이야기":
        context_blob = json.dumps(
            {
                "topic": payload.get("topic") or payload.get("generated_title"),
                "title": payload.get("generated_title") or payload.get("upload_title"),
                "benchmark_analysis": payload.get("benchmark_analysis"),
                "research_bundle": payload.get("research_bundle"),
            },
            ensure_ascii=False,
        )
        if re.search("|".join(re.escape(term) for term in _ECONOMY_TERMS), context_blob, re.I):
            errors.append("off-category economy contamination detected for old-story category")

    video_prompts: list[tuple[str, str]] = []
    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, Mapping):
            errors.append(f"scene {fallback_number} is not an object")
            continue
        label = str(_scene_number(scene, fallback_number))
        video_prompt = _text(scene.get("video_prompt"))
        video_prompts.append((label, video_prompt))

        if scene.get("media_prompt_status") != "ready":
            errors.append(f"scene {label} media_prompt_status is not ready")
        if len(video_prompt) < DEFAULT_MIN_VIDEO_PROMPT_CHARS:
            errors.append(f"scene {label} video_prompt too short/missing")
        video_lower = video_prompt.lower()
        movement_count = sum(1 for movement in APPROVED_VIDEO_CAMERA_MOVEMENTS if movement in video_lower)
        if movement_count != 1:
            errors.append(f"scene {label} video_prompt must contain exactly one approved camera movement")
        for required in ("no dialogue", "no narration", "no subtitles", "no captions", "no music", "no sound effects", "no audio"):
            if required not in video_lower:
                errors.append(f"scene {label} video_prompt missing guardrail: {required}")

    errors.extend(_duplicate_or_near_duplicate_errors(video_prompts, "video_prompt"))

    try:
        from services.image_grid_prompts import validate_image_grid_prompt_readiness

        validate_image_grid_prompt_readiness(
            scenes,
            structure.get("image_grid_prompts") if isinstance(structure, Mapping) else None,
            status=structure.get("image_grid_prompt_status") if isinstance(structure, Mapping) else None,
            require_status="ready",
            require_compact_template=True,
        )
    except Exception as exc:
        errors.append(f"image_grid_prompts invalid: {exc}")

    if not metadata:
        errors.append("missing publish_metadata")
    else:
        if metadata.get("source") == "worker_fallback":
            errors.append("publish_metadata used worker_fallback")
        description = _text(metadata.get("description"))
        if not description:
            errors.append("publish_metadata.description missing")
        elif len(description) < 120:
            errors.append("publish_metadata.description too short")
        elif require_korean_script and _hangul_ratio(description) < 0.8:
            errors.append("publish_metadata.description not Korean enough")
        titles = metadata.get("titles") if isinstance(metadata.get("titles"), list) else []
        primary_title = _text(titles[0] if titles else payload.get("generated_title") or payload.get("upload_title"))
        if primary_title and not _metadata_title_matches_script(primary_title, script):
            errors.append("publish_metadata title does not match script")
        blob = "\n".join([
            primary_title,
            description,
            " ".join(str(tag) for tag in (metadata.get("tags") or [])),
            " ".join(str(tag) for tag in (metadata.get("hashtags") or [])),
        ])
        if any(term.lower() in blob.lower() for term in _METADATA_INTERNAL_TERMS):
            errors.append("publish_metadata leaks internal production terms")
        tags = metadata.get("tags") or metadata.get("hashtags")
        if not isinstance(tags, list) or not any(_text(tag) for tag in tags):
            errors.append("publish_metadata tags/hashtags missing")
        elif len([tag for tag in tags if _text(tag)]) < 5:
            errors.append("publish_metadata has too few tags")
        hashtags = metadata.get("hashtags") if isinstance(metadata.get("hashtags"), list) else []
        if len([tag for tag in hashtags if _text(tag)]) < 3:
            errors.append("publish_metadata has too few hashtags")

    return errors


def assert_generation_package_ready(payload: Mapping[str, Any], *, category: str = "") -> None:
    errors = validate_generation_package(payload, category=category)
    if errors:
        raise ValueError("; ".join(errors))
