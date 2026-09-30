import json
import hashlib
import pathlib
import subprocess
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
import manga_scene_qa as qa
import manga_scene_review as review


def _asset(layers):
    return {"psd_layer_asset": {"gcs_path": "topics/test/scene.psd", "layers": layers}}


def _scene(template, **overrides):
    plan = {"enabled": True, "template": template, "duration_seconds": 4,
            "beats": [{"at_seconds": .25, "action": "reveal", "target": "character"}]}
    if template == "angled_triple_reaction":
        plan["panels"] = [
            {"role": "character_left", "polygon": [[0, 0], [.3, 0], [.4, 1], [0, 1]], "enter_at": 0},
            {"role": "character_center", "polygon": [[.3, 0], [.7, 0], [.6, 1], [.4, 1]], "enter_at": .3},
            {"role": "character_right", "polygon": [[.7, 0], [1, 0], [1, 1], [.6, 1]], "enter_at": .5},
        ]
        plan["asset_requirements"] = {"required_layers": ["background", "character_left", "character_center", "character_right"]}
        plan["beats"] = [
            {"at_seconds": 0, "action": "panel_reveal", "target": "character_left"},
            {"at_seconds": .3, "action": "panel_reveal", "target": "character_center"},
            {"at_seconds": .5, "action": "panel_reveal", "target": "character_right"},
        ]
    elif template == "body_following_qi":
        plan["talisman_target"] = [.5, .6]
        plan["qi_path"] = [[.42, .6], [.5, .48], [.6, .38]]
        plan["beats"] = [
            {"at_seconds": .25, "action": "talisman_attach", "target": "character"},
            {"at_seconds": .5, "action": "qi_trace_start", "target": "qi_path"},
        ]
    elif template == "ink_splat_impact":
        plan["impact"] = {"x": .55, "y": .6, "at_seconds": 1.5, "text": "쾅!"}
        plan["beats"] = [
            {"at_seconds": 1.5, "action": "impact_flash", "target": "impact"},
            {"at_seconds": 1.55, "action": "ink_splat", "target": "impact"},
            {"at_seconds": 1.62, "action": "onomatopoeia", "target": "impact", "text": "쾅!"},
        ]
    elif template == "wall_impact_debris":
        plan["impact"] = {"x": .52, "y": .43, "at_seconds": 1.5}
        plan["beats"] = [
            {"at_seconds": 1.5, "action": "wall_contact", "target": "impact"},
            {"at_seconds": 1.5, "action": "wall_reveal", "target": "wall_broken"},
            {"at_seconds": 1.55, "action": "debris_burst", "target": "impact"},
            {"at_seconds": 2.8, "action": "debris_settle", "target": "impact"},
        ]
    elif template == "glasses_reflection":
        plan["reflection"] = {
            "left_lens": {"center": [.355, .39], "radius": [.115, .135]},
            "right_lens": {"center": [.645, .39], "radius": [.115, .135]},
            "at_seconds": 1.5,
        }
        plan["beats"] = [
            {"at_seconds": 1.5, "action": "reflection_reveal", "target": "reflection_scene"},
            {"at_seconds": 1.62, "action": "lens_glint", "target": "reflection_scene"},
            {"at_seconds": 1.75, "action": "camera_push", "target": "character"},
        ]
    elif template == "kinetic_title_reveal":
        plan["title"] = {"text": "살아남아야 한다", "accent_text": "살아남아야", "style": "threat_red",
                         "position": [.5, .73], "at_seconds": 1.5}
        plan["beats"] = [
            {"at_seconds": 1.5, "action": "text_reveal", "target": "title", "text": "살아남아야 한다"},
            {"at_seconds": 1.6, "action": "text_punch", "target": "title", "text": "살아남아야"},
            {"at_seconds": 2.8, "action": "text_hold", "target": "title"},
        ]
    elif template == "backlit_hand_reveal":
        plan["light_origin"] = [.52, .29]
        plan["beats"] = [
            {"at_seconds": .48, "action": "hand_raise", "target": "hand_foreground"},
            {"at_seconds": 1.5, "action": "light_ignite", "target": "light_origin"},
            {"at_seconds": 1.95, "action": "ray_burst", "target": "light_origin"},
            {"at_seconds": 3.2, "action": "afterglow", "target": "light_origin"},
        ]
    plan.update(overrides)
    return {"scene_number": 1, "ae_effect_plan": plan}


