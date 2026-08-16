from app.routers import user_topics
from services.image_grid_prompts import build_compact_image_grid_prompts


def _grid_prompts() -> list[dict]:
    return build_compact_image_grid_prompts(
        [
            {
                "grid_number": 1,
                "scene_numbers": [1, 2, 3, 4],
                "scene_ids": [f"scene{index:03d}" for index in range(1, 5)],
                "shared_style": "Consistent office documentary style.",
                "panels": [
                    {
                        "scene_number": index,
                        "scene_id": f"scene{index:03d}",
                        "position": position,
                        "panel_prompt": f"Scene {index}: distinct office action beat, consistent characters and lighting.",
                    }
                    for index, position in zip(
                        range(1, 5),
                        ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                    )
                ],
            }
        ]
    )


def _ready_structure() -> dict:
    return {
        "media_prompt_status": "ready",
        "image_grid_prompt_status": "ready",
        "image_grid_prompts": _grid_prompts(),
        "scenes": [
            {
                "scene_order": index,
                "scene_id": f"scene{index:03d}",
                "scene_title": f"Scene {index}",
                "scene_summary": f"Office beat {index}.",
                "video_prompt": (
                    f"Scene {index} video prompt with a slow push-in, subject motion, ambient office motion, "
                    "stable ending pose, no dialogue, no narration, no subtitles, no captions, no music, "
                    "no sound effects, no audio."
                ),
                "media_prompt_status": "ready",
            }
            for index in range(1, 5)
        ],
    }


def test_ready_structure_uses_2x2_grid_and_video_prompts_without_scene_image_prompts():
    assert user_topics._structure_has_ready_media_prompts(_ready_structure()) is True


def test_recommendable_topic_requires_ready_2x2_grid_prompts():
    topic = {
        "status": "pending",
        "generated_title": "AI changes the office routine",
        "category_id": "cat-1",
        "pregenerated_structure_status": "ready",
        "pregenerated_structure": {
            "media_prompt_status": "ready",
            "image_grid_prompt_status": "missing",
            "scenes": [
                {
                    "scene_order": 1,
                    "scene_title": "Opening",
                    "scene_summary": "Housing anxiety opens the story.",
                    "video_prompt": "short",
                    "media_prompt_status": "ready",
                }
            ],
        },
        "pregenerated_script_status": "ready",
        "pregenerated_script": "Ready narration.",
    }

    assert user_topics._is_recommendable_topic(topic) is False


def test_pregenerated_structure_copies_video_rows_without_scene_image_prompts():
    prompts = user_topics._image_prompts_from_pregenerated_structure(_ready_structure())

    assert prompts[0]["scene_number"] == 1
    assert prompts[0]["prompt_en"] == ""
    assert prompts[0]["motion_desc"]
    assert prompts[0]["flow_prompt"] == prompts[0]["motion_desc"]
