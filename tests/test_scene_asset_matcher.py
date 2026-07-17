import asyncio
import io

from fastapi import UploadFile

import app.routers.image as image_router
import app.utils
from services.scene_asset_matcher import (
    build_assignment_plan,
    extract_scene_hint,
    extract_scene_number,
    find_missing_scenes,
)


def test_extract_scene_number_supports_production_filename_patterns():
    assert extract_scene_number("scene_001_upscaled.png") == 1
    assert extract_scene_number("scene_001_crop.png") == 1
    assert extract_scene_number("clip-s12-final.mp4") == 12
    assert extract_scene_number("003_result.webp") == 3
    assert extract_scene_number("final_render.mp4") is None


def test_extract_scene_hint_distinguishes_explicit_from_bare_number():
    assert extract_scene_hint("scene_001_upscaled.png") == (1, True)
    assert extract_scene_hint("clip-s12-final.mp4") == (12, True)
    # 순수 앞자리 숫자는 힌트일 뿐 - 외부 툴의 테이크 번호일 수 있음
    assert extract_scene_hint("003_result.webp") == (3, False)
    assert extract_scene_hint("1_final.mp4") == (1, False)
    assert extract_scene_hint("final_render.mp4") == (None, False)


def test_explicit_filename_match_commits_and_ai_high_fills_unnumbered_files():
    assets = [
        {"original_name": "scene_02.png", "url": "/2.png", "is_video": False},
        {"original_name": "mystery.mp4", "url": "/3.mp4", "is_video": True},
    ]

    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={
            "scene_02.png": {"scene": 1, "confidence": "high"},
            "mystery.mp4": {"scene": 3, "confidence": "high"},
        },
    )

    matched = {item["original_name"]: item for item in plan["matched"]}
    # 명시적 파일명은 AI 의견과 무관하게 파일명이 이긴다
    assert matched["scene_02.png"]["scene_number"] == 2
    assert matched["scene_02.png"]["match_source"] == "filename"
    assert matched["mystery.mp4"]["scene_number"] == 3
    assert matched["mystery.mp4"]["match_source"] == "ai"
    assert plan["needs_review"] == []


def test_legacy_int_ai_mapping_still_commits():
    assets = [{"original_name": "mystery.mp4", "url": "/3.mp4", "is_video": True}]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"mystery.mp4": 3},
    )
    assert plan["matched"][0]["scene_number"] == 3


def test_ai_medium_confidence_goes_to_review_not_committed():
    assets = [{"original_name": "clip.mp4", "url": "/c.mp4", "is_video": True}]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"clip.mp4": {"scene": 2, "confidence": "medium"}},
    )
    assert plan["matched"] == []
    assert plan["needs_review"][0]["scene_number"] == 2
    assert plan["needs_review"][0]["confidence"] == "medium"


def test_bare_number_without_ai_goes_to_review():
    # 외부 툴의 테이크 번호(1_final.mp4)가 무검증 확정되지 않아야 한다
    assets = [{"original_name": "1_final.mp4", "url": "/1.mp4", "is_video": True}]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
    )
    assert plan["matched"] == []
    assert plan["needs_review"][0]["scene_number"] == 1
    assert plan["needs_review"][0]["match_source"] == "filename_hint"


def test_bare_number_confirmed_by_ai_commits():
    assets = [{"original_name": "003_result.webp", "url": "/3.png", "is_video": False}]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"003_result.webp": {"scene": 3, "confidence": "high"}},
    )
    assert plan["matched"][0]["scene_number"] == 3
    assert plan["matched"][0]["match_source"] == "filename+ai"


def test_bare_number_contradicted_by_ai_goes_to_review_with_ai_suggestion():
    assets = [{"original_name": "1_final.mp4", "url": "/1.mp4", "is_video": True}]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"1_final.mp4": {"scene": 2, "confidence": "high"}},
    )
    assert plan["matched"] == []
    assert plan["needs_review"][0]["scene_number"] == 2
    assert plan["needs_review"][0]["match_source"] == "ai"


def test_explicit_filename_wins_slot_over_ai_guess_regardless_of_order():
    # AI 추측이 업로드 순서상 먼저 와도, 명시적 파일명이 슬롯을 가진다
    assets = [
        {"original_name": "guess.mp4", "url": "/g.mp4", "is_video": True},
        {"original_name": "scene_02_final.mp4", "url": "/2.mp4", "is_video": True},
    ]
    plan = build_assignment_plan(
        assets,
        valid_scene_numbers={1, 2, 3},
        existing_slots={},
        ai_mapping={"guess.mp4": {"scene": 2, "confidence": "high"}},
    )
    matched = {item["original_name"]: item for item in plan["matched"]}
    assert matched["scene_02_final.mp4"]["scene_number"] == 2
    assert "guess.mp4" not in matched
    assert plan["duplicates"][0]["original_name"] == "guess.mp4"


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


def test_assign_scene_media_endpoint_commits_reviewed_item(monkeypatch, tmp_path):
    scenes = [
        {"scene_number": 1, "image_url": "", "video_url": ""},
        {"scene_number": 2, "image_url": "", "video_url": ""},
    ]
    video_updates = []
    monkeypatch.setattr(image_router.db, "get_image_prompts", lambda project_id: scenes)
    monkeypatch.setattr(
        image_router.db,
        "update_image_prompt_video_url",
        lambda project_id, scene_number, url: video_updates.append((scene_number, url)),
    )
    monkeypatch.setattr(
        image_router, "sync_project_asset_readiness", lambda project_id: {"ready": False}
    )
    # 저장된 프로젝트 파일처럼 보이도록 경로 해석을 스텁
    monkeypatch.setattr(
        image_router, "_resolve_output_url_to_path", lambda url: str(tmp_path / "f.mp4")
    )

    result = asyncio.run(
        image_router.assign_scene_media(
            project_id=10,
            scene_number=2,
            url="/output/test/bulk_vid_x.mp4",
            is_video=True,
            replace_existing=False,
        )
    )

    assert result["status"] == "ok"
    assert video_updates == [(2, "/output/test/bulk_vid_x.mp4")]


def test_assign_scene_media_rejects_non_project_url(monkeypatch):
    result = asyncio.run(
        image_router.assign_scene_media(
            project_id=10,
            scene_number=1,
            url="https://evil.example.com/x.mp4",
            is_video=True,
            replace_existing=False,
        )
    )
    assert result.status_code == 400
