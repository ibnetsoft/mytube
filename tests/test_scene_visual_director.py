import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from scene_visual_director import validate_directorial_plans
from directing_profiles import resolve_directing_profile


def test_directing_profile_auto_selection_and_explicit_override():
    japanese = resolve_directing_profile({
        "language": "ja", "category_name": "日本昔話", "setting_country": "日本",
    })
    webtoon = resolve_directing_profile({
        "language": "ko", "production_mode": "moving_comic", "image_style": "웹툰",
    })
    explicit = resolve_directing_profile({
        "language": "ja", "setting_country": "日本", "direction_profile": "standard",
    })

    assert japanese["id"] == "japanese_folktale"
    assert japanese["selection"] == "automatic"
    assert webtoon["id"] == "vertical_webtoon_speed"
    assert explicit["id"] == "standard"
    assert explicit["selection"] == "explicit"


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
    assert plans[0]["contract"] == "scene_direction_plan/v1"
    assert plans[0]["direction_profile"] == "standard"
    assert plans[0]["primary_effect"] == "hold"
    assert plans[0]["secondary_effects"] == []
    assert plans[0]["focus_target"]["x"] == 0.5
    assert scene["scene_direction_plan"] == plans[0]
    assert "storyboard_frames" not in plans[0]
    assert "image_fps" not in plans[0]


def test_director_normalizes_explicit_script_stage_direction_contract():
    scene = {"duration_seconds": 6}
    plan = validate_directorial_plans([scene], {"scene_directions": [{
        "scene_role": "clue_reveal",
        "dramatic_intent": "Reveal the letter without overpowering the dialogue.",
        "visual_strategy": "Move attention from the speaker to the letter, then hold.",
        "focus_target": {"type": "prop", "layer": "prop_focus", "x": 1.3, "y": -0.2,
                         "reason": "The letter contains the clue."},
        "primary_effect": "camera_move",
        "secondary_effects": ["light_flicker", "atmosphere_drift"],
        "effect_limits": {"intensity": 0.3, "speed": 0.6, "max_scale_delta": 0.03,
                          "max_move_ratio": 0.02, "max_rotation_degrees": 0.4},
        "timed_beats": [{"start_seconds": 0, "end_seconds": 6, "action": "reveal",
                          "target": "letter"}],
        "ae_operations": ["camera_move", "light_flicker", "atmosphere_drift"],
        "required_layers": [], "additional_keyframes": [],
        "qa_assertions": ["The letter remains readable and identity stays unchanged."],
    }]})[0]

    assert plan["scene_role"] == "clue_reveal"
    assert plan["primary_effect"] == "camera_move"
    assert plan["secondary_effects"] == ["light_flicker", "atmosphere_drift"]
    assert plan["focus_target"]["x"] == 1.0
    assert plan["focus_target"]["y"] == 0.0
    assert plan["effect_limits"]["max_scale_delta"] == 0.03


def test_director_schedules_selective_character_blink_with_exact_acting_cue():
    scene = {"scene_number": 19, "duration_seconds": 6, "eligible_for_eye_blink": True}
    plan = validate_directorial_plans([scene], {"scene_directions": [{
        "scene_role": "reaction",
        "dramatic_intent": "Let O-Suzu absorb the warning before answering.",
        "visual_strategy": "Hold her face and use one restrained blink on the pause.",
        "timed_beats": [{"start_seconds": 0, "end_seconds": 6, "action": "hold", "target": "O-Suzu"}],
        "ae_operations": ["hold"],
        "required_layers": [], "additional_keyframes": [],
        "qa_assertions": ["The blink occurs only once and does not change identity."],
        "eye_blink_plan": {"enabled": True, "character": "お鈴",
                           "reason": "A natural reaction on the pause before her reply.",
                           "cues": [{"at_seconds": 3.15, "duration_seconds": .12, "type": "single"}]},
    }]})[0]

    assert plan["eye_blink_plan"] == {
        "enabled": True, "character": "お鈴",
        "reason": "A natural reaction on the pause before her reply.",
        "cues": [{"at_seconds": 3.15, "duration_seconds": .12, "type": "single"}],
        "source": "scene_visual_director", "validation": "pending_final_image",
        "fallback": "skip_blink",
    }


def test_director_never_auto_blinks_uploaded_video_scenes():
    scene = {"scene_number": 12, "duration_seconds": 6, "eligible_for_eye_blink": False}
    plan = validate_directorial_plans([scene], {"scene_directions": [{
        "dramatic_intent": "Preserve the uploaded performance.",
        "visual_strategy": "Hold the submitted clip.",
        "timed_beats": [{"start_seconds": 0, "end_seconds": 6, "action": "hold", "target": "clip"}],
        "ae_operations": ["hold"], "required_layers": [], "additional_keyframes": [],
        "qa_assertions": ["Do not overlay a synthetic blink on the submitted clip."],
        "eye_blink_plan": {"enabled": True, "character": "お鈴", "reason": "reaction",
                           "cues": [{"at_seconds": 3, "duration_seconds": .12, "type": "single"}]},
    }]})[0]
    assert plan["eye_blink_plan"]["enabled"] is False
    assert plan["eye_blink_plan"]["cues"] == []
