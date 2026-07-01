import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.routers import video
from services import longform_asset_readiness as readiness


def test_readiness_accepts_image_or_video_and_preserves_scene_order():
    result = readiness.evaluate_scene_asset_readiness(
        [
            {"scene_number": 2, "video_url": "/scene_002.mp4"},
            {"scene_number": 1, "image_url": "/scene_001.png"},
        ]
    )

    assert result["policy"] == "image_or_video"
    assert result["scene_order"] == [1, 2]
    assert result["assets_ready"] is True
    assert result["completion_percent"] == 100
    assert result["missing_asset_scenes"] == []


def test_readiness_reports_missing_assets_gaps_and_duplicates():
    result = readiness.evaluate_scene_asset_readiness(
        [
            {"scene_number": 1, "image_url": "/scene_001.png"},
            {"scene_number": 3, "image_url": ""},
            {"scene_number": 3, "video_url": "/duplicate.mp4"},
        ]
    )

    assert result["assets_ready"] is False
    assert result["completion_percent"] == 33
    assert result["missing_asset_scenes"] == [2, 3]
    assert result["missing_scene_rows"] == [2]
    assert result["duplicate_scene_numbers"] == [3]


def test_sync_persists_ready_and_project_complete(monkeypatch):
    writes = {}
    monkeypatch.setattr(
        readiness.db,
        "get_project",
        lambda project_id: {"id": project_id, "status": "rendered"},
    )
    monkeypatch.setattr(
        readiness.db,
        "get_project_settings",
        lambda project_id: {"app_mode": "longform"},
    )
    monkeypatch.setattr(
        readiness.db,
        "get_image_prompts",
        lambda project_id: [
            {"scene_number": 1, "image_url": "/scene_001.png"},
            {"scene_number": 2, "video_url": "/scene_002.mp4"},
        ],
    )
    monkeypatch.setattr(
        readiness.db,
        "update_project_setting",
        lambda project_id, key, value: writes.__setitem__(key, value),
    )

    result = readiness.sync_project_asset_readiness(77)

    assert result["assets_ready"] is True
    assert result["project_complete"] is True
    assert writes["assets_ready"] == 1
    assert writes["asset_completion_percent"] == 100
    assert writes["project_complete"] == 1
    assert writes["assets_ready_at"]


def test_sync_skips_non_longform_projects(monkeypatch):
    monkeypatch.setattr(
        readiness.db,
        "get_project",
        lambda project_id: {"id": project_id, "status": "draft"},
    )
    monkeypatch.setattr(
        readiness.db,
        "get_project_settings",
        lambda project_id: {"app_mode": "longform_music"},
    )
    monkeypatch.setattr(
        readiness.db,
        "update_project_setting",
        lambda *args: pytest.fail("non-longform state must not be persisted"),
    )

    result = readiness.sync_project_asset_readiness(88)

    assert result["applicable"] is False
    assert result["reason"] == "not_longform"


def test_longform_render_is_blocked_when_assets_are_not_ready(monkeypatch):
    monkeypatch.setattr(video.db, "get_tts", lambda project_id: None)
    monkeypatch.setattr(
        video.db,
        "get_project_settings",
        lambda project_id: {"app_mode": "longform"},
    )
    monkeypatch.setattr(
        video,
        "sync_project_asset_readiness",
        lambda project_id: {
            "assets_ready": False,
            "completion_percent": 50,
            "missing_asset_scenes": [2],
            "duplicate_scene_numbers": [],
        },
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            video.render_project_video(
                99,
                video.RenderRequest(project_id=99),
                BackgroundTasks(),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "longform_assets_not_ready"
    assert exc.value.detail["missing_scene_numbers"] == [2]
