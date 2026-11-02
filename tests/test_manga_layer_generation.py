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
    def __init__(self, *, opaque_character=False, size=(1024, 768)):
        self.calls = []
        self.opaque_character = opaque_character
        self.size = size

    def generate(self, *, prompt, role, reference, work_dir):
        self.calls.append((role, reference, prompt))
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / "source.png"
        if role == "background" or role == "character" and self.opaque_character:
            image = Image.new("RGB", self.size, (35, 40, 65))
        else:
            image = Image.new("RGBA", self.size, (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((280, 100, 740, 700), fill=(220, 70, 65, 255))
        image.save(path)
        return path


def test_directed_pose_uses_registered_final_scene_and_transparent_prompt(tmp_path):
    images = tmp_path / 'images'
    images.mkdir()
    scene_image = images / 'scene-001.png'
    Image.new('RGB', package.CANVAS_SIZE, (45, 55, 65)).save(scene_image)
    spec = {'template':'directed_performance','scene_number':1}
    job = {'scene':{'scene_text':'She turns toward the sound.','character_pose_layers':True},'spec':spec,'role':'pose_turning','reference':None}
    reference = generation._visual_reference_for_job(job, images)
    prompt = generation._prompt(job['scene'], spec, job['role'], reference)
    assert reference['path'] == str(scene_image)
    assert 'transparent alpha' in prompt and 'registered' in prompt
    assert reference['sha256'] in prompt


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
            "required_layers": ["background", "character", "foreground"],
            "optional_layers": ["prop_focus", "hair_cloth", "atmosphere", "light_overlay"],
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
    fake = FakeGenerator(size=(1024, 576))

    report = generation.generate_layers(manifest, images, generator=fake)

    assert [item[0] for item in fake.calls] == ["background", "foreground", "character"]
    assert all(item[1] == final_scene for item in fake.calls)
    assert all("fixed composition and registration reference" in item[2] for item in fake.calls)
    assert all(job["status"] == "generated" for job in report["jobs"].values())
    specs = package.scene_specs([scene])
    assert specs[0]["template"] == "parallax_layered_scene"
    assert specs[0]["required_layers"] == ["background", "foreground", "character"]


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
        request_dir = kwargs["cwd"]
        assert (request_dir / "verified-character-reference.png").read_bytes() == portrait.read_bytes()
        Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(request_dir / "source.png")
        (request_dir / "response.json").write_text(json.dumps({"status": "ready",
            "generator": "builtin_image_gen", "image_file": "source.png"}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(generation.subprocess, "run", invoke)
    bridge = generation.NativeCodexLayerGenerator(executable="codex", model="", timeout_seconds=60)
    result = bridge.generate(prompt="one wuxia master", role="character", reference=portrait,
                             work_dir=work)
    assert result.name == "source.png" and result.is_file()
    assert result.parent.parent.name == "requests"
    assert len(seen) == 1

def test_generation_preflight_respects_explicit_scene_scope(tmp_path):
    manifest, scene, _ = _manifest(tmp_path)
    data = json.loads(manifest.read_text(encoding='utf-8'))
    other = json.loads(json.dumps(scene))
    other['scene_number'] = 2
    data['scene_specs'].append(other)
    data['layer_scene_numbers'] = [2]
    manifest.write_text(json.dumps(data), encoding='utf-8')
    _, specs, jobs = generation._preflight(manifest)
    assert [spec['scene_number'] for spec in specs] == [2]
    assert {job['spec']['scene_number'] for job in jobs} == {2}

def test_full_psd_without_explicit_style_matches_source_instead_of_inventing_genre():
    scene = {'scene_number': 19, 'scene_text': 'A woman reads a letter.', 'image_prompt': 'Historical Yokohama illustration.'}
    spec = {'scene_number': 19, 'template': 'full_psd'}
    prompt = generation._prompt(scene, spec, 'foreground_subject_or_focus', {'kind':'registered_scene','path':'scene.png','sha256':'a'*64})
    assert 'Match the registered source image and scene prompt' in prompt
    assert 'Korean wuxia manhwa' not in prompt

def test_registered_scene_layer_rejects_portrait_canvas_instead_of_silent_crop(tmp_path):
    source = tmp_path / 'portrait.png'
    image = Image.new('RGBA', (600, 1000), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((150, 100, 400, 800), fill=(100, 70, 40, 255))
    image.save(source)
    target = tmp_path / 'output.png'
    with pytest.raises(ValueError, match='incompatible canvas aspect ratio'):
        generation._normalize(source, target, 'foreground_subject_or_focus', registered_canvas=True)
    assert not target.exists()