@pytest.mark.parametrize("template,layers", [
    ("angled_triple_reaction", ["background", "character_left", "character_center", "character_right"]),
    ("body_following_qi", ["background", "character", "talisman"]),
    ("ink_splat_impact", ["background", "character", "talisman"]),
    ("wall_impact_debris", ["background", "character", "wall_intact", "wall_broken"]),
    ("glasses_reflection", ["background", "character", "reflection_scene"]),
    ("kinetic_title_reveal", ["background", "character"]),
    ("backlit_hand_reveal", ["background", "hand_foreground"]),
])
def test_valid_template_plan_requires_visual_review(template, layers):
    report = qa.validate_scene_plan(_scene(template), _asset(layers), 4)
    assert report["passed"] is True
    assert report["status"] == "needs_review"
    assert report["review_required"] is True
    assert json.loads(json.dumps(report)) == report


def test_template_rejects_flattened_image_and_missing_character_layer():
    scene = _scene("angled_triple_reaction")
    report = qa.validate_scene_plan(scene, {"gcs_path": "scene.png", "layers": ["background", "character_left"]}, 4)
    assert report["passed"] is False
    assert any("layered PSD" in error for error in report["errors"])
    assert any("character_center" in error for error in report["errors"])


def test_template_checks_local_psd_signature(tmp_path):
    fake_psd = tmp_path / "scene.psd"
    fake_psd.write_bytes(b"PNG!" + b"0" * 100)
    report = qa.validate_scene_plan(_scene("body_following_qi"),
                                    {"local_path": str(fake_psd), "layers": ["background", "character", "talisman"]}, 4)
    assert not report["passed"]
    assert any("8BPS" in error for error in report["errors"])


def test_duplicate_psd_layer_names_are_rejected():
    asset = _asset(["background", "character", "talisman", "character"])
    report = qa.validate_scene_plan(_scene("body_following_qi"), asset, 4)
    assert not report["passed"]
    assert any("must be unique" in error for error in report["errors"])


def test_rejects_bad_panel_polygon_and_offscreen_beat_target():
    scene = _scene("angled_triple_reaction")
    scene["ae_effect_plan"]["panels"][0]["polygon"] = [[0, 0], [0, 0], [0, 0]]
    scene["ae_effect_plan"]["beats"][0]["target"] = [1.3, .5]
    report = qa.validate_scene_plan(scene, _asset(["background", "character_left", "character_center", "character_right"]), 4)
    assert not report["passed"]
    assert {check["code"] for check in report["checks"] if not check["passed"]} >= {
        "panel_1_polygon", "beat_1_target"
    }


def test_rejects_qi_path_with_no_travel_and_impact_text_timing():
    qi_scene = _scene("body_following_qi", qi_path=[[.5, .5], [.5, .5], [.5, .5]])
    qi_report = qa.validate_scene_plan(qi_scene, _asset(["background", "character", "talisman"]), 4)
    assert any("travel" in error for error in qi_report["errors"])

    qi_scene["ae_effect_plan"]["talisman_target"] = [1.2, .6]
    target_report = qa.validate_scene_plan(qi_scene, _asset(["background", "character", "talisman"]), 4)
    assert any("talisman_target" in error for error in target_report["errors"])

    ink_scene = _scene("ink_splat_impact")
    ink_scene["ae_effect_plan"]["impact"] = {"x": 1.2, "y": .4, "at_seconds": 3.9, "text": "�"}
    ink_report = qa.validate_scene_plan(ink_scene, _asset(["background", "character", "talisman"]), 4)
    assert not ink_report["passed"]
    assert any("normalized" in error for error in ink_report["errors"])
    assert any("one 24 fps frame" in error for error in ink_report["errors"])
    assert any("replacement glyph" in error for error in ink_report["errors"])


def test_impact_lettering_must_have_a_visible_hold():
    scene = _scene("ink_splat_impact")
    scene["ae_effect_plan"]["impact"]["at_seconds"] = 3.8
    scene["ae_effect_plan"]["beats"] = [
        {"at_seconds": 3.8, "action": "impact_flash"},
        {"at_seconds": 3.85, "action": "ink_splat"},
        {"at_seconds": 3.9, "action": "onomatopoeia", "text": "쾅!"},
    ]
    report = qa.validate_scene_plan(scene, _asset(["background", "character", "talisman"]), 4)
    assert any("0.35 seconds" in error for error in report["errors"])


