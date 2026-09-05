import json
import sys
from pathlib import Path

from app.routers import image, user_topics
from services.image_grid_prompts import (
    build_compact_image_grid_prompts,
    build_image_grid_prompts,
    normalize_image_grid_prompts,
    validate_image_grid_prompt_readiness,
)


def test_compact_grid_merges_required_guardrails_into_ai_negative_prompt():
    grid = build_compact_image_grid_prompts([{
        "grid_number": 1,
        "scene_numbers": [1, 2, 3, 4],
        "negative_prompt": "avoid blur",
        "panels": [
            {"scene_number": number, "panel_prompt": f"Distinct scene {number} with a clear subject and action."}
            for number in range(1, 5)
        ],
    }])[0]

    assert "avoid blur" in grid["prompt"]
    for required in ("no text", "no words", "no letters", "no captions", "no watermarks"):
        assert required in grid["prompt"].lower()

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
from worker import hermes_worker


def _scenes(count: int) -> list[dict]:
    return [
        {
            "scene_id": f"scene{number:03d}",
            "scene_order": number,
            "scene_situation": f"Detailed story beat for scene {number}.",
            "scene_summary": f"Scene {number} summary.",
        }
        for number in range(1, count + 1)
    ]


def test_grid_prompts_add_overlapping_final_block_for_tail_scenes():
    grids = build_image_grid_prompts(_scenes(9))

    assert len(grids) == 3
    assert grids[0]["scene_numbers"] == [1, 2, 3, 4]
    assert grids[1]["scene_numbers"] == [5, 6, 7, 8]
    assert grids[2]["scene_numbers"] == [6, 7, 8, 9]
    assert grids[0]["panel_count"] == 4
    assert "Panel 4 (Position: Bottom-Right)" in grids[0]["prompt"]
    assert "scene 5" not in grids[0]["prompt"]
    assert "NO borders" in grids[0]["prompt"]


def test_grid_prompts_cover_scene_53_with_final_last_four_window():
    grids = build_image_grid_prompts(_scenes(53))

    assert len(grids) == 14
    assert grids[-2]["scene_numbers"] == [49, 50, 51, 52]
    assert grids[-1]["scene_numbers"] == [50, 51, 52, 53]


def test_compact_grid_prompts_use_panel_briefs_instead_of_full_scene_prompts():
    scenes = _scenes(4)
    for scene in scenes:
        scene["scene_situation"] = scene["scene_situation"] + " " + ("full scene detail " * 80)
    composed = build_image_grid_prompts(scenes)[0]["prompt"]
    compact = build_compact_image_grid_prompts([
        {
            "grid_number": 1,
            "scene_numbers": [1, 2, 3, 4],
            "shared_style": "Consistent character design, wardrobe, lighting, palette, and camera language.",
            "panels": [
                {
                    "scene_number": number,
                    "scene_id": f"scene{number:03d}",
                    "position": position,
                    "panel_prompt": f"Scene {number}: a concise unique action beat with subject, setting, emotion, and one prop.",
                }
                for number, position in zip(
                    range(1, 5),
                    ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                )
            ],
        }
    ])[0]

    assert compact["template"] == "strict_2x2_compact_v1"
    assert compact["scene_numbers"] == [1, 2, 3, 4]
    assert len(compact["prompt"]) < len(composed)
    assert compact["prompt"].count("Negative guardrails") == 1
    assert "full scene detail" not in compact["prompt"]
    validate_image_grid_prompt_readiness(scenes, [compact], status="ready", require_status="ready")


