import asyncio
import io

from fastapi import UploadFile

import app.routers.image as image_router
import app.utils
from services.scene_asset_matcher import (
    build_assignment_plan,
    extract_scene_number,
    find_missing_scenes,
)


def test_extract_scene_number_supports_production_filename_patterns():
    assert extract_scene_number("scene_001_upscaled.png") == 1
    assert extract_scene_number("scene_001_crop.png") == 1
    assert extract_scene_number("clip-s12-final.mp4") == 12
    assert extract_scene_number("003_result.webp") == 3
    assert extract_scene_number("final_render.mp4") is None


def test_filename_match_wins_and_ai_mapping_fills_unnumbered_files():
    assets = [
        {"original_name": "scene_02.png", "url": "/2.png", "is_video": False},
        {"original_name": "mystery.mp4", "url": "/3.mp4", "is_video": True},
    ]

    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"scene_02.png": 1, "mystery.mp4": 3},
    )

    assert [(item["scene_number"], item["match_source"]) for item in plan["matched"]] == [
        (2, "filename"),
        (3, "ai"),
    ]


def test_duplicate_occupied_and_out_of_range_assets_are_not_matched():
    assets = [
        {"original_name": "scene_01.png", "url": "/first.png", "is_video": False},
        {"original_name": "scene_01-copy.png", "url": "/second.png", "is_video": False},
        {"original_name": "scene_02.mp4", "url": "/occupied.mp4", "is_video": True},
        {"original_name": "scene_99.png", "url": "/invalid.png", "is_video": False},
    ]

    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={(2, "video"): True},
    )

    assert [item["original_name"] for item in plan["matched"]] == ["scene_01.png"]
    assert {item["reason"] for item in plan["duplicates"]} == {
        "duplicate_in_upload",
        "scene_slot_occupied",
    }
    assert plan["invalid"][0]["reason"] == "scene_out_of_range"


def test_missing_scene_report_preserves_scene_order():
    scenes = [
        {"scene_number": 1, "image_url": "/1.png", "video_url": ""},
        {"scene_number": 2, "image_url": "", "video_url": "/2.mp4"},
        {"scene_number": 3, "image_url": "", "video_url": ""},
    ]

    assert find_missing_scenes(scenes) == {
        "images": [2, 3],
        "videos": [1, 3],
    }


def test_bulk_route_assigns_numbered_file_without_ai(monkeypatch, tmp_path):
    scenes = [
        {"scene_number": 1, "image_url": "", "video_url": ""},
        {"scene_number": 2, "image_url": "", "video_url": ""},
    ]
    updates = []

    monkeypatch.setattr(image_router.db, "get_image_prompts", lambda project_id: scenes)
    monkeypatch.setattr(
        image_router.db,
        "update_image_prompt_url",
        lambda project_id, scene_number, url: updates.append((scene_number, url)),
    )
    monkeypatch.setattr(
        app.utils,
        "get_project_output_dir",
        lambda project_id: (str(tmp_path), "/output/test"),
    )

    upload = UploadFile(filename="scene_02_upscaled.png", file=io.BytesIO(b"image"))
    result = asyncio.run(image_router.bulk_match_scene_media(10, [upload]))

    assert result["matched_count"] == 1
    assert result["matched"][0]["scene_number"] == 2
    assert result["matched"][0]["match_source"] == "filename"
    assert updates[0][0] == 2


def test_direct_scene_import_can_refuse_occupied_slot(monkeypatch):
    scenes = [
        {"scene_number": 1, "image_url": "/existing.png", "video_url": ""},
    ]
    monkeypatch.setattr(image_router.db, "get_image_prompts", lambda project_id: scenes)

    upload = UploadFile(filename="scene_001_crop.png", file=io.BytesIO(b"image"))
    result = asyncio.run(
        image_router.upload_scene_media(
            project_id=10,
            scene_number=1,
            file=upload,
            replace_existing=False,
        )
    )

    assert result.status_code == 409