def test_wall_plan_rejects_offscreen_contact_wrong_role_and_out_of_order_debris():
    scene = _scene("wall_impact_debris")
    plan = scene["ae_effect_plan"]
    plan["impact"] = {"x": 1.1, "y": .43, "at_seconds": 2.5}
    plan["beats"][1]["at_seconds"] = 1.8
    plan["beats"][1]["target"] = "wall_intact"
    report = qa.validate_scene_plan(scene, _asset(["background", "character", "wall_intact", "wall_broken"]), 4)
    failed = {check["code"] for check in report["checks"] if not check["passed"]}
    assert {"wall_impact_target", "wall_contact_alignment", "wall_reveal_target", "wall_beat_order"} <= failed


def test_reflection_plan_rejects_bad_lenses_and_misaligned_reveal():
    scene = _scene("glasses_reflection")
    plan = scene["ae_effect_plan"]
    plan["reflection"]["left_lens"]["radius"] = [0, .14]
    plan["reflection"]["right_lens"]["center"] = [.99, .39]
    plan["reflection"]["at_seconds"] = 2.5
    plan["beats"][1]["target"] = "character"
    report = qa.validate_scene_plan(scene, _asset(["background", "character", "reflection_scene"]), 4)
    failed = {check["code"] for check in report["checks"] if not check["passed"]}
    assert {"left_lens", "right_lens", "reflection_alignment", "lens_glint_target"} <= failed


def test_training_title_requires_real_prop_and_matching_legible_copy():
    scene = _scene("kinetic_title_reveal")
    title = scene["ae_effect_plan"]["title"]
    title.update({"style": "training_emphasis", "position": [1.2, .73], "accent_text": "없는 문구"})
    scene["ae_effect_plan"]["beats"][0]["text"] = "다른 문구"
    report = qa.validate_scene_plan(scene, _asset(["background", "character"]), 4)
    failed = {check["code"] for check in report["checks"] if not check["passed"]}
    assert {"required_layers", "title_position", "title_accent", "text_reveal_copy", "text_punch_copy"} <= failed
    assert "training_prop" in report["required_layers"]


def test_title_timing_and_style_fail_closed():
    scene = _scene("kinetic_title_reveal")
    plan = scene["ae_effect_plan"]
    plan["title"]["style"] = "unknown"
    plan["title"]["at_seconds"] = 3.6
    plan["beats"][2]["at_seconds"] = 3.8
    report = qa.validate_scene_plan(scene, _asset(["background", "character"]), 4)
    failed = {check["code"] for check in report["checks"] if not check["passed"]}
    assert {"title_style", "title_alignment", "title_readable_hold"} <= failed


def test_backlit_plan_checks_palm_origin_role_and_ray_order():
    scene = _scene("backlit_hand_reveal")
    plan = scene["ae_effect_plan"]
    plan["light_origin"] = [-.1, .3]
    plan["beats"][0]["target"] = "character"
    plan["beats"][2]["at_seconds"] = 1.2
    report = qa.validate_scene_plan(scene, _asset(["background", "hand_foreground"]), 4)
    failed = {check["code"] for check in report["checks"] if not check["passed"]}
    assert {"light_origin", "hand_raise_target", "backlight_beat_order"} <= failed


@pytest.mark.parametrize("template", [
    "wall_impact_debris", "glasses_reflection", "kinetic_title_reveal", "backlit_hand_reveal",
])
def test_generated_new_template_plan_passes_preflight(template):
    import codex_content_runner as planner

    source = {"scene_summary": "근력 훈련 장면" if template == "kinetic_title_reveal" else "장면 연출"}
    plan = planner._manga_template_plan(template, source, 5)
    scene = {"ae_effect_plan": plan}
    layers = plan["asset_requirements"]["required_layers"]
    report = qa.validate_scene_plan(scene, _asset(layers), 5)
    assert report["passed"] is True, report


def test_legacy_scene_is_not_blocked_by_template_gate():
    assert qa.validate_scene_plan({"ae_effect_plan": {"enabled": True}}, {}, 4)["status"] == "not_applicable"
    assert qa.validate_render({}, "missing.mp4")["passed"] is True


def _render_mp4(path, color, duration=2):
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    source = ("color=c=black:s=640x360:r=24" if color == "black"
              else "color=c=blue:s=640x360:r=24" if color == "blue"
              else "testsrc2=s=640x360:r=24")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source,
               "-t", str(duration), "-c:v", "mpeg4", "-q:v", "5", str(path)]
    subprocess.run(command, check=True, capture_output=True, timeout=90)