def test_worker_character_anchors_are_injected_into_compact_grid_prompts():
    context = hermes_worker._character_anchors_context(
        {
            "name": "Minseo",
            "role": "protagonist",
            "visual_dna_en": "Korean woman in her 60s, oval face, silver bob hair, tired but kind eyes",
            "wardrobe_en": "navy cardigan and cream blouse",
            "continuity_instruction": "Keep Minseo's face, hair, and navy cardigan identical in every scene.",
        },
        [
            {
                "name": "Joonho",
                "role": "son",
                "visual_dna_en": "Korean man in his 30s, square jaw, short black hair",
                "wardrobe_en": "gray office jacket",
                "continuity_instruction": "Keep Joonho's face, hair, and gray jacket identical in every scene.",
            }
        ],
    )
    grids = build_compact_image_grid_prompts([
        {
            "grid_number": 1,
            "scene_numbers": [1, 2, 3, 4],
            "scene_ids": [f"scene{index:03d}" for index in range(1, 5)],
            "shared_style": f"Character DNA anchors: {context}",
            "panels": [
                {
                    "scene_number": number,
                    "scene_id": f"scene{number:03d}",
                    "position": position,
                    "panel_prompt": f"Scene {number}: Minseo and Joonho in a concrete story beat.",
                }
                for number, position in zip(
                    range(1, 5),
                    ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                )
            ],
        }
    ])

    prompt = grids[0]["prompt"]
    assert "Minseo" in prompt
    assert "Joonho" in prompt
    assert "silver bob hair" in prompt
    assert "gray office jacket" in prompt


def test_worker_aligns_generated_media_chunk_to_input_scene_identity():
    aligned = hermes_worker._align_generated_media_chunk(
        _scenes(3),
        [
            {"scene_id": "scene001", "scene_order": 1, "video_prompt": "one"},
            {"scene_id": "scene001", "scene_order": 1, "video_prompt": "two"},
            {"scene_id": "scene001", "scene_order": 1, "video_prompt": "three"},
        ],
        "1-3 of 3",
    )

    assert [scene["scene_id"] for scene in aligned] == ["scene001", "scene002", "scene003"]
    assert [scene["scene_order"] for scene in aligned] == [1, 2, 3]
    assert [scene["video_prompt"] for scene in aligned] == ["one", "two", "three"]


def test_validate_grid_prompts_requires_tail_coverage():
    scenes = _scenes(9)
    old_complete_blocks_only = build_image_grid_prompts(_scenes(8))

    try:
        validate_image_grid_prompt_readiness(scenes, old_complete_blocks_only, status="ready", require_status="ready")
    except ValueError as exc:
        assert "do not cover" in str(exc) or "count mismatch" in str(exc)
    else:
        raise AssertionError("tail scene coverage should be required")

    validate_image_grid_prompt_readiness(scenes, build_image_grid_prompts(scenes), status="ready", require_status="ready")


def test_validate_grid_prompts_can_require_direct_compact_template():
    scenes = _scenes(4)
    legacy_grid = build_image_grid_prompts(scenes)

    try:
        validate_image_grid_prompt_readiness(
            scenes,
            legacy_grid,
            status="ready",
            require_status="ready",
            require_compact_template=True,
        )
    except ValueError as exc:
        assert "strict_2x2_compact_v1" in str(exc)
    else:
        raise AssertionError("legacy scene-composed grid prompts should be rejected when compact template is required")


def test_normalize_grid_prompts_discards_partial_or_invalid_records():
    valid = build_image_grid_prompts(_scenes(4))[0]
    invalid = {
        "scene_numbers": [5, 6, 7],
        "panel_count": 3,
        "prompt": "partial grid",
    }

    assert normalize_image_grid_prompts([invalid, valid]) == [valid]


