import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.render_orchestrator import render_orchestrator_service

mock_production_plan = {
    "item_count": 3,
    "production_items": [
        {
            "id": "asset001",
            "shot_id": "shot001",
            "scene_id": "scene001",
            "asset_type": "image",
            "generator": "flux",
            "priority": "normal",
            "prompt": {"positive": "test image"}
        },
        {
            "id": "asset002",
            "shot_id": "shot002",
            "scene_id": "scene001",
            "asset_type": "video",
            "generator": "kling",
            "priority": "high",
            "prompt": {"positive": "test video"}
        },
        {
            "id": "asset003",
            "shot_id": "shot003",
            "scene_id": "scene002",
            "asset_type": "reuse",
            "generator": "none",
            "priority": "normal",
            "prompt": {}
        }
    ]
}

# Mocking Supabase client
class MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data
    def json(self):
        return self._json_data

def mock_supabase_post(table, payload, timeout=10):
    global mock_db
    mock_db.append(payload)
    return MockResponse(201, [payload])

def mock_supabase_get(table, params=None, timeout=10):
    global mock_db
    results = mock_db
    if params:
        if "status" in params:
            val = params["status"].split(".")[1]
            results = [r for r in results if r["status"] == val]
        if "asset_type" in params:
            val = params["asset_type"].split(".")[1]
            results = [r for r in results if r["asset_type"] == val]
    return MockResponse(200, results)

from services.web_admin_client import web_admin_client
web_admin_client.supabase_post = mock_supabase_post
web_admin_client.supabase_get = mock_supabase_get
mock_db = []

def test_orchestrator():
    print("=== Test 1: Create Render Jobs ===")
    res = render_orchestrator_service.create_render_jobs(mock_production_plan)
    assert not res.get("error"), "Should not have error"
    
    jobs = res.get("jobs", [])
    assert len(jobs) == 3, "Job count should be 3"
    assert res.get("job_count") == 3, "job_count == 3"
    
    # Check default statuses
    image_job = next(j for j in jobs if j["asset_type"] == "image")
    video_job = next(j for j in jobs if j["asset_type"] == "video")
    reuse_job = next(j for j in jobs if j["asset_type"] == "reuse")
    
    assert image_job["status"] == "queued", "Image job default status == queued"
    assert video_job["status"] == "queued", "Video job default status == queued"
    assert reuse_job["status"] == "completed", "Reuse job default status == completed"
    
    for job in jobs:
        assert job["retry_count"] == 0, "retry_count == 0"
        assert job["max_retries"] == 3, "max_retries == 3"
        assert "id" in job, "UUID should be assigned"
        
    print("Test 1 PASS\n")

    print("=== Test 2: GET Jobs with Filters ===")
    queued_jobs = render_orchestrator_service.get_render_jobs(status="queued")
    assert len(queued_jobs) == 2, "Should return 2 queued jobs"
    
    completed_jobs = render_orchestrator_service.get_render_jobs(status="completed")
    assert len(completed_jobs) == 1, "Should return 1 completed job"
    
    video_jobs = render_orchestrator_service.get_render_jobs(asset_type="video")
    assert len(video_jobs) == 1, "Should return 1 video job"
    print("Test 2 PASS\n")

    print("=== Test 3: Invalid Input Fallback ===")
    res2 = render_orchestrator_service.create_render_jobs({"invalid": "plan"})
    assert res2.get("error") is True, "Should return error flag"
    print("Test 3 PASS\n")
    
    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_orchestrator()
