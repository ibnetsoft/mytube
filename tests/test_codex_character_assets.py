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


def test_child_portrait_preserves_age_and_safe_guidance(tmp_path):
    class Generator:
        def generate(self, prompt):
            assert "Approved character age: 12" in prompt
            assert "Do not substitute an adult, conceal age" in prompt
            assert "recorded human review" in prompt
            return tmp_path / "portrait.png"
    class Store:
        def publish(self, topic, c, path, fingerprint, payload):
            return {**c, "image_url": "https://assets.example/portrait.png"}
    assets.generate_character_references(
        {"script": "A quiet family moment", "main_character": {
            **character("순덕"), "age_group": "12", "visual_dna_en": "Korean girl, black braid"}},
        {"topic_queue_id": 3292}, None, tmp_path, generator=Generator(), store=Store())


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


def test_upload_saves_design_and_verifies_registry_readback(monkeypatch, tmp_path):
    path = tmp_path / "portrait.png"
    Image.new("RGB", (512, 512), "blue").save(path)
    store = object.__new__(assets.CharacterAssetStore)
    saved = {}
    class Response:
        def __init__(self, value): self.value = value
        def json(self): return self.value
    def request(method, url, **kwargs):
        assert url == "/rest/v1/topic_character_assets"
        if method == "POST": saved.update(kwargs["json"])
        return Response([saved])
    monkeypatch.setattr(store, "request", request)
    monkeypatch.setattr(store, "_upload_gcs_bytes", lambda *args: ("bucket", "topics/3197/characters/test.png", "/image.png"))
    design = {**character(), "character_key": "test", "hair_design_en": "Wide shaved forehead; short forward knot",
              "scene_numbers": [2, 4], "aliases": ["elder son"]}
    result = store.publish(3197, design, path, "fingerprint", {})
    assert result["image_generation_status"] == "ready"
    assert saved["usage_context"]["character_design"]["hair_design_en"] == design["hair_design_en"]
    assert saved["usage_context"]["character_design"]["scene_numbers"] == [2, 4]
    reloaded = store.load_references(3197)[0]
    assert reloaded["aliases"] == ["elder son"]
    assert reloaded["hair_design_en"] == design["hair_design_en"]
    assert reloaded["gcs_path"] == "topics/3197/characters/test.png"
    monkeypatch.setattr(store, "request", lambda *a, **k: Response([]))
    with pytest.raises(RuntimeError, match="read-back"):
        store.publish(3197, design, path, "fingerprint", {})


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
    monkeypatch.setattr(scenes, "_download_gcs_bytes", lambda *args: portrait.read_bytes())
    structure["character_anchors"] = {"main_character": {
        **character(), "character_key": "yeonhwa", "gcs_path": "reference.png",
        "image_url": "/api/std/assets/gcs-file?bucket=air-studio-prod&path=reference.png"}}
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


def test_every_recurring_person_gets_a_stable_saved_design_without_a_three_person_cap(tmp_path):
    designs = [{**character(name), 'scene_numbers': [2, 4], 'hair_design_en': 'Shaved crown; compact forward knot'}
               for name in ['father', 'mother', 'daughter', 'elder son', 'younger son', 'doctor']]
    designs.append({**character('one-scene visitor'), 'scene_numbers': [4, 4]})
    published = []
    class Generator:
        def generate(self, prompt):
            assert 'Shaved crown; compact forward knot' in prompt
            return tmp_path / 'portrait.png'
    class Store:
        def publish(self, topic, character, *args):
            published.append(character)
            return {**character, 'image_url': '/reference.png'}
    def run(supporting):
        return assets.generate_character_references({'script': 'final', 'main_character': designs[0],
            'supporting_characters': supporting}, {'topic_queue_id': 3373}, None, tmp_path,
            generator=Generator(), store=Store())
    first = run(designs[1:])
    second = run(list(reversed(designs[1:])))
    assert first['character_image_generation']['count'] == 6
    assert {c['name']: c['character_key'] for c in first['supporting_characters']} == {
        c['name']: c['character_key'] for c in second['supporting_characters']}
    assert all(c['name'] != 'one-scene visitor' for c in published)


def test_saved_portrait_is_reused_after_reload_and_scene_membership_changes(tmp_path):
    original = {**character('son'), 'hair_design_en': 'Shaved crown; short forward knot',
        'character_key': 'original-key', 'scene_numbers': [2, 4], 'image_url': '/saved.png',
        'storage_bucket': 'bucket', 'storage_object_path': 'saved.png', 'image_sha256': 'hash'}
    saved = []
    class Generator:
        def generate(self, prompt):
            raise AssertionError('Unchanged design must reuse its image')
    class Store:
        def load_references(self, topic): return [original]
        def save_design(self, topic, design, *args): saved.append(design)
    result = assets.generate_character_references({'script': 'final', 'main_character': {
        **original, 'scene_numbers': [2, 4, 8], 'image_url': '/stale-browser-thumbnail'}},
        {'topic_queue_id': 3373}, None, tmp_path, generator=Generator(), store=Store())
    assert result['main_character']['image_url'] == '/saved.png'
    assert result['main_character']['character_key'] == 'original-key'
    assert saved[0]['scene_numbers'] == [2, 4, 8]
    assert saved[0]['image_sha256'] == 'hash'


def test_registry_only_approved_design_wins_over_a_new_model_interpretation(tmp_path):
    from worker.character_continuity import LEGACY_REFERENCE_HAIR_LOCK
    original = {**character('son'), 'character_key': 'approved-son', 'image_url': '/approved.png',
                'storage_bucket': 'bucket', 'storage_object_path': 'approved.png'}
    class Store:
        def load_references(self, topic): return [original]
        def save_design(self, topic, result, *args):
            assert result['visual_dna_en'] == original['visual_dna_en']
    class Generator:
        def generate(self, prompt): raise AssertionError('Do not replace the approved design')
    changed = {**character('son'), 'visual_dna_en': 'A newly invented face',
               'wardrobe_en': 'Different clothing', 'hair_design_en': 'Full hair instead of shaved crown',
               'scene_numbers': [3, 7]}
    result = assets.generate_character_references({'script': 'final', 'main_character': changed},
        {'topic_queue_id': 3373}, None, tmp_path, generator=Generator(), store=Store())['main_character']
    assert result['image_url'] == '/approved.png'
    assert result['hair_design_en'] == LEGACY_REFERENCE_HAIR_LOCK
    assert result['wardrobe_en'] == original['wardrobe_en']
    assert result['scene_numbers'] == [3, 7]


def test_exact_saved_key_wins_over_legacy_rows_with_the_same_name(tmp_path):
    canonical = {**character('son'), 'hair_design_en': 'Exact approved knot',
                 'character_key': 'canonical', 'image_url': '/canonical.png'}
    class Store:
        def load_references(self, topic): return [{**canonical, 'character_key': 'old', 'image_url': '/old.png'}, canonical]
        def save_design(self, *args): pass
    class Generator:
        def generate(self, prompt): raise AssertionError('Use the exact saved key')
    result = assets.generate_character_references({'script': 'final', 'main_character': canonical},
        {'topic_queue_id': 3373}, None, tmp_path, generator=Generator(), store=Store())
    assert result['main_character']['image_url'] == '/canonical.png'
    with pytest.raises(RuntimeError, match='Multiple saved designs'):
        assets.generate_character_references({'script': 'final', 'main_character': character('son')},
            {'topic_queue_id': 3373}, None, tmp_path, generator=Generator(), store=Store())
