import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.asset_upload_service import asset_upload_service
from app.services.asset_matching_service import asset_matching_service
from services.web_admin_client import web_admin_client

# --- Mock Supabase Client ---
class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or []
    def json(self):
        return self._json_data

mock_db = {"uploaded_assets": [], "asset_scene_matches": []}

def mock_supabase_post(table, payload, timeout=10):
    global mock_db
    mock_db[table].append(payload)
    return MockResponse(201, [payload])

def mock_supabase_get(table, params=None, timeout=10):
    global mock_db
    return MockResponse(200, mock_db[table])

def mock_supabase_patch(table, payload, params=None, timeout=10):
    global mock_db
    # Simplified mock update
    if "id" in params:
        match_id = params["id"].split(".")[1]
        for row in mock_db[table]:
            if row.get("id") == match_id:
                row.update(payload)
                return MockResponse(200, [row])
    return MockResponse(404)

web_admin_client.supabase_post = mock_supabase_post
web_admin_client.supabase_get = mock_supabase_get
web_admin_client.supabase_patch = mock_supabase_patch
# ----------------------------

mock_shots = [
    {
        "id": "shot001",
        "scene_id": "scene001",
        "subject": "woman",
        "emotion": "sad",
        "camera": "close up",
        "scene_visual_hint": "city street"
    },
    {
        "id": "shot002",
        "scene_id": "scene001",
        "subject": "man",
        "emotion": "happy",
        "camera": "wide",
        "scene_visual_hint": "forest"
    }
]

def test_asset_matching():
    print("=== Test 1: Upload and Metadata Extraction (Image) ===")
    res1 = asset_upload_service.process_upload(
        project_id="test_proj_1",
        user_id="test_user_1",
        file_name="sad_woman_in_city.jpg",
        file_type="image",
        mime_type="image/jpeg",
        file_size=102400
    )
    assert res1["success"], "Upload should succeed"
    asset1 = res1["asset"]
    assert asset1["file_type"] == "image"
    assert asset1["duration"] is None
    analysis1 = asset1["analysis_result"]
    assert "woman" in analysis1["subjects"]
    assert analysis1["emotion"] == "sad"
    assert "city" in analysis1["background"]
    print("Test 1 PASS\n")

    print("=== Test 2: Upload and Metadata Extraction (Video) ===")
    res2 = asset_upload_service.process_upload(
        project_id="test_proj_1",
        user_id="test_user_1",
        file_name="happy_man_forest.mp4",
        file_type="video",
        mime_type="video/mp4",
        file_size=5000000
    )
    assert res2["success"], "Upload should succeed"
    asset2 = res2["asset"]
    assert asset2["file_type"] == "video"
    assert asset2["duration"] == 5.0
    analysis2 = asset2["analysis_result"]
    assert "man" in analysis2["subjects"]
    assert analysis2["emotion"] == "happy"
    assert "forest" in analysis2["background"]
    print("Test 2 PASS\n")

    print("=== Test 3: Auto Scene/Shot Matching ===")
    match_res1 = asset_matching_service.auto_match_asset(asset1, mock_shots)
    assert match_res1["success"], "Matching should succeed"
    match1 = match_res1["match"]
    assert match1["shot_id"] == "shot001", "Should match shot001 (sad woman city)"
    
    match_res2 = asset_matching_service.auto_match_asset(asset2, mock_shots)
    assert match_res2["success"], "Matching should succeed"
    match2 = match_res2["match"]
    assert match2["shot_id"] == "shot002", "Should match shot002 (happy man forest)"
    print("Test 3 PASS\n")

    print("=== Test 4: Manual Override API ===")
    override_success = asset_matching_service.override_match(
        match_id=match1["id"],
        scene_id="scene002",
        shot_id="shot009"
    )
    assert override_success, "Override should succeed"
    
    # Check mock DB
    updated_match = next((m for m in mock_db["asset_scene_matches"] if m["id"] == match1["id"]), None)
    assert updated_match["scene_id"] == "scene002"
    assert updated_match["shot_id"] == "shot009"
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
    test_asset_matching()
