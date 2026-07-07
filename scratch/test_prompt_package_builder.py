import sys
import os
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.prompt_package_builder import prompt_package_builder_service

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
            "prompt": {"positive": "test image", "negative": "bad", "camera": "close up"}
        },
        {
            "id": "asset002",
            "shot_id": "shot002",
            "scene_id": "scene001",
            "asset_type": "video",
            "generator": "kling",
            "priority": "high",
            "prompt": {"positive": "test video", "lighting": "cinematic"}
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

def test_builder():
    print("=== Test 1: Build Package ===")
    res = prompt_package_builder_service.build_package(mock_production_plan, "test_proj_123")
    
    assert res.get("package_id"), "Package ID should be returned"
    assert res.get("package_url"), "Package URL should be returned"
    
    file_tree = res.get("file_tree", [])
    
    # Asserting structure
    assert "prompts/image/" in file_tree
    assert "prompts/video/" in file_tree
    assert "prompts/tts/" in file_tree
    assert "prompts/bgm/" in file_tree
    assert "metadata.json" in file_tree
    assert "prompts/image/shot001_image.txt" in file_tree
    assert "prompts/video/shot002_video.txt" in file_tree
    # Reuse shouldn't generate a text file
    assert "prompts/reuse/shot003_reuse.txt" not in file_tree
    
    metadata = res.get("metadata", {})
    assert metadata["project_id"] == "test_proj_123"
    assert len(metadata["items"]) == 3
    
    # Assert physical zip file properties
    package_path = res.get("package_path")
    assert os.path.exists(package_path), "ZIP file should exist"
    
    with zipfile.ZipFile(package_path, 'r') as zf:
        namelist = zf.namelist()
        assert "metadata.json" in namelist
        assert "prompts/image/shot001_image.txt" in namelist
        
        # Check text file content
        content = zf.read("prompts/image/shot001_image.txt").decode('utf-8')
        assert "test image" in content
        assert "bad" in content
        assert "close up" in content
        assert "flux" in content

    print("Test 1 PASS\n")
    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_builder()
