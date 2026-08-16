import pytest

from services.generation_quality_gate import (
    assert_generation_package_ready,
    validate_generation_package,
)
from services.image_grid_prompts import build_compact_image_grid_prompts


def _long_korean_script() -> str:
    return " ".join(
        [
            "마을 끝 낡은 한옥 마당에서 이야기가 시작된다.",
            "며느리는 아무 말 없이 보따리를 들었고 사람들은 그 안에 숨은 약속을 두려워했다.",
        ]
        * 80
    )


def _scene(number: int, suffix: str = "") -> dict:
    video_detail = (
        f"Scene {number} AI video prompt: start on worn straw shoes, then a slow push-in toward "
        f"the daughter-in-law's trembling hands around the bundle, subtle lantern flicker, cloth moving in the wind, "
        f"villagers shifting silently in the midground, shallow depth of field, no dialogue, no captions, no music, "
        f"no narration, no subtitles, no sound effects, no audio, no text overlays, continuous single moment, "
        f"atmospheric dusk lighting. {suffix}"
    )
    return {
        "scene_id": f"scene{number:03d}",
        "scene_order": number,
        "media_prompt_status": "ready",
        "video_prompt": video_detail,
        "keyframe_subject": f"Scene {number}: daughter-in-law with cloth bundle in a hanok courtyard. {suffix}",
    }


def _grid_prompts() -> list[dict]:
    return build_compact_image_grid_prompts(
        [
            {
                "grid_number": 1,
                "scene_numbers": [1, 2, 3, 4],
                "scene_ids": [f"scene{index:03d}" for index in range(1, 5)],
                "shared_style": "Consistent old Korean folk tale, warm hand-painted texture, dusk hanok courtyard.",
                "panels": [
                    {
                        "scene_number": index,
                        "scene_id": f"scene{index:03d}",
                        "position": position,
                        "panel_prompt": (
                            f"Scene {index}: unique folk-tale action beat with the daughter-in-law, "
                            "cloth bundle, villagers, hanok courtyard, and emotional body language."
                        ),
                    }
                    for index, position in zip(
                        range(1, 5),
                        ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                    )
                ],
            }
        ]
    )


def _valid_payload() -> dict:
    scenes = [_scene(index, f"unique visual clue {index}") for index in range(1, 5)]
    return {
        "category": "옛날이야기",
        "generated_title": "마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리",
        "script": _long_korean_script(),
        "script_quality_report": {"verdict": "pass", "score": 86, "critical_issues": []},
        "structure": {
            "media_prompt_status": "ready",
            "image_grid_prompt_status": "ready",
            "scenes": scenes,
            "image_grid_prompts": _grid_prompts(),
        },
        "publish_metadata": {
            "titles": ["마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리"],
            "description": (
                "마을에서 쫓겨난 며느리가 오래된 보따리를 들고 돌아오며 시작되는 이야기입니다. "
                "사람들이 잊었다고 믿었던 약속과 가족의 선택이 어떤 대가로 돌아오는지 따라갑니다. "
                "작은 오해가 세월을 지나 어떻게 진실로 바뀌는지, 그리고 한 사람이 품고 온 침묵이 "
                "마을 전체의 기억을 어떻게 흔드는지 차분하게 보여주는 장편 민담형 영상입니다."
            ),
            "tags": ["며느리", "보따리", "마을", "약속", "민담", "가족"],
            "hashtags": ["#며느리", "#보따리", "#민담"],
        },
    }


def test_generation_quality_gate_accepts_complete_package():
    assert validate_generation_package(_valid_payload(), category="옛날이야기") == []
    assert_generation_package_ready(_valid_payload(), category="옛날이야기")


def test_generation_quality_gate_rejects_missing_video_and_grid_prompts():
    payload = _valid_payload()
    payload["structure"]["scenes"][2]["video_prompt"] = ""
    payload["structure"]["image_grid_prompts"] = []

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("video_prompt too short" in error for error in errors)
    assert any("image_grid_prompts" in error for error in errors)


def test_generation_quality_gate_rejects_bad_script_and_metadata():
    payload = _valid_payload()
    payload["script"] = "Auto-generated longform intro scene in English."
    payload["publish_metadata"] = {"description": "", "tags": []}

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("script too short" in error for error in errors)
    assert any("fallback/scratch" in error for error in errors)
    assert any("description missing" in error for error in errors)
    assert any("tags/hashtags missing" in error for error in errors)


def test_generation_quality_gate_rejects_revise_script_quality():
    payload = _valid_payload()
    payload["script_quality_report"] = {
        "verdict": "revise",
        "score": 74,
        "critical_issues": ["needs another rewrite"],
    }

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("script_quality_report not passing" in error for error in errors)


def test_generation_quality_gate_rejects_internal_metadata_terms():
    payload = _valid_payload()
    payload["publish_metadata"]["description"] += "\n\n이 프롬프트와 벤치마크 분석을 기반으로 자동 생성된 설명입니다."

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("internal production terms" in error for error in errors)


def test_generation_quality_gate_raises_on_invalid_package():
    payload = _valid_payload()
    payload["structure"]["image_grid_prompts"] = []

    with pytest.raises(ValueError, match="image_grid_prompts"):
        assert_generation_package_ready(payload, category="옛날이야기")
