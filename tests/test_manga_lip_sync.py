from __future__ import annotations

import copy
import json
import sys
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))

import codex_content_runner as planner
import manga_layer_generation as generation
import manga_layer_package as layers
import manga_scene_qa as qa
from manga_ae_templates import write_manga_jsx
from manga_lip_sync import MOUTH_ROLES, build_cues, prepare_lip_sync, validate_lip_sync


def _audio(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 24000 * 3)


def _scene(tmp_path: Path, *, speaking: bool) -> dict:
    scene = {"scene_number": 1, "scene_text": "주인공이 가까이서 말한다.",
             "duration_seconds": 3, "ae_template": "dialogue_closeup"}
    if speaking:
        audio = tmp_path / "approved-dialogue.wav"
        _audio(audio)
        scene["ae_lip_sync"] = prepare_lip_sync(
            audio_path=audio, speaker_key="hero", mouth_box=[.43, .44, .57, .55],
            duration=3, words=[
                {"text": "당장", "start_seconds": .5, "end_seconds": .9, "speaker_key": "hero"},
                {"text": "부탁드려도", "start_seconds": 1.1, "end_seconds": 1.6, "speaker_key": "hero"},
            ],
        )
    payload = {"character_anchors": {"main_character": {"character_key": "hero", "name": "주인공"}}}
    planned = planner._plan_ae_effects_for_scenes([scene], payload)
    assert planned and scene["ae_effect_plan"]["template"] == "dialogue_closeup"
    return scene


def _asset(scene: dict) -> dict:
    names = list(layers.scene_spec(scene, 1)["required_layers"])
    return {"gcs_path": "topics/1/scene.psd", "layers": names}


def test_closeup_is_opt_in_and_silent_scenes_need_no_mouth_layers(tmp_path):
    scene = _scene(tmp_path, speaking=False)
    assert scene["ae_effect_plan"].get("lip_sync") is None
    assert layers.scene_spec(scene, 1)["required_layers"] == ["background", "character"]
    assert qa.validate_scene_plan(scene, _asset(scene), 3)["passed"]


def test_approved_dialogue_produces_step_cues_and_requires_mouth_layers(tmp_path):
    scene = _scene(tmp_path, speaking=True)
    lip = scene["ae_effect_plan"]["lip_sync"]
    assert lip["cues"][0] == {"at_seconds": 0.0, "pose": "closed"}
    assert {cue["pose"] for cue in lip["cues"]} == {"closed", "half", "open"}
    assert set(MOUTH_ROLES) <= set(layers.scene_spec(scene, 1)["required_layers"])
    assert qa.validate_scene_plan(scene, _asset(scene), 3)["passed"]

    missing = _asset(scene)
    missing["layers"].remove("mouth_open")
    assert not qa.validate_scene_plan(scene, missing, 3)["passed"]

    jsx = tmp_path / "closeup.jsx"
    write_manga_jsx(scene=scene, input_psd=tmp_path / "approved.psd",
                    project_path=tmp_path / "scene.aep", render_path=tmp_path / "scene.mp4",
                    jsx_path=jsx, comp_name="closeup", width=1920, height=1080, fps=24, duration=3)
    script = jsx.read_text(encoding="utf-8")
    assert '"mouth_closed"' in script and '"mouth_open"' in script
    assert "KeyframeInterpolationType.HOLD" in script
    assert '"speaker_key": "hero"' in script


def test_stale_audio_wrong_speaker_or_modified_cues_fail_closed(tmp_path):
    scene = _scene(tmp_path, speaking=True)
    plan = scene["ae_effect_plan"]
    lip = plan["lip_sync"]
    assert validate_lip_sync(lip, template="dialogue_closeup", character_key="hero", duration=3) == []
    wrong_speaker = copy.deepcopy(lip)
    wrong_speaker["words"][0]["speaker_key"] = "other"
    assert any("speaker" in error for error in validate_lip_sync(
        wrong_speaker, template="dialogue_closeup", character_key="hero", duration=3))
    wrong_cues = copy.deepcopy(lip)
    wrong_cues["cues"][1]["pose"] = "closed"
    assert any("cues" in error for error in validate_lip_sync(
        wrong_cues, template="dialogue_closeup", character_key="hero", duration=3))
    asset = _asset(scene)
    Path(lip["audio_path"]).write_bytes(b"new take")
    assert not qa.validate_scene_plan(scene, asset, 3)["passed"]


