import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from scene_visual_director import validate_directorial_plans


def test_director_accepts_video_first_plan_without_generated_storyboard():
    scene = {"duration_seconds": 7}
    plans = validate_directorial_plans([scene], {
        "scene_directions": [{
            "dramatic_intent": "Hold on the reunion before the reply.",
            "visual_strategy": "Preserve the uploaded framing and let the pause carry the beat.",
            "source_video_reviewed": True,
            "timed_beats": [{
                "start_seconds": 0, "end_seconds": 7,
                "action": "hold", "target": "the two characters",
            }],
            "ae_operations": ["hold"],
            "required_layers": [],
            "additional_keyframes": [],
            "qa_assertions": ["Keep character identity and clothing unchanged."],
        }],
    })

    assert plans[0]["source_video_review_status"] == "reviewed"
    assert plans[0]["required_layers"] == []
    assert "storyboard_frames" not in plans[0]
    assert "image_fps" not in plans[0]
