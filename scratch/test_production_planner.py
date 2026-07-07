import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.production_planner import production_planner_service

mock_shot_plan = {
  "shot_count": 3,
  "total_duration": 10,
  "director_notes": {
    "overall_vision": "Action-packed sequence",
    "error": False
  },
  "shots": [
    {
      "id": "shot001",
      "scene_id": "scene001",
      "order": 1,
      "duration": 3,
      "camera": "wide shot",
      "subject": "The hero standing still.",
      "composition": "rule of thirds",
      "movement": "static",
      "emotion": "determined",
      "generation_type": "image",
      "image_prompt": "Hero standing still in the city.",
      "video_prompt": "",
      "transition": "cut"
    },
    {
      "id": "shot002",
      "scene_id": "scene001",
      "order": 2,
      "duration": 5,
      "camera": "close-up",
      "subject": "The hero running fast.",
      "composition": "center framed",
      "movement": "fast pan",
      "emotion": "angry",
      "generation_type": "video",
      "image_prompt": "",
      "video_prompt": "Hero running fast in the city.",
      "transition": "cut"
    },
    {
      "id": "shot003",
      "scene_id": "scene001",
      "order": 3,
      "duration": 2,
      "camera": "wide shot",
      "subject": "The hero standing still.",
      "composition": "rule of thirds",
      "movement": "static",
      "emotion": "determined",
      "generation_type": "image",
      "image_prompt": "Hero standing still in the city.",
      "video_prompt": "",
      "transition": "cut"
    }
  ]
}

def validate_response(res):
    items = res.get('production_items', [])
    assert len(items) > 0, "No production items generated"
    assert res.get('item_count', 0) == len(items), "Item count mismatch"
    
    total_dur = sum(item.get("target_duration", 0) for item in items)
    assert res.get('total_estimated_duration') == total_dur, "Total duration mismatch"
    
    asset_types = set()
    for item in items:
        assert item.get("asset_type") in ["image", "video", "reuse"], f"Invalid asset_type in {item['id']}"
        asset_types.add(item.get("asset_type"))
        
        # Verify generator defaults
        if item["asset_type"] == "image":
            assert item["generator"] == "flux", "Default generator for image should be flux"
        elif item["asset_type"] == "video":
            assert item["generator"] == "kling", "Default generator for video should be kling"
        elif item["asset_type"] == "reuse":
            assert item["generator"] == "none", "Default generator for reuse should be none"
            
        assert item.get("prompt"), f"Missing prompt in {item['id']}"
        assert item["prompt"].get("positive"), f"Missing prompt.positive in {item['id']}"
        
        # Check shot_id match
        assert item.get("shot_id") in ["shot001", "shot002", "shot003"], f"Unknown shot_id {item['shot_id']}"
        
    print(f"Detected asset types: {asset_types}")

async def test_planner():
    print("=== Test 1: Plan Production ===")
    res1 = await production_planner_service.plan_production(mock_shot_plan)
    print(f"Item count: {res1.get('item_count')}")
    validate_response(res1)
    print("Test 1 PASS\n")

    print("=== Test 2: Invalid / Empty Input ===")
    res2 = await production_planner_service.plan_production({"invalid": "data"})
    assert res2.get('production_items') == [], "Items should be empty on fallback"
    assert res2.get('planner_notes', {}).get('error') is True, "Error flag should be true"
    print("Test 2 PASS\n")

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test_planner())
