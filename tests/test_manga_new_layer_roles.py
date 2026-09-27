"""The new AE directions require real, independently authored role layers."""

import json
import pathlib
import sys

import pytest
from PIL import Image, ImageDraw
from psd_tools import PSDImage


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worker"))
import manga_layer_generation as generation
import manga_layer_package as package


TEMPLATES = {
    "wall_impact_debris": ({"background", "character", "wall_intact", "wall_broken"},
                           {"debris", "speedlines"}),
    "glasses_reflection": ({"background", "character", "reflection_scene"}, {"lens_glint"}),
    "kinetic_title_reveal": ({"background", "character"},
                             {"training_prop", "title_backdrop", "speedlines"}),
    "backlit_hand_reveal": ({"background", "hand_foreground"}, {"light_core", "light_rays"}),
}


def _scene(template, *, mapped=True, extra_required=()):
    identity = "hand_foreground" if template == "backlit_hand_reveal" else "character"
    return {
        "scene_number": 1,
        "scene_text": "인물이 벽을 돌파하고 안경에 비친다",
        "image_prompt": "Korean webtoon still, dramatic action",
        "ae_effect_plan": {
            "enabled": True, "template": template,
            "character_role_keys": {identity: "hero"} if mapped else {},
            "asset_requirements": {"required_layers": list(extra_required)},
            "impact": {"x": 0.65, "y": 0.5, "at_seconds": 1.8},
            "light_origin": [0.53, 0.25],
        },
    }


def _manifest(tmp_path, scene):
    portrait = tmp_path / "character-reference-1.png"
    Image.new("RGB", (512, 512), (50, 70, 90)).save(portrait)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": "cowork_scene_assets/v1", "topic_id": "topic-new",
        "scene_specs": [scene], "character_references": [
            {"character_key": "hero", "name": "주인공", "local_file": str(portrait)}],
    }, ensure_ascii=False), encoding="utf-8")
    return manifest, portrait


class FakeGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, *, prompt, role, reference, work_dir):
        self.calls.append((role, reference, prompt))
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / "source.png"
        if role == "background":
            image = Image.new("RGB", (1024, 768), (50, 60, 80))
        else:
            image = Image.new("RGBA", (1024, 768), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((200, 120, 780, 700), fill=(210, 150, 100, 255))
        image.save(target)
        return target


@pytest.mark.parametrize("template", TEMPLATES)
def test_new_template_role_contract(template):
    required, optional = TEMPLATES[template]
    spec = package.scene_spec(_scene(template), 1)
    assert set(spec["required_layers"]) == required
    assert set(spec["optional_layers"]) == optional
    assert set(spec["layer_files"]) == required | optional
    assert all(spec["layer_files"][role].endswith(".png") for role in required)


def test_unrelated_or_duplicated_role_cannot_enter_reviewed_psd():
    scene = _scene("glasses_reflection", extra_required=("wall_broken",))
    with pytest.raises(ValueError, match="unrelated layer roles"):
        package.scene_spec(scene, 1)
    scene["ae_effect_plan"]["asset_requirements"]["required_layers"] = ["reflection_scene", "reflection_scene"]
    with pytest.raises(ValueError, match="duplicate"):
        package.scene_spec(scene, 1)


def test_wall_generation_uses_intact_wall_as_geometry_reference_and_stays_pending(tmp_path):
    scene = _scene("wall_impact_debris")
    manifest, portrait = _manifest(tmp_path, scene)
    images = tmp_path / "images"
    fake = FakeGenerator()
    report = generation.generate_layers(manifest, images, generator=fake)
    spec = package.scene_specs([scene])[0]
    assert [role for role, _, _ in fake.calls] == spec["required_layers"]
    references = {role: ref for role, ref, _ in fake.calls}
    assert references["character"] == portrait
    assert references["wall_broken"] == images / spec["layer_files"]["wall_intact"]
    assert "SAME wall plane" in next(prompt for role, _, prompt in fake.calls if role == "wall_broken")
    assert all(value["status"] == "generated" for value in report["jobs"].values())
    assert report["review_required"] is True
    for role in spec["required_layers"]:
        with Image.open(images / spec["layer_files"][role]) as image:
            assert image.size == (1920, 1080)
            assert image.getchannel("A").getextrema() == (
                (255, 255) if role == "background" else (0, 255))
    receipt = package.prepare(manifest, images, [spec])
    psd = PSDImage.open(images / receipt["packages"]["1"]["psd_file"])
    assert [layer.name for layer in psd] == spec["required_layers"]
    assert receipt["packages"]["1"]["status"] == "pending_visual_review"
    with pytest.raises(ValueError, match="needs visual review"):
        package.validate_receipt(manifest, images, [spec], require_approved=True)


def test_hand_foreground_requires_verified_character_reference_before_generation(tmp_path):
    scene = _scene("backlit_hand_reveal", mapped=False)
    manifest, _ = _manifest(tmp_path, scene)
    fake = FakeGenerator()
    with pytest.raises(ValueError, match="hand_foreground.*character_role_keys"):
        generation.generate_layers(manifest, tmp_path / "images", generator=fake)
    assert fake.calls == []
    scene["ae_effect_plan"]["character_role_keys"] = {"hand_foreground": "hero"}
    manifest, portrait = _manifest(tmp_path, scene)
    result = generation.generate_layers(manifest, tmp_path / "images-2", generator=fake)
    assert [role for role, _, _ in fake.calls] == ["background", "hand_foreground"]
    assert fake.calls[1][1] == portrait
    assert "verified_character" in fake.calls[1][2]
    assert result["review_required"]


def test_reflection_plate_is_independent_alpha_art_not_a_character_crop(tmp_path):
    scene = _scene("glasses_reflection")
    manifest, portrait = _manifest(tmp_path, scene)
    images = tmp_path / "images"
    fake = FakeGenerator()
    generation.generate_layers(manifest, images, generator=fake)
    spec = package.scene_spec(scene, 1)
    assert [role for role, _, _ in fake.calls] == spec["required_layers"]
    assert next(ref for role, ref, _ in fake.calls if role == "character") == portrait
    assert next(ref for role, ref, _ in fake.calls if role == "reflection_scene") is None
    assert "masked into both lenses" in next(
        prompt for role, _, prompt in fake.calls if role == "reflection_scene")
    with Image.open(images / spec["layer_files"]["reflection_scene"]) as image:
        assert image.size == (1920, 1080)
        assert image.getchannel("A").getextrema() == (0, 255)


def test_training_prop_can_be_required_by_scene_without_changing_base_contract(tmp_path):
    scene = _scene("kinetic_title_reveal", extra_required=("training_prop",))
    spec = package.scene_spec(scene, 1)
    assert "training_prop" in spec["required_layers"]
    assert "training_prop" not in spec["optional_layers"]
    manifest, _ = _manifest(tmp_path, scene)
    fake = FakeGenerator()
    generation.generate_layers(manifest, tmp_path / "images", generator=fake)
    assert "training_prop" in [role for role, _, _ in fake.calls]
    assert "No person, scenery, title, or text" in next(
        prompt for role, _, prompt in fake.calls if role == "training_prop")


def test_new_scene_slots_follow_impact_and_light_origin():
    scene = _scene("wall_impact_debris")
    wall = generation._slot_for_scene(scene, "wall_broken")
    assert (wall[0] + wall[2]) / 2 == pytest.approx(0.65)
    light = generation._slot_for_scene(scene, "light_core")
    assert (light[0] + light[2]) / 2 == pytest.approx(0.53)
