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
MIN_SCRIPT_QUALITY_SCORE = 78
DEFAULT_MIN_IMAGE_PROMPT_CHARS = 220
DEFAULT_MIN_VIDEO_PROMPT_CHARS = 260
MAX_VIDEO_PROMPT_SCENES = 12
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
_STORY_OFF_CATEGORY_TERMS = _ECONOMY_TERMS + (
    "국민연금",
    "퇴직연금",
    "연금 계산서",
    "연금 수령액",
    "노후자금",
    "가계부",
    "생활비",
    "고정비",
    "자동이체",
    "pension",
    "retirement fund",
    "bank statement",
    "年金",
    "老後資金",
    "家計簿",
    "生活費",
)
_CATEGORY_CONTAMINATION_MAP = {
    "옛날이야기": _STORY_OFF_CATEGORY_TERMS,
    "English Folktales": _STORY_OFF_CATEGORY_TERMS,
    "日本昔話": _STORY_OFF_CATEGORY_TERMS,
    "무협": ("스마트폰", "아파트", "달러", "주식", "비행기", "경찰", "CCTV", "엘리베이터", "지하철"),
    "탈북사연": ("비급", "장문인", "사부", "단전", "내공", "무림", "호랑이 사냥꾼", "조선시대"),
}
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


def _metadata_contains_internal_term(text: str) -> bool:
    blob = str(text or "")
    lowered = blob.lower()
    for term in _METADATA_INTERNAL_TERMS:
        normalized = str(term or "").strip()
        if not normalized:
            continue
        term_lower = normalized.lower()
        if re.fullmatch(r"[a-z0-9_ ]+", term_lower):
            pattern = r"(?<![a-z0-9_])" + re.escape(term_lower) + r"(?![a-z0-9_])"
            if re.search(pattern, lowered):
                return True
            continue
        if term_lower in lowered:
            return True
    return False


def _text(value: Any) -> str:
    return str(value or "").strip()


def _japanese_char_count(value: str) -> int:
    text = str(value or "")
    return len(re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff々〆ヵヶー]", text))


def _scene_number(scene: Mapping[str, Any], fallback: int) -> int | str:
    value = scene.get("scene_order") or scene.get("scene_number") or fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _scene_requires_video_prompt(scene: Mapping[str, Any], fallback: int) -> bool:
    if scene.get("video_prompt_required") is False:
        return False
    scene_number = _scene_number(scene, fallback)
    return isinstance(scene_number, int) and scene_number <= MAX_VIDEO_PROMPT_SCENES


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


def _contamination_context(payload: Mapping[str, Any]) -> str:
    benchmark_analysis = payload.get("benchmark_analysis")
    benchmark_context: Any = benchmark_analysis
    if isinstance(benchmark_analysis, Mapping):
        benchmark_context = {
            "keyword": benchmark_analysis.get("keyword"),
            "selected_title": benchmark_analysis.get("selected_title"),
            "representative_title": benchmark_analysis.get("representative_title"),
            "candidates": [],
        }
        candidates = benchmark_analysis.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates[:10]:
                if not isinstance(candidate, Mapping):
                    continue
                benchmark_context["candidates"].append({
                    "title": candidate.get("title"),
                    "channel_title": candidate.get("channel_title"),
                    "search_query": candidate.get("search_query"),
                })

    research_bundle = payload.get("research_bundle")
    research_context: Any = research_bundle
    if isinstance(research_bundle, Mapping):
        research_context = {
            "topic": research_bundle.get("topic"),
            "upload_title": research_bundle.get("upload_title"),
            "sources": [],
        }
        sources = research_bundle.get("sources")
        if isinstance(sources, list):
            for source in sources[:10]:
                if isinstance(source, Mapping):
                    research_context["sources"].append({"title": source.get("title"), "url": source.get("url")})

    return json.dumps(
        {
            "topic": payload.get("topic") or payload.get("generated_title"),
            "title": payload.get("generated_title") or payload.get("upload_title"),
            "benchmark_analysis": benchmark_context,
            "research_bundle": research_context,
        },
        ensure_ascii=False,
    )


