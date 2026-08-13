import json

from app.routers import image, user_topics
from services.image_grid_prompts import (
    build_image_grid_prompts,
    normalize_image_grid_prompts,
)


def _scenes(count: int) -> list[dict]:
    return [
        {
            "scene_id": f"scene{number:03d}",
            "scene_order": number,
            "image_prompt": f"Detailed image prompt for scene {number}.",
        }
        for number in range(1, count + 1)
    ]


def test_grid_prompts_use_only_complete_four_scene_blocks():
    grids = build_image_grid_prompts(_scenes(9))

    assert len(grids) == 2
    assert grids[0]["scene_numbers"] == [1, 2, 3, 4]
    assert grids[1]["scene_numbers"] == [5, 6, 7, 8]
    assert grids[0]["panel_count"] == 4
    assert "Panel 4 (Position: Bottom-Right)" in grids[0]["prompt"]
    assert "scene 5" not in grids[0]["prompt"]
    assert "NO borders" in grids[0]["prompt"]


def test_normalize_grid_prompts_discards_partial_or_invalid_records():
    valid = build_image_grid_prompts(_scenes(4))[0]
    invalid = {
        "scene_numbers": [5, 6, 7],
        "panel_count": 3,
        "prompt": "partial grid",
    }

    assert normalize_image_grid_prompts([invalid, valid]) == [valid]


def test_prepared_topic_copy_preserves_worker_grid_prompts(monkeypatch):
    worker_grids = build_image_grid_prompts(_scenes(4))
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
                "scenes": _scenes(4),
                "image_grid_prompts": worker_grids,
            },
        },
    )

    assert json.loads(stored_settings["image_grid_prompts_json"]) == worker_grids
    structure = json.loads(stored_settings["pregenerated_structure_json"])
    assert structure["image_grid_prompts"] == worker_grids


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