def test_word_timing_rejects_overlap_and_non_closeup_opt_in(tmp_path):
    with pytest.raises(ValueError, match="nonoverlapping"):
        build_cues([{"text": "하나", "start_seconds": .2, "end_seconds": .6},
                    {"text": "둘", "start_seconds": .5, "end_seconds": .8}], 2)
    scene = _scene(tmp_path, speaking=True)
    scene["ae_template"] = "glasses_reflection"
    with pytest.raises(ValueError, match="dialogue_closeup"):
        planner._plan_ae_effects_for_scenes([scene],
            {"character_anchors": {"main_character": {"character_key": "hero", "name": "주인공"}}})


def test_mouth_layers_must_share_reviewed_position(tmp_path):
    scene = _scene(tmp_path, speaking=True)
    spec = layers.scene_spec(scene, 1)
    images = tmp_path / "images"
    images.mkdir()
    for role in spec["required_layers"]:
        image = Image.new("RGBA", layers.CANVAS_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if role == "background":
            draw.rectangle((0, 0, 1919, 1079), fill=(30, 40, 60, 255))
        elif role == "character":
            draw.ellipse((530, 50, 1400, 1000), fill=(240, 200, 175, 255))
        else:
            draw.ellipse((900, 510, 1020, 570), fill=(210, 125, 125, 255))
        image.save(images / spec["layer_files"][role])
    assert len(layers._inputs(spec, images)) == 5
    displaced = images / spec["layer_files"]["mouth_open"]
    image = Image.new("RGBA", layers.CANVAS_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((1110, 510, 1180, 570), fill=(210, 125, 125, 255))
    image.save(displaced)
    with pytest.raises(ValueError, match="mouth patch falls outside|registration"):
        layers._inputs(spec, images)


def test_mouth_generation_references_final_character_cutout(tmp_path):
    scene = _scene(tmp_path, speaking=True)
    portrait = tmp_path / "hero.png"
    Image.new("RGB", (512, 512), (90, 70, 65)).save(portrait)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": "cowork_scene_assets/v1", "topic_id": "1",
        "scene_specs": [scene], "character_references": [
            {"character_key": "hero", "name": "주인공", "local_file": str(portrait)}],
    }, ensure_ascii=False), encoding="utf-8")
    images = tmp_path / "images"
    seen = []

    class Generator:
        def generate(self, *, prompt, role, reference, work_dir):
            seen.append((role, reference, prompt))
            work_dir.mkdir(parents=True, exist_ok=True)
            path = work_dir / "source.png"
            if role == "background":
                Image.new("RGB", (1024, 768), (25, 30, 40)).save(path)
            else:
                image = Image.new("RGBA", (1024, 768), (0, 0, 0, 0))
                ImageDraw.Draw(image).ellipse((250, 130, 770, 650), fill=(220, 170, 140, 255))
                image.save(path)
            return path

    generation.generate_layers(manifest, images, generator=Generator())
    spec = layers.scene_spec(scene, 1)
    character = images / spec["layer_files"]["character"]
    assert [role for role, _, _ in seen] == ["background", "character", *MOUTH_ROLES]
    assert seen[1][1] == portrait
    assert all(reference == character for role, reference, _ in seen if role in MOUTH_ROLES)
    assert all("mouth_box" in prompt for role, _, prompt in seen if role in MOUTH_ROLES)
    assert len(layers._inputs(spec, images)) == 5


def test_sql_review_gate_includes_new_template_without_public_execute():
    sql = (ROOT / "supabase" / "migrations" /
           "20260927001946_enable_dialogue_closeup_review.sql").read_text(encoding="utf-8")
    assert sql.count("'dialogue_closeup', 'angled_triple_reaction'") == 3
    assert sql.count("security invoker") == 2
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