def test_render_gate_decodes_real_video_and_flags_flat_black(tmp_path):
    scene = _scene("ink_splat_impact", duration_seconds=2)
    scene["ae_effect_plan"]["impact"]["at_seconds"] = 1
    scene["ae_effect_plan"]["beats"][1]["at_seconds"] = 1
    moving = tmp_path / "moving.mp4"
    _render_mp4(moving, "moving")
    report = qa.validate_render(scene, moving, fps=24)
    assert report["passed"] is True, report
    assert len(report["samples"]) >= 3
    assert report["review_required"] is True
    assert "image" not in json.dumps(report)

    # The Premiere scene may last longer than the AE clip. The caller passes
    # the actual AE job duration when checking the rendered file.
    scene["ae_effect_plan"]["duration_seconds"] = 8
    assert qa.validate_render(scene, moving, fps=24, duration_seconds=2)["passed"] is True
    scene["ae_effect_plan"]["duration_seconds"] = 2

    blank = tmp_path / "blank.mp4"
    _render_mp4(blank, "black")
    blank_report = qa.validate_render(scene, blank, fps=24)
    assert blank_report["passed"] is False
    assert any("flat black" in error for error in blank_report["errors"])

    static = tmp_path / "static.mp4"
    _render_mp4(static, "blue")
    static_report = qa.validate_render(scene, static, fps=24)
    assert static_report["passed"] is False
    assert any("planned impact" in error for error in static_report["errors"])


def test_render_gate_rejects_corrupt_mp4(tmp_path):
    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"X" * 2000)
    report = qa.validate_render(_scene("body_following_qi"), video)
    assert report["passed"] is False
    assert any("MP4 probe" in error for error in report["errors"])


@pytest.fixture(scope="module")
def new_template_clips(tmp_path_factory):
    directory = tmp_path_factory.mktemp("manga-new-template-qa")
    moving, static = directory / "moving.mp4", directory / "static.mp4"
    _render_mp4(moving, "moving", duration=4)
    _render_mp4(static, "blue", duration=4)
    return moving, static


@pytest.mark.parametrize("template,layers", [
    ("wall_impact_debris", ["background", "character", "wall_intact", "wall_broken"]),
    ("glasses_reflection", ["background", "character", "reflection_scene"]),
    ("kinetic_title_reveal", ["background", "character"]),
    ("backlit_hand_reveal", ["background", "hand_foreground"]),
    ("directed_performance", ["background", "pose_sleeping", "pose_waking"]),
])
def test_new_templates_render_event_and_stay_under_visual_review(template, layers, new_template_clips):
    moving, static = new_template_clips
    scene = _scene(template)
    if template == "directed_performance":
        scene["ae_effect_plan"]["asset_requirements"] = {"required_layers": layers}
        scene["ae_effect_plan"]["beats"] = [
            {"at_seconds": 0.0, "action": "pose_reveal", "target": "pose_sleeping"},
            {"at_seconds": 1.8, "action": "pose_reveal", "target": "pose_waking"},
        ]
    plan_report = qa.validate_scene_plan(scene, _asset(layers), 4)
    assert plan_report["passed"] is True, plan_report
    render_report = qa.validate_render(scene, moving, fps=24)
    assert render_report["passed"] is True, render_report
    assert render_report["status"] == "needs_review"
    assert render_report["review_required"] is True
    if template == "directed_performance":
        assert any(check["code"] == "directorial_beat_2_frame_change" and check["passed"] for check in render_report["checks"])
    else:
        assert render_report["event_frame_difference"] >= .7
    static_report = qa.validate_render(scene, static, fps=24)
    assert static_report["passed"] is False
    assert any(("directorial action" in error or "planned" in error or "directed beat" in error)
               and ("visible change" in error or "visibly change" in error)
               for error in static_report["errors"])

    digest = hashlib.sha256(moving.read_bytes()).hexdigest()
    scene["metadata"] = {"ae_effect_asset": {
        "status": "review_pending", "render_sha256": digest, "review_local_path": str(moving),
        "manga_qa": {"plan": plan_report, "render": render_report},
    }}
    structure = {"scenes": [scene]}
    review.apply_review(structure, scene_number=1, decision="approved", reviewer="QA",
                        note="Event timing and scene layers visually checked", expected_sha256=digest,
                        allowed_media_root=moving.parent)
    assert scene["metadata"]["ae_effect_asset"]["status"] == "ready"
