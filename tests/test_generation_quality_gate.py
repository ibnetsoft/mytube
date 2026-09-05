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
        "image_prompt": (
            f"Scene {number}: the daughter-in-law grips a weathered cloth bundle in a hanok courtyard, "
            f"with distinct body language, dusk lantern light, period wardrobe, and unique visual clue {number}."
        ),
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


def _grid_prompts_for_count(scene_count: int) -> list[dict]:
    grids = []
    for grid_number, start in enumerate(range(1, scene_count + 1, 4), start=1):
        scene_numbers = list(range(start, min(start + 4, scene_count + 1)))
        if len(scene_numbers) < 4:
            break
        grids.append(
            {
                "grid_number": grid_number,
                "scene_numbers": scene_numbers,
                "scene_ids": [f"scene{index:03d}" for index in scene_numbers],
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
                        scene_numbers,
                        ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                    )
                ],
            }
        )
    return build_compact_image_grid_prompts(grids)


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


def test_generation_quality_gate_rejects_deterministic_image_prompt_fallback():
    payload = _valid_payload()
    payload["structure"]["scenes"][0]["image_prompt"] = (
        "Scene 1: visualize the final narration beat. Story excerpt: a generic scene. "
        "Emotion: tense. Unique visual anchor: courtyard."
    )

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("deterministic fallback" in error for error in errors)


def test_generation_quality_gate_rejects_duplicate_scene_summary_and_hook():
    payload = _valid_payload()
    for scene in payload["structure"]["scenes"][:2]:
        scene["scene_summary"] = "며느리가 붉은 실로 묘 앞 소나무와 초가 문고리를 잇는다"
        scene["retention_hook"] = "며느리가 붉은 실을 묶은 진짜 이유는 무엇일까?"

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("duplicate scene scene_summary" in error for error in errors)
    assert any("duplicate scene retention_hook" in error for error in errors)


def test_generation_quality_gate_allows_video_prompts_only_for_first_12_scenes():
    payload = _valid_payload()
    scenes = [_scene(index, f"unique visual clue {index}") for index in range(1, 17)]
    for scene in scenes[12:]:
        scene["video_prompt"] = ""
        scene["video_prompt_required"] = False
    payload["structure"]["scenes"] = scenes
    payload["structure"]["image_grid_prompts"] = _grid_prompts_for_count(16)

    errors = validate_generation_package(payload, category="old-story")

    assert not any("scene 13 video_prompt" in error for error in errors)
    assert not any("scene 16 video_prompt" in error for error in errors)


def test_generation_quality_gate_rejects_bad_script_and_metadata():
    payload = _valid_payload()
    payload["script"] = "Auto-generated longform intro scene in English."
    payload["publish_metadata"] = {"description": "", "tags": []}

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("script too short" in error for error in errors)
    assert any("fallback/scratch" in error for error in errors)
    assert any("description missing" in error for error in errors)
    assert any("tags/hashtags missing" in error for error in errors)


def test_generation_quality_gate_blocks_revise_script_quality():
    payload = _valid_payload()
    payload["script_quality_report"] = {
        "verdict": "revise",
        "score": 74,
        "critical_issues": ["needs another rewrite"],
    }

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("script_quality_report not passing" in error for error in errors)


def test_generation_quality_gate_blocks_story_script_with_pension_contamination():
    payload = _valid_payload()
    payload["category"] = "日本昔話"
    payload["language"] = "ja"
    payload["script"] = "年金と生活費の計算を続けました。" * 300

    errors = validate_generation_package(payload, category="日本昔話", require_korean_script=False)

    assert any("finance/economy contamination" in error for error in errors)


def test_generation_quality_gate_blocks_finance_contamination_for_non_story_category():
    payload = _valid_payload()
    payload["category"] = "무협"
    payload["script"] += " 국민연금 수령액을 확인했다."

    errors = validate_generation_package(payload, category="무협")

    assert any("finance/pension contamination is prohibited in every category" in error for error in errors)


def test_finance_filter_does_not_treat_denunciation_as_stock_sale():
    from services.content_safety import finance_content_matches

    assert "매도" not in finance_content_matches("문파 사람들은 그를 배신자로 매도하고 모욕했다.")
    assert "매도" in finance_content_matches("보유 주식을 시장 가격에 매도 주문했다.")


def test_old_story_contamination_ignores_korean_suffix_substrings():
    payload = _valid_payload()
    payload["script"] += " 우물가로 다가온 그는 저주가 아니라 이유가 남긴 흔적을 보았다." * 20

    errors = validate_generation_package(payload, category="옛날이야기")

    assert not any("finance/economy contamination" in error for error in errors)


def test_old_story_contamination_still_blocks_standalone_price_terms():
    payload = _valid_payload()
    payload["script"] += " 물가 상승과 유가 급등을 분석했다." * 20

    errors = validate_generation_package(payload, category="옛날이야기")

    assert any("finance/economy contamination" in error for error in errors)


def test_old_story_contamination_ignores_benchmark_analysis_body():
    payload = _valid_payload()
    payload["benchmark_analysis"] = {
        "keyword": "옛날이야기",
        "candidates": [
            {
                "title": "조선시대 산골 마을에 남겨진 붉은 실의 비밀",
                "channel_title": "역사 이야기",
                "search_query": "옛날이야기",
                "analysis": {
                    "main_topics": ["신분 차이", "부동산과 경제라는 단어가 분석 설명에만 등장"],
                    "summary": "성과 분석 문장에는 경제라는 말이 있을 수 있다.",
                },
            }
        ],
    }

    errors = validate_generation_package(payload, category="옛날이야기")

    assert not any("off-category economy contamination" in error for error in errors)


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
