"""Offline validation harness for Hermes generation packages.

This module is intentionally API-free. It creates deterministic generation
payloads and verifies the same gates that the worker uses before a job can be
marked ready.
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from services.generation_quality_gate import validate_generation_package
from services.image_grid_prompts import build_compact_image_grid_prompts


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402


TARGET_CATEGORIES = (
    "옛날이야기",
    "탈북사연",
    "해외감동",
    "노후금융",
    "황혼19금",
    "한국사연",
    "무협",
    "경제",
)


@dataclass(frozen=True)
class HarnessCheck:
    name: str
    passed: bool
    detail: str = ""
    category: str = "common"


def _long_korean_script(title: str) -> str:
    beats = [
        f"{title}이라는 말이 처음 마을에 퍼졌을 때 사람들은 아무도 쉽게 믿지 않았습니다.",
        "그러나 오래된 약속을 기억하는 노인이 조용히 문을 열자 모두가 숨을 죽였습니다.",
        "주인공은 겁을 삼키고 남겨진 흔적을 하나씩 확인하며 가족의 비밀에 다가갔습니다.",
        "작은 물건 하나와 떨리는 증언 하나가 서로 맞물리면서 감춰진 진실이 모습을 드러냈습니다.",
        "마지막 순간 그는 원망보다 선택을 먼저 바라보았고, 그 선택이 마을의 오래된 상처를 바꾸었습니다.",
    ]
    return " ".join(beats * 70)


def _video_prompt(scene_number: int) -> str:
    scene_variants = {
        1: (
            "An old wooden gate fills the foreground while a sealed paper charm trembles on the latch. "
            "A grandmother stands behind the threshold with one hand hidden in her sleeve, and dawn mist rolls through the yard."
        ),
        2: (
            "Inside a narrow room, a brass bowl, a folded letter, and a rain-soaked coat sit on a low table. "
            "The protagonist notices a fresh footprint beside the mat while candlelight bends across the wall."
        ),
        3: (
            "At the stone bridge, villagers hold back under umbrellas as the youngest witness points toward the riverbank. "
            "Wet reeds move behind him and a wrapped keepsake lies half-buried near the water."
        ),
        4: (
            "Near the shrine tree, the family gathers in a broken circle while the hidden object is finally opened. "
            "Late sunlight cuts through leaves, revealing dust, tears, and a changed expression on every face."
        ),
    }
    return (
        f"The shot uses a slow push-in. Scene {scene_number} opens on a distinct Korean longform story moment: "
        f"{scene_variants.get(scene_number, scene_variants[1])} "
        "The camera begins wide enough to show the surrounding place, then settles on the central subject with controlled "
        "cinematic lighting, natural fabric movement, restrained background motion, clear depth, and no written signs. "
        "The frame must preserve era, wardrobe, location logic, and character continuity while avoiding recycled poses. "
        "No dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio."
    )


def _scene(scene_number: int) -> dict[str, Any]:
    return {
        "scene_id": f"scene{scene_number:03d}",
        "scene_order": scene_number,
        "scene_summary": f"서로 다른 단서와 감정 변화가 드러나는 장면 {scene_number}",
        "scene_purpose": f"갈등을 다음 단계로 밀어 올리는 고유한 목적 {scene_number}",
        "retention_hook": f"다음 장면에서 밝혀질 다른 의문 {scene_number}",
        "media_prompt_status": "ready",
        "video_prompt": _video_prompt(scene_number),
        "keyframe_subject": f"장면 {scene_number}의 중심 인물과 고유한 소품",
    }


def _grid_prompts() -> list[dict[str, Any]]:
    panels = []
    for scene_number, position in zip(
        range(1, 5),
        ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"),
    ):
        panels.append(
            {
                "scene_number": scene_number,
                "scene_id": f"scene{scene_number:03d}",
                "position": position,
                "panel_prompt": (
                    f"Scene {scene_number}: a unique Korean narrative beat with distinct gesture, "
                    "prop, weather, eye-line, and emotional tension; no repeated composition."
                ),
            }
        )
    return build_compact_image_grid_prompts(
        [
            {
                "grid_number": 1,
                "scene_numbers": [1, 2, 3, 4],
                "scene_ids": [f"scene{index:03d}" for index in range(1, 5)],
                "shared_style": (
                    "Korean longform story storyboard, consistent characters, wardrobe, props, "
                    "lighting direction, location logic, and cinematic realism."
                ),
                "panels": panels,
            }
        ]
    )


def build_valid_sample_payload(category: str) -> dict[str, Any]:
    title = f"{category} 검증용 이야기, 닫힌 문 뒤에서 밝혀진 오래된 약속"
    return {
        "category": category,
        "generated_title": title,
        "script": _long_korean_script(title),
        "script_quality_report": {"verdict": "pass", "score": 86, "critical_issues": []},
        "structure": {
            "media_prompt_status": "ready",
            "image_grid_prompt_status": "ready",
            "scenes": [_scene(index) for index in range(1, 5)],
            "image_grid_prompts": _grid_prompts(),
        },
        "publish_metadata": {
            "titles": [title],
            "description": (
                f"{title}을 중심으로 오래된 약속과 감춰진 선택이 어떻게 사람들의 마음을 바꾸는지 따라갑니다. "
                "초반에는 의문을 분명히 제시하고, 중반에는 서로 다른 단서와 감정의 방향을 쌓으며, "
                "후반에는 주인공의 선택이 남긴 의미를 차분하게 정리합니다. 반복 장면 없이 이야기의 긴장과 여운을 살린 구성입니다."
            ),
            "tags": [category, "장편이야기", "감동사연", "반전이야기", "인물서사", "한국어내레이션"],
            "hashtags": [f"#{category}", "#장편이야기", "#반전이야기"],
        },
    }


def _expect_gate_error(name: str, payload: dict[str, Any], category: str, expected: str) -> HarnessCheck:
    errors = validate_generation_package(payload, category=category)
    matched = any(expected in error for error in errors)
    return HarnessCheck(
        name=name,
        category=category,
        passed=matched,
        detail="; ".join(errors) if errors else "no errors returned",
    )


def _expect_gate_pass(name: str, payload: dict[str, Any], category: str) -> HarnessCheck:
    errors = validate_generation_package(payload, category=category)
    return HarnessCheck(
        name=name,
        category=category,
        passed=not errors,
        detail="; ".join(errors),
    )


def run_offline_harness() -> dict[str, Any]:
    checks: list[HarnessCheck] = []

    for category in TARGET_CATEGORIES:
        errors = validate_generation_package(build_valid_sample_payload(category), category=category)
        checks.append(
            HarnessCheck(
                name=f"{category}: complete package smoke",
                category=category,
                passed=not errors,
                detail="; ".join(errors),
            )
        )

    contaminated = build_valid_sample_payload("옛날이야기")
    contaminated["benchmark_analysis"] = {
        "candidates": [{"title": "삼성전자 주가와 코스피 반등을 분석한 경제 영상"}]
    }
    checks.append(
        _expect_gate_error(
            "old-story package blocks economy benchmark contamination",
            contaminated,
            "옛날이야기",
            "off-category economy contamination",
        )
    )

    repeated_structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면이 반복된다",
                "scene_purpose": f"다른 목적처럼 보이지만 반복 {index}",
                "retention_hook": f"다른 훅처럼 보이지만 반복 {index}",
            }
            for index in range(1, 5)
        ]
    }
    repetition_errors = hermes_worker._scene_plan_repetition_errors(repeated_structure)
    checks.append(
        HarnessCheck(
            name="scene plan repetition is blocked",
            passed=any("repeats one summary" in error for error in repetition_errors),
            detail="; ".join(repetition_errors),
        )
    )


    missing_grid = build_valid_sample_payload("옛날이야기")
    missing_grid["structure"]["image_grid_prompts"] = []
    checks.append(
        _expect_gate_error(
            "missing 2x2 image grid prompts are blocked",
            missing_grid,
            "옛날이야기",
            "image_grid_prompts",
        )
    )

    bad_script = build_valid_sample_payload("옛날이야기")
    bad_script["script"] = "Auto-generated longform intro scene in English."
    checks.append(
        _expect_gate_error(
            "fallback English script text is blocked",
            bad_script,
            "옛날이야기",
            "fallback/scratch",
        )
    )

    revise_script = build_valid_sample_payload("옛날이야기")
    revise_script["script_quality_report"] = {"verdict": "revise", "score": 42, "critical_issues": ["looping"]}
    checks.append(
        _expect_gate_pass(
            "revise script QA report is informational",
            revise_script,
            "옛날이야기",
        )
    )

    missing_metadata = build_valid_sample_payload("옛날이야기")
    missing_metadata.pop("publish_metadata", None)
    checks.append(
        _expect_gate_error(
            "missing metadata is blocked",
            missing_metadata,
            "옛날이야기",
            "missing publish_metadata",
        )
    )

    rss_payload = {
        "category": "옛날이야기",
        "category_name": "옛날이야기",
        "search_keywords": ["조선시대 설화", "한국 민담"],
    }
    bad_rss_candidate = {
        "title": "국정원이 키운 전학생과 학교 권투부의 비밀",
        "description": "현대 학교 드라마",
        "channel_title": "현대 사건 채널",
    }
    good_rss_candidate = {
        "title": "조선시대 나무꾼이 산길에서 만난 저승사자 이야기",
        "description": "한국 민담과 전설",
        "channel_title": "옛이야기",
    }
    checks.append(
        HarnessCheck(
            name="old-story RSS relevance rejects modern contamination",
            passed=not hermes_worker._is_relevant_rss_candidate(bad_rss_candidate, rss_payload, "옛날이야기"),
        )
    )
    checks.append(
        HarnessCheck(
            name="old-story RSS relevance accepts folk material",
            passed=hermes_worker._is_relevant_rss_candidate(good_rss_candidate, rss_payload, "옛날이야기"),
        )
    )

    failed = [check for check in checks if not check.passed]
    return {
        "status": "pass" if not failed else "fail",
        "api_calls": 0,
        "categories": list(TARGET_CATEGORIES),
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": [asdict(check) for check in checks],
    }


def assert_offline_harness_passes() -> None:
    report = run_offline_harness()
    if report["status"] != "pass":
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    result = run_offline_harness()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "pass" else 1)
