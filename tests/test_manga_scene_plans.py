"""Script-stage contracts for the dedicated manga motion templates."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "worker") not in sys.path:
    sys.path.insert(0, str(ROOT / "worker"))

import codex_content_runner as runner
import manga_scene_qa as scene_qa


def _scene(number: int, summary: str) -> dict:
    return {
        "scene_order": number,
        "duration_seconds": 5,
        "scene_summary": summary,
        "image_prompt": "A layered Korean martial arts comic composition with clean individual elements.",
    }


def test_three_manga_templates_produce_timed_geometry_and_required_layers():
    scenes = [
        _scene(1, "세 사람은 서로 대치하며 놀란 표정으로 반응했다."),
        _scene(2, "부적이 몸에 닿자 보랏빛 기운이 혈맥을 따라 흘렀다."),
        {**_scene(3, "부적이 가슴에 부딪혀 강한 충격과 먹물 폭발이 터졌다."), "impact_text": "뻥!"},
    ]

    plans = runner._plan_ae_effects_for_scenes(scenes, {"category": "무협"})

    assert len(plans) == 3
    by_template = {scene["ae_effect_plan"]["template"]: scene["ae_effect_plan"] for scene in scenes}
    assert set(by_template) == {"angled_triple_reaction", "body_following_qi", "ink_splat_impact"}
    triple = by_template["angled_triple_reaction"]
    assert [panel["role"] for panel in triple["panels"]] == ["character_left", "character_center", "character_right"]
    assert all(len(panel["polygon"]) == 4 and 0 <= panel["enter_at"] < 5 for panel in triple["panels"])
    reaction = next(beat for beat in triple["beats"] if beat["action"] == "reaction_push")
    bubble = next(beat for beat in triple["beats"] if beat["action"] == "speech_bubble")
    assert bubble["text"] == "?!" and bubble["at_seconds"] >= reaction["at_seconds"]
    assert triple["asset_requirements"]["required_layers"] == ["background", "character_left", "character_center", "character_right"]
    qi = by_template["body_following_qi"]
    assert len(qi["qi_path"]) == 5
    assert qi["talisman_target"] == [0.5, 0.6]
    assert any(beat["action"] == "qi_trace_start" for beat in qi["beats"])
    assert qi["asset_requirements"]["required_layers"] == ["background", "character", "talisman"]
    impact = by_template["ink_splat_impact"]
    assert impact["impact"] == {"x": 0.51, "y": 0.56, "at_seconds": 1.9, "text": "뻥!"}
    assert next(beat for beat in impact["beats"] if beat["action"] == "onomatopoeia")["text"] == "뻥!"
    assert all(0 <= beat["at_seconds"] < 5 for plan in by_template.values() for beat in plan["beats"])

    runner._plan_ae_motion_for_scenes(scenes, {"category": "무협"})
    policy = runner._plan_image_generation_efficiency(scenes, {"category": "무협"}, plans)
    assert policy["psd_layer_scene_count"] == 3
    assert [scene["psd_layer_plan"]["outputs"] for scene in scenes] == [
        ["background", "character_left", "character_center", "character_right"],
        ["background", "character", "talisman", "qi_overlay"],
        ["background", "character", "talisman", "ink_splat"],
    ]
    assert all(scene["psd_layer_plan"]["enabled"] for scene in scenes)
    assert all(scene["image_generation_policy"]["psd_layer_package_reason"] == "ae_manga_template_required" for scene in scenes)
    assert "Top-Right left character cutout" in scenes[0]["psd_layer_plan"]["prompt"]
    assert "talisman prop cutout" in scenes[1]["psd_layer_plan"]["prompt"]
    for scene in scenes:
        required = scene["ae_effect_plan"]["asset_requirements"]["required_layers"]
        asset = {"gcs_path": "scene.psd", "layer_names": required}
        assert scene_qa.validate_scene_plan(scene, asset, 5)["passed"] is True


def test_visual_director_layered_performance_routes_timed_poses_to_ae_assets():
    scene = {
        **_scene(19, "Daigoro wakes in pain, looks toward the shoji, then closes his eyes again."),
        "ae_directorial_plan": {
            "dramatic_intent": "Show the lonely cycle of pain, checking the quiet room, and returning to sleep.",
            "visual_strategy": "Crossfade aligned poses only at the three narrated action beats.",
            "requires_layered_assets": True,
            "required_layers": ["background", "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "shoji"],
            "timed_beats": [
                {"start_seconds": 0, "end_seconds": 1.0, "action": "pose_reveal", "target": "pose_sleeping"},
                {"start_seconds": 1.0, "end_seconds": 2.6, "action": "pose_reveal", "target": "pose_waking"},
                {"start_seconds": 2.6, "end_seconds": 4.8, "action": "pose_reveal", "target": "pose_turning", "attention_target": [.72, .42]},
                {"start_seconds": 4.8, "end_seconds": 7.0, "action": "pose_reveal", "target": "pose_resting"},
            ],
            "ae_operations": ["pose_change", "mask_reveal"],
            "qa_assertions": ["All three pose changes are visible at their authored beat."],
            "continuity_rules": ["Keep face, clothing, blanket and body placement registered."],
        },
        "ae_effect_plan": {
            "enabled": True, "template": "directed_performance", "template_source": "scene_visual_director",
            "preset": "directed_scene_performance", "dramatic_intent": "Pain, glance, rest.",
            "duration_seconds": 7,
            "asset_requirements": {"required_layers": ["background", "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "shoji"], "optional_layers": []},
            "beats": [
                {"at_seconds": 0, "end_seconds": 1.0, "action": "pose_reveal", "target": "pose_sleeping"},
                {"at_seconds": 1.0, "end_seconds": 2.6, "action": "pose_reveal", "target": "pose_waking"},
                {"at_seconds": 2.6, "end_seconds": 4.8, "action": "pose_reveal", "target": "pose_turning", "attention_target": [.72, .42]},
                {"at_seconds": 4.8, "end_seconds": 7.0, "action": "pose_reveal", "target": "pose_resting"},
            ],
            "qa_assertions": ["Pose changes visible."],
        },
    }
    effect_plans = runner._plan_ae_effects_for_scenes([scene], {})
    policy = runner._plan_image_generation_efficiency([scene], {}, effect_plans)
    plan = scene["ae_effect_plan"]
    assert plan["template"] == "directed_performance"
    assert plan["asset_requirements"]["required_layers"] == scene["ae_directorial_plan"]["required_layers"]
    assert scene["psd_layer_plan"]["enabled"] is True
    assert "complete clean plate" in scene["psd_layer_plan"]["prompt"]
    assert scene["psd_layer_plan"]["outputs"] == ["background", "pose_sleeping", "pose_waking", "pose_turning", "pose_resting", "shoji"]
    report = scene_qa.validate_scene_plan(scene, {"gcs_path": "scene.psd", "layers": scene["psd_layer_plan"]["outputs"]}, 7)
    assert report["passed"] is True, report


def test_explicit_template_geometry_and_timing_override_defaults():
    scene = {
        **_scene(1, "그는 조용히 서 있었다."),
        "ae_template": "ink_splat_impact",
        "ae_template_parameters": {"impact": {"x": 0.32, "y": 0.61, "at_seconds": 2.25, "text": "퍽!"}},
    }
    runner._plan_ae_effects_for_scenes([scene], {})
    plan = scene["ae_effect_plan"]
    assert plan["enabled"] is True
    assert plan["impact"] == {"x": 0.32, "y": 0.61, "at_seconds": 2.25, "text": "퍽!"}
    assert next(beat for beat in plan["beats"] if beat["action"] == "impact_flash")["at_seconds"] == 2.25


def test_scene_direction_plan_drives_regular_image_motion_with_limits():
    scene = {
        **_scene(24, "The daughter notices the letter in her father's hand."),
        "scene_direction_plan": {
            "contract": "scene_direction_plan/v1", "scene_role": "clue_reveal",
            "visual_strategy": "Guide attention to the letter.",
            "focus_target": {"type": "prop", "layer": "prop_focus", "x": 0.73, "y": 0.61},
            "primary_effect": "camera_move", "secondary_effects": ["light_flicker"],
            "effect_limits": {"intensity": 0.2, "max_scale_delta": 0.01, "max_move_ratio": 0.008},
            "ae_operations": ["camera_move", "light_flicker"], "timed_beats": [],
            "fallback": "original_visual",
        },
    }

    runner._plan_ae_motion_for_scenes([scene], {"category": "옛날이야기"})
    plan = scene["ae_motion_plan"]
    assert plan["scene_direction_plan"]["contract"] == "scene_direction_plan/v1"
    assert plan["primary_effect"] == "camera_move"
    assert plan["targets"][0]["x"] == 0.73
    assert plan["intensity"] <= 0.2
    assert abs(plan["motion"]["push"]) <= 0.01
    assert abs(plan["motion"]["drift_x"]) <= 0.008
    assert "warm_lantern_flicker" in plan["vfx"]


def test_script_director_hold_is_not_replaced_by_keyword_highlight():
    scene = {
        **_scene(25, "A dramatic explosion and final truth are described in narration."),
        "scene_direction_plan": {
            "contract": "scene_direction_plan/v1", "scene_role": "narration",
            "visual_strategy": "Hold so the narration carries the reveal.",
            "focus_target": {"type": "scene_focus", "x": 0.5, "y": 0.5},
            "primary_effect": "hold", "secondary_effects": [],
            "effect_limits": {"intensity": 0.1, "max_scale_delta": 0, "max_move_ratio": 0},
            "ae_operations": ["hold"], "timed_beats": [], "fallback": "original_visual",
        },
    }

    assert runner._plan_ae_effects_for_scenes([scene], {"category": "무협"}) == []
    assert scene["ae_effect_plan"]["reason"] == "script_director_uses_motion_plan"
    runner._plan_ae_motion_for_scenes([scene], {"category": "무협"})
    assert scene["ae_motion_plan"]["motion"] == {
        "push": 0.0, "drift_x": 0.0, "drift_y": 0.0, "shake": 0.0,
    }


def test_invalid_template_coordinates_fall_back_and_ordinary_scene_stays_ordinary():
    special = {
        **_scene(1, "기운이 그의 몸을 따라 흘렀다."),
        "ae_template": "body_following_qi",
        "ae_template_parameters": {"qi_path": [[-1, 0.5], [2, 0.5]], "talisman_target": [1.4, -0.2]},
    }
    ordinary = _scene(2, "연화는 편지를 읽고 조용히 문을 닫았다.")
    runner._plan_ae_effects_for_scenes([special, ordinary], {})
    assert special["ae_effect_plan"]["qi_path"] == [[0.48, 0.72], [0.39, 0.59], [0.52, 0.48], [0.61, 0.38], [0.50, 0.24]]
    assert special["ae_effect_plan"]["talisman_target"] == [0.5, 0.6]
    assert not ordinary["ae_effect_plan"].get("template")


def test_custom_talisman_target_is_normalized_into_qi_plan():
    scene = {
        **_scene(1, "부적이 가슴에 붙자 보랏빛 기운이 몸을 따라 흘렀다."),
        "ae_template_parameters": {"talisman_target": {"x": 0.43, "y": 0.57}},
    }
    runner._plan_ae_effects_for_scenes([scene], {})
    assert scene["ae_effect_plan"]["template"] == "body_following_qi"
    assert scene["ae_effect_plan"]["talisman_target"] == [0.43, 0.57]


def test_long_scene_template_timing_is_capped_to_actual_ae_clip():
    scene = {
        **_scene(1, "부적이 가슴을 때려 먹물 폭발과 충격이 터졌다."),
        "duration_seconds": 20,
        "ae_template_parameters": {"impact": {"x": 0.41, "y": 0.62, "at_seconds": 18.0, "text": "쾅!"}},
    }
    runner._plan_ae_effects_for_scenes([scene], {})
    plan = scene["ae_effect_plan"]
    assert plan["duration_seconds"] == 12
    assert plan["source_scene_duration_seconds"] == 20
    assert plan["impact"]["at_seconds"] == 11.45
    assert all(0 <= beat["at_seconds"] < 12 for beat in plan["beats"])
    asset = {"gcs_path": "scene.psd", "layer_names": ["background", "character", "talisman"]}
    assert scene_qa.validate_scene_plan(scene, asset, 12)["passed"] is True


def test_character_roles_bind_only_to_verified_portrait_keys():
    anchors = {
        "main_character": {"name": "서린", "character_key": "main-01"},
        "supporting_characters": [
            {"name": "모신", "character_key": "support-02"},
            {"name": "고찬", "character_key": "support-03"},
        ],
    }
    scene = {
        **_scene(1, "세 사람이 서로 놀라 반응했다."),
        "ae_template": "angled_triple_reaction",
        "ae_character_roles": {"character_left": "모신", "character_center": "서린", "character_right": "고찬"},
    }
    runner._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors})
    assert scene["ae_effect_plan"]["character_role_keys"] == {
        "character_left": "support-02",
        "character_center": "main-01",
        "character_right": "support-03",
    }
    scene.pop("ae_character_roles")
    runner._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors})
    assert scene["ae_effect_plan"]["character_role_keys"] == {}


def test_custom_panel_times_are_ordered_and_bad_polygons_fall_back():
    scene = {
        **_scene(1, "세 명이 놀라며 서로의 반응을 살폈다."),
        "ae_template": "angled_triple_reaction",
        "ae_template_parameters": {"panels": [
            {"role": "character_left", "enter_at": 2.0, "polygon": [[.2, .2]] * 4},
            {"role": "character_center", "enter_at": 0.4},
            {"role": "character_right", "enter_at": 1.0},
        ], "speech_bubble_text": "헉?!"},
    }
    runner._plan_ae_effects_for_scenes([scene], {})
    plan = scene["ae_effect_plan"]
    times = [beat["at_seconds"] for beat in plan["beats"]]
    assert times == sorted(times)
    assert plan["panels"][0]["polygon"] == [[0.04, 0.02], [0.33, 0.02], [0.28, 0.98], [0.04, 0.98]]
    assert next(beat for beat in plan["beats"] if beat["action"] == "speech_bubble")["text"] == "헉?!"
    asset = {"gcs_path": "scene.psd", "layer_names": ["background", "character_left", "character_center", "character_right"]}
    assert scene_qa.validate_scene_plan(scene, asset, 5)["passed"] is True


def test_ordinary_scenes_do_not_inherit_or_accidentally_select_templates():
    scenes = [
        _scene(1, "그는 부적을 발견하고 충격을 받았다."),
        _scene(2, "그는 몸의 기운을 천천히 되찾았다."),
        _scene(3, "세 사람은 함께 산길을 걸었다."),
        _scene(4, "먹물 방울이 폭발하듯 종이에 흩어졌다."),
    ]
    runner._plan_ae_effects_for_scenes(scenes, {"category": "무협"})
    assert all(not scene["ae_effect_plan"].get("template") for scene in scenes)

    scene = _scene(1, "부적에서 나온 기운이 그의 몸을 따라 흘렀다.")
    runner._plan_ae_effects_for_scenes([scene], {})
    assert scene["ae_effect_plan"]["template_source"] == "scene_semantics"
    scene["scene_summary"] = "그는 조용히 문을 닫았다."
    runner._plan_ae_effects_for_scenes([scene], {})
    assert not scene["ae_effect_plan"].get("template")


def test_conflicting_or_duplicate_character_names_do_not_bind_wrong_identity():
    scene = {
        **_scene(1, "세 사람이 경악했다."),
        "ae_template": "angled_triple_reaction",
        "ae_character_roles": {"character_left": "모신", "character_center": "서린"},
        "ae_character_role_keys": {"character_left": "wrong-key"},
    }
    anchors = {"main_character": {"name": "서린", "character_key": "main"},
               "supporting_characters": [{"name": "모신", "character_key": "left"},
                                         {"name": "다른 이", "character_key": "wrong-key"}]}
    runner._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors})
    assert scene["ae_effect_plan"]["character_role_keys"] == {"character_center": "main"}
    scene["ae_character_role_keys"] = {}
    anchors["supporting_characters"].append({"name": "모신", "character_key": "duplicate"})
    runner._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors})
    assert scene["ae_effect_plan"]["character_role_keys"] == {"character_center": "main"}


def test_four_new_scene_actions_select_distinct_templates_with_timed_geometry():
    scenes = [
        _scene(1, "그가 벽에 처박혀 충돌하자 벽이 부서지고 파편이 흩어졌다."),
        _scene(2, "노인의 안경 렌즈에 벽에서 쓰러진 인물의 모습이 비쳤다."),
        _scene(3, "근력 훈련 장면에서 화면에 큰 글자로 강조 문구가 터졌다."),
        _scene(4, "그는 손바닥을 태양을 향해 뻗었고 역광 광선이 퍼졌다."),
    ]
    plans = runner._plan_ae_effects_for_scenes(scenes, {})
    assert len(plans) == 4
    wall, glasses, title, hand = [scene["ae_effect_plan"] for scene in scenes]
    assert [plan["template"] for plan in (wall, glasses, title, hand)] == [
        "wall_impact_debris", "glasses_reflection", "kinetic_title_reveal", "backlit_hand_reveal",
    ]
    assert wall["asset_requirements"]["required_layers"] == ["background", "character", "wall_intact", "wall_broken"]
    assert wall["impact"] == {"x": 0.52, "y": 0.43, "at_seconds": 1.9}
    assert {beat["action"] for beat in wall["beats"]} >= {"wall_contact", "wall_reveal", "debris_burst"}
    assert glasses["asset_requirements"]["required_layers"] == ["background", "character", "reflection_scene"]
    assert glasses["reflection"]["left_lens"]["center"] == [0.355, 0.39]
    assert glasses["reflection"]["right_lens"]["center"] == [0.645, 0.39]
    assert glasses["reflection"]["at_seconds"] == next(
        beat["at_seconds"] for beat in glasses["beats"] if beat["action"] == "reflection_reveal")
    assert title["title"]["style"] == "training_emphasis"
    assert "training_prop" in title["asset_requirements"]["required_layers"]
    assert title["title"]["text"] == next(
        beat["text"] for beat in title["beats"] if beat["action"] == "text_reveal")
    assert hand["asset_requirements"]["required_layers"] == ["background", "hand_foreground"]
    assert hand["light_origin"] == [0.52, 0.29]
    assert {beat["action"] for beat in hand["beats"]} >= {"hand_raise", "light_ignite", "ray_burst"}
    assert all(0 <= beat["at_seconds"] < 5 for plan in (wall, glasses, title, hand) for beat in plan["beats"])
    runner._plan_image_generation_efficiency(scenes, {}, plans)
    assert [scene["psd_layer_plan"]["required_layers"] for scene in scenes] == [
        ["background", "character", "wall_intact", "wall_broken"],
        ["background", "character", "reflection_scene"],
        ["background", "character", "training_prop"],
        ["background", "hand_foreground"],
    ]
    assert all(scene["image_generation_policy"]["psd_layer_package_required"] for scene in scenes)


def test_new_template_explicit_overrides_are_normalized_and_bounded():
    scenes = [
        {**_scene(1, "그는 서 있었다."), "ae_template": "wall_impact_debris",
         "ae_template_parameters": {"impact": {"x": 0.39, "y": 0.61, "at_seconds": 3.2}}},
        {**_scene(2, "그는 바라봤다."), "ae_template": "glasses_reflection",
         "ae_template_parameters": {"reflection": {"at_seconds": 2.1,
             "left_lens": {"center": [0.31, 0.42], "radius": [0.08, 0.12]},
             "right_lens": {"center": [0.69, 0.42], "radius": [0.08, 0.12]}}}},
        {**_scene(3, "그는 단호하게 말했다."), "ae_template": "kinetic_title_reveal",
         "ae_template_parameters": {"title": {"text": "그들로부터 살아남아야 한다", "accent_text": "살아남아야 한다",
             "style": "threat_red", "position": [0.48, 0.78], "at_seconds": 2.3}}},
        {**_scene(4, "그는 손을 폈다."), "ae_template": "backlit_hand_reveal",
         "ae_template_parameters": {"light_origin": {"x": 0.44, "y": 0.22}, "light_at_seconds": 2.0}},
    ]
    runner._plan_ae_effects_for_scenes(scenes, {})
    wall, glasses, title, hand = [scene["ae_effect_plan"] for scene in scenes]
    assert wall["impact"] == {"x": 0.39, "y": 0.61, "at_seconds": 3.2}
    assert next(beat for beat in wall["beats"] if beat["action"] == "wall_contact")["at_seconds"] == 3.2
    assert glasses["reflection"]["left_lens"] == {"center": [0.31, 0.42], "radius": [0.08, 0.12]}
    assert glasses["reflection"]["right_lens"] == {"center": [0.69, 0.42], "radius": [0.08, 0.12]}
    assert glasses["reflection"]["at_seconds"] == 2.1
    assert title["title"] == {"text": "그들로부터 살아남아야 한다", "accent_text": "살아남아야 한다",
                              "style": "threat_red", "position": [0.48, 0.78], "at_seconds": 2.3}
    assert "training_prop" not in title["asset_requirements"]["required_layers"]
    assert hand["light_origin"] == [0.44, 0.22]
    assert next(beat for beat in hand["beats"] if beat["action"] == "light_ignite")["at_seconds"] == 2.0


def test_invalid_new_geometry_falls_back_without_false_template_selection():
    scenes = [
        {**_scene(1, "그는 서 있었다."), "ae_template": "glasses_reflection",
         "ae_template_parameters": {"reflection": {
             "left_lens": {"center": [-2, 4], "radius": [0, 0]},
             "right_lens": {"center": [0.95, 0.5], "radius": [0.2, 0.2]},
         }}},
        {**_scene(2, "그는 서 있었다."), "ae_template": "backlit_hand_reveal",
         "ae_template_parameters": {"light_origin": [1.5, -1], "light_at_seconds": 999}},
        _scene(3, "그는 벽 옆에서 놀라 안경을 고쳐 썼다."),
        _scene(4, "그는 근력 훈련을 마치고 조용히 손을 내렸다."),
    ]
    runner._plan_ae_effects_for_scenes(scenes, {})
    reflection = scenes[0]["ae_effect_plan"]["reflection"]
    assert reflection["left_lens"] == {"center": [0.355, 0.39], "radius": [0.115, 0.135]}
    assert reflection["right_lens"] == {"center": [0.645, 0.39], "radius": [0.115, 0.135]}
    assert scenes[1]["ae_effect_plan"]["light_origin"] == [0.52, 0.29]
    assert all(0 <= beat["at_seconds"] < 5 for beat in scenes[1]["ae_effect_plan"]["beats"])
    assert not scenes[2]["ae_effect_plan"].get("template")
    assert not scenes[3]["ae_effect_plan"].get("template")


def test_backlit_hand_uses_verified_protagonist_identity():
    scene = {**_scene(1, "그는 손바닥을 태양을 향해 뻗었다."), "ae_template": "backlit_hand_reveal"}
    anchors = {"main_character": {"name": "서린", "character_key": "hero-01"},
               "supporting_characters": [{"name": "고찬", "character_key": "other-02"}]}
    runner._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors})
    assert scene["ae_effect_plan"]["character_role_keys"] == {"hand_foreground": "hero-01"}
    assert scene["ae_effect_plan"]["character_role_names"] == {"hand_foreground": "서린"}


def test_new_templates_cap_geometry_to_twelve_second_ae_clip():
    scenes = [
        {**_scene(1, "그는 벽에 처박혀 벽이 깨지고 파편이 튀었다."), "duration_seconds": 22,
         "ae_template": "wall_impact_debris", "ae_template_parameters": {"impact": {"at_seconds": 21}}},
        {**_scene(2, "그는 손을 태양을 향해 뻗었다."), "duration_seconds": 19,
         "ae_template": "backlit_hand_reveal", "ae_template_parameters": {"light_at_seconds": 18}},
    ]
    runner._plan_ae_effects_for_scenes(scenes, {})
    assert [scene["ae_effect_plan"]["duration_seconds"] for scene in scenes] == [12, 12]
    assert scenes[0]["ae_effect_plan"]["impact"]["at_seconds"] <= 11.55
    assert all(0 <= beat["at_seconds"] < 12 for scene in scenes for beat in scene["ae_effect_plan"]["beats"])


def test_new_template_plans_pass_preflight_at_short_and_clamped_durations():
    late = {"impact": {"at_seconds": 999}, "reflection": {"at_seconds": 999},
            "title": {"at_seconds": 999}, "raise_at_seconds": 999,
            "light_at_seconds": 999, "ray_at_seconds": 999}
    early = {"impact": {"at_seconds": 0}, "reflection": {"at_seconds": 0},
             "title": {"at_seconds": 0}, "raise_at_seconds": 0,
             "light_at_seconds": 0, "ray_at_seconds": 0}
    for template in ("wall_impact_debris", "glasses_reflection", "kinetic_title_reveal", "backlit_hand_reveal"):
        for duration in range(1, 13):
            for parameters in ({}, late, early):
                scene = {**_scene(1, "A deliberately directed manga shot."),
                         "ae_template": template, "duration_seconds": duration,
                         "ae_template_parameters": parameters}
                runner._plan_ae_effects_for_scenes([scene], {})
                plan = scene["ae_effect_plan"]
                asset = {"gcs_path": "scene.psd",
                         "layer_names": plan["asset_requirements"]["required_layers"]}
                qa = scene_qa.validate_scene_plan(scene, asset, duration)
                assert qa["passed"], (template, duration, parameters, qa["errors"])