def _category_content(payload: Mapping[str, Any]) -> str:
    structure = payload.get("structure") if isinstance(payload.get("structure"), Mapping) else {}
    scenes = structure.get("scenes") if isinstance(structure, Mapping) else []
    compact_scenes = []
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, Mapping):
            continue
        compact_scenes.append({
            key: scene.get(key)
            for key in (
                "scene_summary",
                "scene_situation",
                "scene_purpose",
                "retention_hook",
                "title_promise_link",
                "end_bridge",
            )
        })
    return json.dumps(
        {
            "title": payload.get("generated_title") or payload.get("upload_title"),
            "script": payload.get("script"),
            "scenes": compact_scenes,
        },
        ensure_ascii=False,
    )


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
    language = _text(payload.get("language")).lower() or "ko"
    require_korean_script = require_korean_script and language == "ko"
    script_quality = payload.get("script_quality_report")

    if not isinstance(script_quality, Mapping):
        errors.append("missing script_quality_report")
    else:
        try:
            script_quality_score = int(float(script_quality.get("score") or 0))
        except (TypeError, ValueError):
            errors.append("script_quality_report score invalid")
        else:
            verdict = _text(script_quality.get("verdict")).lower()
            critical_issues = script_quality.get("critical_issues")
            if verdict != "pass" or script_quality_score < MIN_SCRIPT_QUALITY_SCORE or critical_issues:
                errors.append(
                    "script_quality_report not passing: "
                    f"verdict={verdict or 'missing'}, score={script_quality_score}, "
                    f"critical_issues={len(critical_issues) if isinstance(critical_issues, list) else int(bool(critical_issues))}"
                )

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
    elif language == "ja":
        japanese = _japanese_char_count(script)
        hangul = len(re.findall(r"[\uac00-\ud7a3]", script))
        if japanese < 800:
            errors.append(f"script is not Japanese enough: japanese={japanese}, chars={len(script)}")
        if hangul > 0:
            errors.append(f"script contains Hangul for Japanese category: hangul={hangul}")

    if any(marker in script for marker in _FALLBACK_SCRIPT_MARKERS):
        errors.append("script contains fallback/scratch English template text")

    contamination_terms = _CATEGORY_CONTAMINATION_MAP.get(category)
    if contamination_terms:
        content_blob = f"{_contamination_context(payload)}\n{_category_content(payload)}"
        if re.search("|".join(re.escape(term) for term in contamination_terms), content_blob, re.I):
            if category in {"옛날이야기", "English Folktales", "日本昔話"}:
                errors.append(f"off-category finance/economy contamination detected for story category '{category}'")
            else:
                errors.append(f"off-category contamination detected for category '{category}'")

    video_prompts: list[tuple[str, str]] = []
    for fallback_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, Mapping):
            errors.append(f"scene {fallback_number} is not an object")
            continue
        label = str(_scene_number(scene, fallback_number))
        video_prompt = _text(scene.get("video_prompt"))
        requires_video_prompt = _scene_requires_video_prompt(scene, fallback_number)
        if video_prompt:
            video_prompts.append((label, video_prompt))

        if scene.get("media_prompt_status") != "ready":
            errors.append(f"scene {label} media_prompt_status is not ready")
        if not requires_video_prompt:
            continue
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
        titles = metadata.get("titles") if isinstance(metadata.get("titles"), list) else []
        primary_title = _text(titles[0] if titles else payload.get("generated_title") or payload.get("upload_title"))
        if not description:
            errors.append("publish_metadata.description missing")
        elif len(description) < 120:
            errors.append("publish_metadata.description too short")
        elif require_korean_script and _hangul_ratio(description) < 0.8:
            errors.append("publish_metadata.description not Korean enough")
        elif language == "ja":
            if _japanese_char_count(primary_title) < 2:
                errors.append("publish_metadata title is not Japanese enough")
            if _japanese_char_count(description) < 24 or re.search(r"[\uac00-\ud7a3]", description):
                errors.append("publish_metadata.description is not Japanese enough")
        if primary_title and not _metadata_title_matches_script(primary_title, script):
            errors.append("publish_metadata title does not match script")
        blob = "\n".join([
            primary_title,
            description,
            " ".join(str(tag) for tag in (metadata.get("tags") or [])),
            " ".join(str(tag) for tag in (metadata.get("hashtags") or [])),
        ])
        if _metadata_contains_internal_term(blob):
            errors.append("publish_metadata leaks internal production terms")
        tags = metadata.get("tags") or metadata.get("hashtags")
        if not isinstance(tags, list) or not any(_text(tag) for tag in tags):
            errors.append("publish_metadata tags/hashtags missing")
        elif len([tag for tag in tags if _text(tag)]) < 5:
            errors.append("publish_metadata has too few tags")
        elif language == "ja" and any(_japanese_char_count(_text(tag).lstrip("#")) < 1 for tag in tags[:8] if _text(tag)):
            errors.append("publish_metadata tags are not Japanese enough")
        hashtags = metadata.get("hashtags") if isinstance(metadata.get("hashtags"), list) else []
        if len([tag for tag in hashtags if _text(tag)]) < 3:
            errors.append("publish_metadata has too few hashtags")
        elif language == "ja" and any(_japanese_char_count(_text(tag).lstrip("#")) < 1 for tag in hashtags[:8] if _text(tag)):
            errors.append("publish_metadata hashtags are not Japanese enough")

    return errors


def assert_generation_package_ready(payload: Mapping[str, Any], *, category: str = "") -> None:
    errors = validate_generation_package(payload, category=category)
    if errors:
        raise ValueError("; ".join(errors))
