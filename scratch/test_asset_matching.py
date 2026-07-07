import sys
import os
import uuid
from typing import Dict, Any, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.asset_upload_service import asset_upload_service
from app.services.asset_matching_service import asset_matching_service
from services.web_admin_client import web_admin_client

mock_db = {
    "projects": [{"id": "proj001"}],
    "uploaded_assets": [],
    "asset_scene_matches": []
}

mock_scenes = [
    {
        "id": "scene001",
        "scene_visual_hint": "city street at night",
        "emotion": "sad",
        "summary": "A sad woman walks alone.",
        "shot_hints": [{"emotion": "sad", "camera": "close-up"}]
    },
    {
        "id": "scene002",
        "scene_visual_hint": "sunny forest",
        "emotion": "happy",
        "summary": "A happy man runs.",
        "shot_hints": [{"emotion": "happy", "camera": "wide shot"}]
    }
]

# Override the DB client for testing
def mock_post(table, payload, **kwargs):
    if table == "uploaded_assets":
        mock_db["uploaded_assets"].append(payload)
    elif table == "asset_scene_matches":
        mock_db["asset_scene_matches"].append(payload)
    class Resp:
        status_code = 201
    return Resp()

def mock_patch(table, payload, params=None, **kwargs):
    if table == "asset_scene_matches" and params and "id" in params:
        match_id = params["id"].split(".")[-1]
        for m in mock_db["asset_scene_matches"]:
            if m["id"] == match_id:
                m.update(payload)
                break
    class Resp:
        status_code = 200
    return Resp()

web_admin_client.supabase_post = mock_post
web_admin_client.supabase_patch = mock_patch

def run_tests():
    print("=== Test 1: Upload and Metadata Extraction (Image) ===")
    res1 = asset_upload_service.process_upload(
        project_id="proj001",
        user_id="user001",
        file_name="sad_woman_city.png",
        file_type="image",
        mime_type="image/png",
        file_size=1024
    )
    assert res1["success"] is True, "Upload processing failed"
    asset1 = res1["asset"]
    assert asset1["analysis_result"]["emotion"] == "sad"
    print("Test 1 PASS\n")

    print("=== Test 2: Upload and Metadata Extraction (Video) ===")
    res2 = asset_upload_service.process_upload(
        project_id="proj001",
        user_id="user001",
        file_name="happy_man_nature.mp4",
        file_type="video",
        mime_type="video/mp4",
        file_size=2048
    )
    assert res2["success"] is True
    asset2 = res2["asset"]
    assert asset2["analysis_result"]["emotion"] == "happy"
    assert asset2["duration"] == 5.0
    print("Test 2 PASS\n")

    print("=== Test 3: Auto Scene Matching ===")
    match_res1 = asset_matching_service.auto_match_asset(asset1, mock_scenes)
    assert match_res1["success"] is True, "Auto match failed"
    match1 = match_res1["match"]
    assert match1["scene_id"] == "scene001", f"Expected scene001, got {match1['scene_id']}"
    assert match1["shot_id"] is None
    assert match1["match_score"] > 0
    
    match_res2 = asset_matching_service.auto_match_asset(asset2, mock_scenes)
    match2 = match_res2["match"]
    assert match2["scene_id"] == "scene002"
    print("Test 3 PASS\n")

    print("=== Test 4: Manual Override API ===")
    override_success = asset_matching_service.override_match(
        match_id=match1["id"],
        scene_id="scene002",
        shot_id="shot009"  # Passing shot_id to check if it's gracefully ignored or allowed
    )
    assert override_success, "Override should succeed"
    
    # Check mock DB
    updated_match = next((m for m in mock_db["asset_scene_matches"] if m["id"] == match1["id"]), None)
    assert updated_match["scene_id"] == "scene002"
    assert updated_match["user_overridden"] is True
    assert updated_match["match_status"] == "approved"
    print("Test 4 PASS\n")

    print("=== Test 5: Update Match Status ===")
    status_success = asset_matching_service.update_match_status(
        match_id=match2["id"],
        status="rejected"
    )
    assert status_success, "Status update should succeed"
    
    updated_match2 = next((m for m in mock_db["asset_scene_matches"] if m["id"] == match2["id"]), None)
    assert updated_match2["match_status"] == "rejected"
    print("Test 5 PASS\n")

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    run_tests()
