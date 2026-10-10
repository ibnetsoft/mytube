import json
import pathlib
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worker"))
import manga_layer_generation as generation
import manga_layer_package as package


def _manifest(tmp_path, *, with_mapping=True):
    portrait = tmp_path / "character-reference-1.png"
    Image.new("RGB", (512, 512), (28, 33, 71)).save(portrait)
    scene = {"scene_number": 1, "scene_text": "부적이 가슴에 닿자 기운이 폭발했다.",
             "image_prompt": "Korean wuxia manhwa, wounded master, purple qi",
             "image_style": "Korean wuxia manhwa",
             "ae_effect_plan": {"enabled": True, "template": "ink_splat_impact",
                                "character_role_keys": {"character": "master"} if with_mapping else {}}}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema": "cowork_scene_assets/v1", "topic_id": "topic-1",
        "scene_specs": [scene], "character_references": [{"character_key": "master",
            "name": "장주", "local_file": str(portrait)}]}, ensure_ascii=False), encoding="utf-8")
    return manifest, scene, portrait


class FakeGenerator:
    def __init__(self, *, opaque_character=False):
        self.calls = []
        self.opaque_character = opaque_character

    def generate(self, *, prompt, role, reference, work_dir):
        self.calls.append((role, reference, prompt))
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / "source.png"
        if role == "background" or role == "character" and self.opaque_character:
            image = Image.new("RGB", (1024, 768), (35, 40, 65))
        else:
            image = Image.new("RGBA", (1024, 768), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((280, 100, 740, 700), fill=(220, 70, 65, 255))
        image.save(path)
        return path


def test_generated_roles_are_independent_full_canvas_and_still_need_visual_review(tmp_path):
    manifest, scene, portrait = _manifest(tmp_path)
    images = tmp_path / "images"
    fake = FakeGenerator()
    report = generation.generate_layers(manifest, images, generator=fake)

    assert [item[0] for item in fake.calls] == ["background", "character", "talisman"]
    assert fake.calls[1][1] == portrait
    assert fake.calls[0][1] is None and fake.calls[2][1] is None
    assert "verified_character" in fake.calls[1][2]
    assert all(job["status"] == "generated" for job in report["jobs"].values())
    assert report["review_required"] is True
    specs = package.scene_specs([scene])
    for role in specs[0]["required_layers"]:
        with Image.open(images / specs[0]["layer_files"][role]) as image:
            assert image.size == (1920, 1080)
            extrema = image.getchannel("A").getextrema()
            assert extrema == ((255, 255) if role == "background" else (0, 255))
    prepared = package.prepare(manifest, images, specs)
    assert prepared["packages"]["1"]["status"] == "pending_visual_review"
    with pytest.raises(ValueError, match="needs visual review"):
        package.validate_receipt(manifest, images, specs, require_approved=True)
    package.approve(manifest, images, specs, reviewer="operator", note="Identity, cutout edges, and impact placement inspected")
    package.validate_receipt(manifest, images, specs, require_approved=True)
    assert len(fake.calls) == 3


def test_explicit_parallax_range_uses_final_scene_as_registration_reference(tmp_path):
    scene = {
        "scene_number": 19,
        "scene_text": "인물이 등불을 들고 골목을 걷는다.",
        "image_prompt": "A character walking through a lantern-lit street.",
        "image_style": "period animation",
        "psd_layer_plan": {
            "enabled": True,
            "selection_source": "explicit_scene_range",
            "template": "parallax_layered_scene",
            "required_layers": ["background", "foreground"],
            "optional_layers": ["prop_focus", "atmosphere"],
        },
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": "cowork_scene_assets/v1",
        "topic_id": "topic-1",
        "scene_specs": [scene],
        "character_references": [],
    }), encoding="utf-8")
    images = tmp_path / "images"
    images.mkdir()
    final_scene = images / "scene-019.png"
    Image.new("RGB", (1920, 1080), (35, 40, 65)).save(final_scene)
    fake = FakeGenerator()

    report = generation.generate_layers(manifest, images, generator=fake)

    assert [item[0] for item in fake.calls] == ["background", "foreground"]
    assert all(item[1] == final_scene for item in fake.calls)
    assert "fixed composition and registration reference" in fake.calls[1][2]
    assert all(job["status"] == "generated" for job in report["jobs"].values())
    specs = package.scene_specs([scene])
    assert specs[0]["template"] == "parallax_layered_scene"
    assert specs[0]["required_layers"] == ["background", "foreground"]


def test_ambiguous_character_mapping_stops_before_provider_call(tmp_path):
    manifest, _, _ = _manifest(tmp_path, with_mapping=False)
    fake = FakeGenerator()
    with pytest.raises(ValueError, match="character_role_keys mapping is required"):
        generation.generate_layers(manifest, tmp_path / "images", generator=fake)
    assert fake.calls == []
    issue = json.loads((tmp_path / "images" / "manga-layer-generation-issues.json").read_text(encoding="utf-8"))
    assert issue["status"] == "needs_review"


def test_provider_opaque_character_blocks_layer_and_does_not_retry(tmp_path):
    manifest, scene, _ = _manifest(tmp_path)
    images = tmp_path / "images"
    fake = FakeGenerator(opaque_character=True)
    with pytest.raises(ValueError, match="transparent alpha"):
        generation.generate_layers(manifest, images, generator=fake)
    specs = package.scene_specs([scene])
    assert not (images / specs[0]["layer_files"]["character"]).exists()
    report = json.loads(generation.report_path(images).read_text(encoding="utf-8"))
    assert report["jobs"]["scene-001-character"]["status"] == "needs_review"
    with pytest.raises(RuntimeError, match="prior generation was interrupted or failed"):
        generation.generate_layers(manifest, images, generator=fake)
    assert [role for role, _, _ in fake.calls] == ["background", "character"]


def test_native_bridge_passes_local_portrait_to_builtin_tool_without_api_fallback(tmp_path, monkeypatch):
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (512, 512), (35, 45, 65)).save(portrait)
    work = tmp_path / "work"
    seen = []

    def invoke(command, **kwargs):
        seen.append((command, kwargs))
        task = command[-1]
        assert "BUILT-IN image_gen" in task
        assert "transparent_background" in task
        assert "referenced_image_paths" in task
        assert "external image APIs" in task
        assert (work / "verified-character-reference.png").is_file()
        Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(work / "source.png")
        (work / "response.json").write_text(json.dumps({"status": "ready",
            "generator": "builtin_image_gen", "image_file": "source.png"}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(generation.subprocess, "run", invoke)
    bridge = generation.NativeCodexLayerGenerator(executable="codex", model="", timeout_seconds=60)
    assert bridge.generate(prompt="one wuxia master", role="character", reference=portrait,
                           work_dir=work) == work / "source.png"
    assert len(seen) == 1
