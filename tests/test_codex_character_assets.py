import pathlib
import sys
import pytest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
import codex_character_assets as assets


def character(name="연화"):
    return {"name": name, "role": "protagonist", "visual_dna_en": "Korean woman, adult, dark eyes",
            "wardrobe_en": "Joseon hanbok"}


def test_portraits_must_be_real_bitmaps(tmp_path):
    path = tmp_path / "bad.png"
    path.write_text("prompt only")
    with pytest.raises(Exception):
        assets.validate_portrait(path)
    Image.new("RGB", (32, 32)).save(path)
    with pytest.raises(RuntimeError, match="512"):
        assets.validate_portrait(path)


def test_generation_and_storage_are_mandatory(tmp_path):
    calls = []
    class Generator:
        def generate(self, prompt):
            calls.append("generate")
            assert "No letters" in prompt
            return tmp_path / "portrait.png"
    class Store:
        def publish(self, topic, c, path, fingerprint, payload):
            calls.append("publish")
            assert topic == 3197 and fingerprint
            return {**c, "image_url": "https://assets.example/portrait.png"}
    result = assets.generate_character_references({"script": "final narration", "main_character": character(),
        "supporting_characters": [character("덕수")]}, {"topic_queue_id": 3197}, None, tmp_path,
        generator=Generator(), store=Store())
    assert calls == ["generate", "publish", "generate", "publish"]
    assert result["character_image_generation"]["count"] == 2
    class BrokenStore:
        def publish(self, *args):
            raise RuntimeError("upload failed")
    with pytest.raises(RuntimeError, match="upload failed"):
        assets.generate_character_references({"script": "final", "main_character": character()},
            {"topic_queue_id": 3197}, None, tmp_path, generator=Generator(), store=BrokenStore())


def test_rejects_missing_final_script_or_character_dna(tmp_path):
    with pytest.raises(RuntimeError, match="Final script"):
        assets.generate_character_references({}, {}, None, tmp_path)
    with pytest.raises(RuntimeError, match="visual DNA"):
        assets.generate_character_references({"script": "final", "main_character": {"name": "연화"}},
            {"topic_queue_id": 3197}, None, tmp_path)


def test_upload_requires_public_bytes_and_registry_readback(monkeypatch, tmp_path):
    path = tmp_path / "portrait.png"
    Image.new("RGB", (512, 512), "blue").save(path)
    store = object.__new__(assets.CharacterAssetStore)
    store.base = "https://test.supabase.co"
    saved = {}
    class Response:
        status_code = 200
        content = path.read_bytes()
        def __init__(self, value=None): self.value = value
        def json(self): return self.value
    def request(method, url, **kwargs):
        if url == "/rest/v1/topic_character_assets":
            if method == "POST": saved.update(kwargs["json"])
            return Response([saved])
        assert url.startswith("/storage/v1/object/content-assets/topics/3197/characters/")
        return Response()
    monkeypatch.setattr(store, "request", request)
    monkeypatch.setattr(assets.requests, "get", lambda *a, **k: Response())
    result = store.publish(3197, {**character(), "character_key": "test"}, path, "fingerprint", {})
    assert result["image_generation_status"] == "ready"
    assert saved["generation_model"] == "codex_builtin_image_gen"
    class Unreadable(Response):
        status_code = 403
    monkeypatch.setattr(assets.requests, "get", lambda *a, **k: Unreadable())
    with pytest.raises(RuntimeError, match="publicly readable"):
        store.publish(3197, {**character(), "character_key": "test"}, path, "fingerprint", {})


def test_scene_export_requires_portrait_and_carries_reference_files(monkeypatch, tmp_path):
    import cowork_scene_assets as scenes
    structure = {"scenes": [{"scene_number": i} for i in range(1, 5)],
                 "image_grid_prompts": [{"scene_numbers": [1, 2, 3, 4], "prompt": "A grid"}]}
    base = "https://test.supabase.co"
    monkeypatch.setattr(scenes, "_topic", lambda _: ({"id": 3197}, structure, base, {}))
    with pytest.raises(RuntimeError, match="character reference"):
        scenes.export_manifest("3197", tmp_path / "manifest.json", "content-assets")
    portrait = tmp_path / "reference.png"
    Image.new("RGB", (512, 512), "blue").save(portrait)
    class Response:
        content = portrait.read_bytes()
        def raise_for_status(self): pass
    monkeypatch.setattr(scenes.requests, "get", lambda *a, **k: Response())
    structure["character_anchors"] = {"main_character": {
        **character(), "image_url": base + "/storage/v1/object/public/content-assets/reference.png"}}
    import json
    result = json.loads(scenes.export_manifest("3197", tmp_path / "manifest.json", "content-assets").read_text(encoding="utf-8"))
    assert pathlib.Path(result["grids"][0]["character_references"][0]["local_file"]).exists()
    assert "never video clips" in result["generation_instruction"]


def test_project_link_preserves_edits_and_uses_compare_and_swap(monkeypatch, tmp_path):
    import copy
    store = object.__new__(assets.CharacterAssetStore)
    rows = [
        {"id": "active", "status": "in_progress", "submitted_at": None, "updated_at": "stamp",
         "project_payload": {"script": "final", "thumbnail_url": "keep"}, "source_payload": {}, "progress_payload": {}},
        {"id": "edited", "project_payload": {"script": "user edit"}},
        {"id": "submitted", "submitted_at": "stamp", "project_payload": {"script": "final"}},
    ]
    changed = []
    class Response:
        def __init__(self, value): self.value = copy.deepcopy(value)
        def json(self): return self.value
    def request(method, path, **kwargs):
        if method == "PATCH":
            assert kwargs["params"]["updated_at"] == "eq.stamp"
            assert kwargs["params"]["submitted_at"] == "is.null"
            rows[0].update(kwargs["json"])
            changed.append(rows[0]["id"])
            return Response([rows[0]])
        return Response([rows[0]] if "id" in kwargs["params"] else rows)
    monkeypatch.setattr(store, "request", request)
    anchors = {"main_character": {**character(), "image_url": "https://assets.example/portrait.png"}, "supporting_characters": []}
    assert store.sync_matching_projects(3197, "final", anchors, tmp_path) == 1
    assert changed == ["active"]
    assert rows[0]["project_payload"]["thumbnail_url"] == "keep"
    assert list(tmp_path.glob("active-*.json"))
