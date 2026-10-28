import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))

import ae_highlight_worker as ae
import codex_content_runner as planner


def test_strong_action_scene_selects_webtoon_impact_without_matching_plain_dialogue():
    action = {"scene_number": 1, "duration_seconds": 5, "narration": "그가 검을 내리쳤고 바닥과 충돌했다."}
    dialogue = {"scene_number": 2, "duration_seconds": 5, "narration": "두 사람은 조용히 이야기를 나누었다."}

    plans = planner._plan_ae_effects_for_scenes([action, dialogue], {})

    assert plans[0]["preset"] == "webtoon_impact_beat_v1"
    assert action["ae_effect_plan"]["enabled"] is True
    assert action["ae_effect_plan"]["impact"]["at_seconds"] == 1.9
    assert dialogue["ae_effect_plan"]["enabled"] is False


def test_explicit_webtoon_impact_parameters_are_clamped():
    scene = {
        "scene_number": 4,
        "duration_seconds": 2,
        "narration": "잠시 멈춘다.",
        "ae_effect_preset": "webtoon_impact_beat_v1",
        "ae_effect_parameters": {"impact": {
            "at_seconds": 99, "x": -3, "y": 4, "direction": "diagonal", "intensity": 8,
        }},
    }

    planner._plan_ae_effects_for_scenes([scene], {})

    impact = scene["ae_effect_plan"]["impact"]
    assert impact == {"at_seconds": 1.35, "x": 0.05, "y": 0.95,
                      "direction": "center_out", "intensity": 1.0}


def test_webtoon_impact_can_augment_an_existing_directorial_plan():
    scene = {
        "scene_number": 7,
        "duration_seconds": 4,
        "narration": "주먹이 정면으로 강타했다.",
        "scene_direction_plan": {"scene_role": "action", "primary_effect": "slow_push_in"},
    }

    planner._plan_ae_effects_for_scenes([scene], {})

    assert scene["ae_effect_plan"]["enabled"] is True
    assert scene["ae_effect_plan"]["preset"] == "webtoon_impact_beat_v1"


def test_webtoon_impact_jsx_uses_scene_trigger_for_flash_hold_and_shake(tmp_path):
    scene = {"scene_number": 3, "ae_effect_plan": {
        "enabled": True,
        "preset": "webtoon_impact_beat_v1",
        "duration_seconds": 5,
        "vfx": ["speedline_burst", "impact_camera_shake", "flash_cut", "impact_hold"],
        "targets": [{"type": "impact_focus", "x": 0.61, "y": 0.43}],
        "impact": {"at_seconds": 3.42, "direction": "left_to_right"},
        "motion": {"push": 0.055, "shake": 0.025},
        "intensity": 0.72,
    }}
    job = ae.SceneJob("topic", "webtoon", {"scenes": [scene]}, 0, scene, 3,
                      "effect", "webtoon_impact_beat_v1", 5.0,
                      ae.GcsRef("bucket", "scene.png"))
    jsx_path = tmp_path / "impact.jsx"

    ae._write_jsx(job, tmp_path / "scene.png", tmp_path / "project.aep",
                  tmp_path / "render.mp4", jsx_path)
    jsx = jsx_path.read_text(encoding="utf-8")
    plan_line = next(line for line in jsx.splitlines() if line.startswith("var PLAN = "))
    plan = json.loads(plan_line.removeprefix("var PLAN = ").removesuffix(";"))

    assert plan["impact_at"] == 3.42
    assert plan["impact_direction"] == "left_to_right"
    assert plan["intensity"] == 0.72
    assert 'PLAN.preset == "webtoon_impact_beat_v1"' in jsx
    assert 'bg.property("Scale").setValueAtTime(IMPACT_AT' in jsx
    assert 'setOpacity(pulse, Math.max(0, IMPACT_AT - 0.04)' in jsx
    assert '"webtoon_impact_ring"' in jsx


def test_webtoon_speech_bubble_plan_accepts_metadata_and_normalizes_values():
    scene = {"scene_number": 8, "duration_seconds": 4, "metadata": {"ae_speech_bubbles": {
        "enabled": True,
        "bubbles": [{"text": "  네가 범인이었구나!  ", "position": [2, -1],
                     "style": "shout", "tail": "right", "start_seconds": -3, "end_seconds": 99}],
    }}}

    planner._plan_ae_effects_for_scenes([scene], {})

    plan = scene["ae_effect_plan"]
    assert plan["preset"] == "webtoon_speech_bubble_v1"
    assert plan["speech_bubbles"]["bubbles"][0] == {
        "text": "네가 범인이었구나!", "speaker": "", "position": [0.84, 0.14],
        "style": "shout", "tail": "right", "start_seconds": 0.0, "end_seconds": 4.0,
    }


def test_webtoon_speech_bubble_jsx_creates_box_tail_and_text(tmp_path):
    bubble = {"enabled": True, "bubbles": [{"text": "멈춰!", "speaker": "주인공",
        "position": [0.7, 0.2], "style": "dialogue", "tail": "left",
        "start_seconds": 0.2, "end_seconds": 3.5}]}
    scene = {"scene_number": 9, "ae_effect_plan": {"enabled": True,
        "preset": "webtoon_speech_bubble_v1", "duration_seconds": 4,
        "vfx": ["webtoon_speech_bubbles"], "speech_bubbles": bubble,
        "motion": {"push": 0.015, "shake": 0}, "intensity": 0.5}}
    job = ae.SceneJob("topic", "comic", {"scenes": [scene]}, 0, scene, 9,
                      "effect", "webtoon_speech_bubble_v1", 4.0, ae.GcsRef("bucket", "scene.png"))
    jsx_path = tmp_path / "bubble.jsx"

    ae._write_jsx(job, tmp_path / "scene.png", tmp_path / "project.aep",
                  tmp_path / "render.mp4", jsx_path)
    jsx = jsx_path.read_text(encoding="utf-8")

    assert "makeWebtoonSpeechBubbles(comp)" in jsx
    assert 'comp.layers.addText(textValue)' in jsx
    assert 'webtoon_bubble_tail_' in jsx
    assert "멈춰!" not in jsx  # JSON is ASCII escaped so ExtendScript reads it safely.


def test_webtoon_speech_bubble_auto_style_uses_scene_situation():
    scene = {"scene_number": 10, "duration_seconds": 3, "scene_situation": "비밀을 조용히 속삭인다",
             "ae_speech_bubbles": {"enabled": True, "bubbles": [{"text": "아무에게도 말하지 마.", "style": "auto"}]}}

    planner._plan_ae_effects_for_scenes([scene], {})

    assert scene["ae_effect_plan"]["speech_bubbles"]["bubbles"][0]["style"] == "whisper"
