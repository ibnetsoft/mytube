import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.director_ai import director_ai_service

# Mock data from Script Analyzer (AIR-0204)
mock_scene_1 = {
    "scenes": [
        {
            "id": "scene001",
            "order": 1,
            "summary": "A peaceful morning establishing shot.",
            "script_text": "The sun rises over the quiet city.",
            "estimated_seconds": 6,
            "emotion": "calm",
            "visual_prompt_hint": "Sunrise over a modern city.",
            "tts_hint": {},
            "transition_hint": "fade_in"
        }
    ]
}

mock_scenes_3 = {
    "scenes": [
        {
            "id": "scene001",
            "order": 1,
            "summary": "A peaceful morning establishing shot.",
            "script_text": "The sun rises over the quiet city.",
            "estimated_seconds": 4,
            "emotion": "calm",
            "visual_prompt_hint": "Sunrise over a modern city.",
            "tts_hint": {},
            "transition_hint": "fade_in"
        },
        {
            "id": "scene002",
            "order": 2,
            "summary": "The hero wakes up.",
            "script_text": "Hero: (yawns) It's a new day.",
            "estimated_seconds": 6,
            "emotion": "sleepy",
            "visual_prompt_hint": "A young man stretches in bed.",
            "tts_hint": {"speaker_id": "char001"},
            "transition_hint": "cut"
        },
        {
            "id": "scene003",
            "order": 3,
            "summary": "The hero rushes out.",
            "script_text": "Hero: Oh no, I'm late!",
            "estimated_seconds": 5,
            "emotion": "panicked",
            "visual_prompt_hint": "A young man running frantically out the door.",
            "tts_hint": {"speaker_id": "char001"},
            "transition_hint": "cut"
        }
    ]
}

def validate_response(input_data, res):
    shots = res.get('shots', [])
    assert len(shots) > 0, "No shots generated"
    assert res.get('shot_count', 0) == len(shots), f"Shot count mismatch"
    
    # Check scene matching and durations
    for scene in input_data["scenes"]:
        scene_shots = [s for s in shots if s["scene_id"] == scene["id"]]
        assert len(scene_shots) > 0, f"No shots for {scene['id']}"
        
        sum_dur = sum(s.get("duration", 0) for s in scene_shots)
        est_sec = scene["estimated_seconds"]
        assert abs(sum_dur - est_sec) <= 2, f"Duration error for {scene['id']}: expected {est_sec}, got sum {sum_dur}"
    
    for shot in shots:
        assert shot.get("generation_type") in ["image", "video"], f"Invalid generation_type in {shot['id']}"
        assert shot.get("image_prompt") or shot.get("video_prompt"), f"Missing prompt in {shot['id']}"

async def test_director():
    print("=== Test 1: Single Scene ===")
    res1 = await director_ai_service.plan_shots(mock_scene_1)
    print(f"Shot count: {res1.get('shot_count')}")
    assert res1.get('shot_count', 0) >= 2, "1 scene should yield >= 2 shots"
    validate_response(mock_scene_1, res1)
    print("Test 1 PASS\n")

    print("=== Test 2: Three Scenes ===")
    res2 = await director_ai_service.plan_shots(mock_scenes_3)
    print(f"Shot count: {res2.get('shot_count')}")
    validate_response(mock_scenes_3, res2)
    print("Test 2 PASS\n")

    print("=== Test 3: Invalid / Empty Input ===")
    res3 = await director_ai_service.plan_shots({"invalid": "data"})
    assert res3.get('shots') == [], "Shots should be empty on fallback"
    assert res3.get('director_notes', {}).get('error') is True, "Error flag should be true"
    print("Test 3 PASS\n")

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test_director())