def test_prepared_topic_copy_preserves_worker_grid_prompts(monkeypatch):
    worker_grids = build_compact_image_grid_prompts([
        {
            "grid_number": 1,
            "scene_numbers": [1, 2, 3, 4],
            "scene_ids": [f"scene{index:03d}" for index in range(1, 5)],
            "shared_style": "Consistent character design, wardrobe, lighting, palette, and camera language.",
            "panels": [
                {
                    "scene_number": number,
                    "scene_id": f"scene{number:03d}",
                    "position": position,
                    "panel_prompt": f"Scene {number}: a concise unique action beat with subject, setting, emotion, and one prop.",
                }
                for number, position in zip(
                    range(1, 5),
                    ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                )
            ],
        }
    ])
    stored_settings: dict[str, str] = {}

    monkeypatch.setattr(
        user_topics.db,
        "update_project_setting",
        lambda _project_id, key, value: stored_settings.__setitem__(key, value),
    )
    monkeypatch.setattr(user_topics.db, "save_script_structure", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_topics.db, "save_image_prompts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_topics.db, "update_project", lambda *_args, **_kwargs: None)

    user_topics._copy_prepared_topic_assets_to_project(
        12,
        {
            "pregenerated_structure": {
                "media_prompt_status": "ready",
                "image_grid_prompt_status": "ready",
                "scenes": _scenes(4),
                "image_grid_prompts": worker_grids,
            },
        },
    )

    normalized_worker_grids = normalize_image_grid_prompts(worker_grids)
    assert json.loads(stored_settings["image_grid_prompts_json"]) == normalized_worker_grids
    structure = json.loads(stored_settings["pregenerated_structure_json"])
    assert structure["image_grid_prompts"] == normalized_worker_grids


def test_image_api_persists_rebuilt_grid_prompts(monkeypatch):
    stored_settings: dict[str, str] = {}

    monkeypatch.setattr(
        image.db,
        "update_project_setting",
        lambda _project_id, key, value: stored_settings.__setitem__(key, value),
    )

    grids = image._persist_image_grid_prompts(33, _scenes(4))

    assert json.loads(stored_settings["image_grid_prompts_json"]) == grids
    assert grids[0]["scene_numbers"] == [1, 2, 3, 4]


def test_image_api_does_not_rebuild_grid_prompts_when_loading_without_saved_grids(monkeypatch):
    monkeypatch.setattr(image.db, "get_project_settings", lambda _project_id: {})

    assert image._load_image_grid_prompts(33, _scenes(4)) == []


def test_worker_rebuilds_missing_ai_grid_prompt_windows():
    class FakeRouter:
        def __init__(self):
            self.calls = 0

        async def generate_text(self, *_args, **_kwargs):
            self.calls += 1
            grid_number = self.calls
            return json.dumps({
                "grids": [
                    {
                        "grid_number": grid_number,
                        "scene_numbers": list(range((grid_number - 1) * 4 + 1, grid_number * 4 + 1)),
                        "scene_ids": [f"scene{number:03d}" for number in range((grid_number - 1) * 4 + 1, grid_number * 4 + 1)],
                        "shared_style": "consistent style",
                        "panels": [
                            {
                                "scene_number": number,
                                "scene_id": f"scene{number:03d}",
                                "position": position,
                                "panel_prompt": (
                                    f"Scene {number}: a distinct subject performs a specific action in a period setting, "
                                    "with clear composition, emotional body language, natural light, and one unique prop."
                                ),
                            }
                                for number, position in zip(
                                    range((grid_number - 1) * 4 + 1, grid_number * 4 + 1),
                                    ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                                )
                            ],
                        }
                    ]
                })

    class FakeLog:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    scenes = [
        {
            "scene_id": f"scene{number:03d}",
            "scene_order": number,
            "scene_summary": f"Summary {number}",
            "scene_situation": f"Situation {number}",
            "scene_emotion": "tense",
            "script_excerpt": f"Narration excerpt {number}",
        }
        for number in range(1, 9)
    ]

    checkpoints = []
    grids = hermes_worker._generate_direct_image_grid_prompts(
        FakeRouter(),
        "fake-model",
        "topic",
        "upload title",
        scenes,
        {},
        "3d_render",
        "cinematic Korean period style",
        FakeLog(),
        checkpoint_callback=lambda **event: checkpoints.append(event),
    )

    assert len(grids) == 2
    assert [grid["scene_numbers"] for grid in grids] == [[1, 2, 3, 4], [5, 6, 7, 8]]
    assert all(grid["template"] == "strict_2x2_compact_v1" for grid in grids)
    grid_checkpoints = [event for event in checkpoints if event["stage"] == "image_grid_prompt"]
    scene_checkpoints = [event for event in checkpoints if event["stage"] == "image_prompt"]
    assert [event["scene_numbers"] for event in grid_checkpoints] == [[1, 2, 3, 4], [5, 6, 7, 8]]
    assert [event["scene_numbers"] for event in scene_checkpoints] == [[1], [2], [3], [4], [5], [6], [7], [8]]
    assert all(event["status"] == "ready" for event in checkpoints)


def test_worker_resumes_image_grids_after_last_saved_grid():
    class ResumeRouter:
        def __init__(self):
            self.calls = 0

        async def generate_text(self, *_args, **_kwargs):
            self.calls += 1
            return json.dumps({"grids": [_grid_spec(2)]})

    class FakeLog:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    def _grid_spec(grid_number):
        numbers = list(range((grid_number - 1) * 4 + 1, grid_number * 4 + 1))
        return {
            "grid_number": grid_number,
            "scene_numbers": numbers,
            "scene_ids": [f"scene{number:03d}" for number in numbers],
            "shared_style": "consistent period documentary style with stable wardrobe and natural lighting",
            "negative_prompt": "no text, no words, no letters, no captions, no watermarks",
            "panels": [
                {
                    "scene_number": number,
                    "scene_id": f"scene{number:03d}",
                    "position": position,
                    "panel_prompt": (
                        f"Scene {number}: a distinct subject performs a specific action in a period village, "
                        "with emotional body language, natural light, clear composition, and a unique prop."
                    ),
                }
                for number, position in zip(numbers, ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"])
            ],
        }

    scenes = _scenes(8)
    existing_grid = build_compact_image_grid_prompts([_grid_spec(1)])[0]
    router = ResumeRouter()
    grids = hermes_worker._generate_direct_image_grid_prompts(
        router,
        "fake-model",
        "topic",
        "upload title",
        scenes,
        {},
        "watercolor",
        "soft documentary watercolor style",
        FakeLog(),
        existing_grids=[existing_grid],
    )

    assert router.calls == 1
    assert [grid["grid_number"] for grid in grids] == [1, 2]


def test_worker_rejects_image_grid_prompts_when_ai_json_remains_malformed():
    class FakeRouter:
        async def generate_text(self, *_args, **_kwargs):
            return '{"grids": [{"grid_number": 1, "scene_numbers": [1, 2, 3, 4]'

    class FakeLog:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    scenes = [
        {
            "scene_id": f"scene{number:03d}",
            "scene_order": number,
            "scene_summary": f"Summary {number}",
            "scene_situation": f"Situation {number}",
            "scene_emotion": "tense",
            "script_excerpt": f"Narration excerpt {number}",
        }
        for number in range(1, 9)
    ]

    import pytest

    with pytest.raises(ValueError, match="failed after retry"):
        hermes_worker._generate_direct_image_grid_prompts(
            FakeRouter(),
            "fake-model",
            "topic",
            "upload title",
            scenes,
            {},
            "watercolor",
            "soft documentary watercolor style",
            FakeLog(),
        )


def test_worker_generates_large_image_grid_sets_in_bounded_ai_batches():
    class BatchedRouter:
        def __init__(self):
            self.calls = 0

        async def generate_text(self, *_args, **_kwargs):
            self.calls += 1
            grid_number = self.calls
            return json.dumps({
                "grids": [
                    {
                        "grid_number": grid_number,
                        "scene_numbers": list(range((grid_number - 1) * 4 + 1, grid_number * 4 + 1)),
                        "scene_ids": [f"scene{number:03d}" for number in range((grid_number - 1) * 4 + 1, grid_number * 4 + 1)],
                        "shared_style": "consistent period documentary style with stable characters and wardrobe",
                        "panels": [
                            {
                                "scene_number": number,
                                "scene_id": f"scene{number:03d}",
                                "position": position,
                                "panel_prompt": (
                                    f"Scene {number}: a distinct subject performs a specific action in a period setting, "
                                    "with clear composition, emotional body language, natural light, and one unique prop."
                                ),
                            }
                            for number, position in zip(
                                range((grid_number - 1) * 4 + 1, grid_number * 4 + 1),
                                ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"],
                            )
                        ],
                    }
                ]
            })

    class FakeLog:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    scenes = [
        {
            "scene_id": f"scene{number:03d}",
            "scene_order": number,
            "scene_summary": f"Summary {number}",
            "scene_situation": f"Situation {number}",
            "scene_emotion": "tense",
            "script_excerpt": f"Narration excerpt {number}",
        }
        for number in range(1, 53)
    ]

    router = BatchedRouter()
    grids = hermes_worker._generate_direct_image_grid_prompts(
        router,
        "fake-model",
        "topic",
        "upload title",
        scenes,
        {},
        "watercolor",
        "soft documentary watercolor style",
        FakeLog(),
    )

    assert len(grids) == 13
    assert router.calls == 13
    assert grids[-1]["scene_numbers"] == [49, 50, 51, 52]
    validate_image_grid_prompt_readiness(scenes, grids, status="ready", require_status="ready")
