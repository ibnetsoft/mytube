import pytest

from services.generation_quality_gate import (
    assert_generation_package_ready,
    validate_generation_package,
)


def _long_korean_script() -> str:
    return " ".join(
        [
            "마을 어귀의 낡은 우물가에서 시작된 작은 소문은 밤마다 조금씩 커져 갔다.",
            "며느리는 아무 말 없이 보따리를 품었고, 사람들은 그 안에 숨은 약속을 두려워했다.",
        ]
        * 80
    )


def _scene(number: int, suffix: str = "") -> dict:
    image_detail = (
        f"Old Korean folk tale illustration for scene {number}, a specific hanok courtyard at dusk, "
        f"one weary daughter-in-law holding a faded cloth bundle, villagers watching from wooden gates, "
        f"foreground worn straw shoes, midground tense faces, background blue mountain ridge and paper lanterns, "
        f"consistent warm Studio Ghibli inspired hand-painted texture, restrained earthy palette, emotional body language, "
        f"no text, no words, no letters, no labels, no watermarks, no captions, correct anatomy, exactly two arms, "
        f"exactly two hands, anatomically correct hands, no extra limbs, no fused fingers, no duplicated people. {suffix}"
    )
    video_detail = (
        f"Scene {number} AI video prompt: start locked-off on the worn straw shoes, then slow push-in toward "
        f"the daughter-in-law's trembling hands around the bundle, subtle lantern flicker, cloth moving in the wind, "
        f"villagers shifting silently in the midground, shallow depth of field, no dialogue, no captions, no music, "
        f"no narration, no subtitles, no sound effects, no audio, no text overlays, continuous single moment, "
        f"atmospheric dusk lighting. {suffix}"
    )
    return {
        "scene_id": f"scene{number:03d}",
        "scene_order": number,
        "media_prompt_status": "ready",
        "image_prompt": image_detail,
        "video_prompt": video_detail,
    }


def _valid_payload() -> dict:
    scenes = [_scene(index, f"unique visual clue {index}") for index in range(1, 5)]
    from services.image_grid_prompts import build_image_grid_prompts

    return {
        "category": "옛날이야기",
        "generated_title": "마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리",
        "script": _long_korean_script(),
        "structure": {
            "media_prompt_status": "ready",
            "image_grid_prompt_status": "ready",
            "scenes": scenes,
            "image_grid_prompts": build_image_grid_prompts(scenes),
        },
        "publish_metadata": {
            "titles": ["마을에서 쫓겨난 며느리가 십 년 뒤 들고 온 보따리"],
            "description": (
                "마을에서 쫓겨난 며느리가 십 년 뒤 낡은 보따리를 들고 돌아오며 시작되는 이야기입니다. "
                "사람들이 잊었다고 믿었던 약속과 우물가에 남겨진 작은 단서가 하나씩 드러납니다.\n\n"
                "보따리 안에 숨겨진 진실이 마을 사람들의 오래된 오해를 흔들고, 한 가족의 선택이 어떤 대가로 돌아오는지 따라갑니다."
            ),
            "tags": ["며느리", "보따리", "마을", "오해", "약속", "민담", "가족"],
            "hashtags": ["#며느리", "#보따리", "#민담"],
        },
    }


def test_generation_quality_gate_accepts_complete_package():
    assert validate_generation_package(_valid_payload(), category="옛날이야기") == []
    assert_generation_package_ready(_valid_payload(), category="옛날이야기")


def test_generation_quality_gate_rejects_duplicate_and_missing_prompts():
    payload = _valid_payload()
    scenes = payload["structure"]["scenes"]
    scenes[1]["image_prompt"] = scenes[0]["image_prompt"]
    scenes[2]["video_prompt"] = ""

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("duplicate image_prompt" in error for error in errors)
    assert any("video_prompt too short" in error for error in errors)


def test_generation_quality_gate_rejects_bad_script_and_metadata():
    payload = _valid_payload()
    payload["script"] = "Auto-generated longform intro scene in English."
    payload["publish_metadata"] = {"description": "", "tags": []}

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("script too short" in error for error in errors)
    assert any("fallback/scratch" in error for error in errors)
    assert any("description missing" in error for error in errors)
    assert any("tags/hashtags missing" in error for error in errors)


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
