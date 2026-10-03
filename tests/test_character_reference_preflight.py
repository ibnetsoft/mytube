import copy
import io
import json
import pathlib
import sys

import pytest
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worker"))
import character_reference_preflight as preflight


def character(name, *, ready=False):
    result = {"name": name, "aliases": [], "gender": "male", "age_group": "adult",
              "scene_numbers": [1, 2], "visual_dna_en": f"Approved face of {name}",
              "wardrobe_en": f"Approved robe of {name}", "hair_design_en": f"Exact shaved scalp and knot for {name}",
              "continuity_instruction": "Preserve the saved design."}
    if ready:
        result.update(character_key=f"key-{name}", image_url=f"/ref/{name}.png", gcs_path=f"ref/{name}.png",
                      storage_object_path=f"ref/{name}.png", storage_bucket="test", image_style="anime illustration")
    return result


def fixture():
    lead = character("Father", ready=True)
    row = {"id": 3373, "pregenerated_script": "  Father and both sons talk.\n", "language": "ja"}
    structure = {"scenes": [{"scene_number": n, "scene_text": f"Family scene {n}",
                             "image_prompt": f"The father with both sons in scene {n}"} for n in (1, 2)],
                 "characters": [{"id": "older", "name": "Older son"}, {"id": "younger", "name": "Younger son"}],
                 "content_setting": {"language": "ja", "setting_country": "일본", "era_region": "Edo Shimosa",
                                     "image_style": "anime illustration"},
                 "character_anchors": {"main_character": lead, "supporting_characters": []}}
    return row, structure


class Store:
    def __init__(self, references):
        self.references = copy.deepcopy(references)
        self.linked = []

    def load_references(self, topic):
        assert topic == 3373
        return copy.deepcopy(self.references)

    def save_design(self, topic, result, fingerprint, payload):
        result = {**copy.deepcopy(result), "cast_census": copy.deepcopy(payload["_character_census"])}
        self.references = [ref for ref in self.references if ref.get("character_key") != result["character_key"]]
        self.references.append(result)

    def publish(self, topic, character, path, fingerprint, payload):
        result = {**character, "image_url": f"/ref/{character['name']}.png",
                  "gcs_path": f"ref/{character['name']}.png", "storage_object_path": f"ref/{character['name']}.png"}
        self.save_design(topic, result, fingerprint, payload)
        return result

    def sync_matching_projects(self, topic, script, anchors, directory):
        self.linked.append((topic, script, copy.deepcopy(anchors)))


class Runner:
    def __init__(self):
        self.contexts = []

    def finalize_character_identity(self, job, context, setting):
        self.contexts.append(copy.deepcopy(context))
        assert setting["era_region"] == "Edo Shimosa"
        return {"main_character": character("Father"),
                "supporting_characters": [character("Older son"), character("Younger son")],
                "scene_cast": [{"scene_number": n, "characters": ["Father", "Older son", "Younger son"]}
                               for n in (1, 2)]}


class Generator:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return pathlib.Path("unused-mocked-portrait.png")


def test_legacy_export_prepares_missing_sons_once_and_links_using_exact_script(tmp_path):
    row, structure = fixture()
    original = copy.deepcopy(structure)
    store = Store([structure["character_anchors"]["main_character"]])
    runner, generator = Runner(), Generator()
    result = preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    assert structure == original
    assert len(generator.prompts) == 2
    assert len(result["character_anchors"]["supporting_characters"]) == 2
    assert runner.contexts[0]["declared_characters"] == structure["characters"]
    assert runner.contexts[0]["existing_character_anchors"]["main_character"]["image_url"] == "/ref/Father.png"
    assert store.linked[0][1] == row["pregenerated_script"]
    for saved in store.references:
        assert saved["cast_census"]["character_names"] == ["Father", "Older son", "Younger son"]
        assert saved["cast_census"]["fingerprint"] == preflight.census_fingerprint(row["pregenerated_script"], structure["scenes"])
    again = preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    assert len(runner.contexts) == 1 and len(generator.prompts) == 2
    assert again["character_anchors"]["character_image_generation"]["status"] == "ready"
    assert [c["name"] for c in again["supporting_characters"]] == ["Older son", "Younger son"]
    assert len(store.linked) == 2


def test_changed_scene_recounts_cast_but_preserves_saved_portraits(tmp_path):
    row, structure = fixture()
    store, runner, generator = Store([structure["character_anchors"]["main_character"]]), Runner(), Generator()
    preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    structure["scenes"][1]["image_prompt"] += ", now a closer view"
    preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    assert len(runner.contexts) == 2
    assert len(generator.prompts) == 2


def test_incomplete_cached_cast_cannot_skip_missing_reference(tmp_path):
    row, structure = fixture()
    store, runner, generator = Store([structure["character_anchors"]["main_character"]]), Runner(), Generator()
    preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    store.references = [c for c in store.references if c["name"] != "Younger son"]
    repaired = preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    assert len(runner.contexts) == 2 and len(generator.prompts) == 3
    assert len(repaired["supporting_characters"]) == 2


def test_validated_current_package_bypasses_store_and_generation(tmp_path):
    row, structure = fixture()
    store, runner, generator = Store([structure["character_anchors"]["main_character"]]), Runner(), Generator()
    ready = preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    class NoCalls:
        def __getattr__(self, name):
            pytest.fail(f"Unnecessary call: {name}")
    result = preflight.ensure_character_references(row, ready, tmp_path, runner=NoCalls(), store=NoCalls(), generator=NoCalls())
    assert len(result["supporting_characters"]) == 2


def test_exact_saved_key_wins_over_same_name_legacy_design(tmp_path):
    row, structure = fixture()
    lead = structure["character_anchors"]["main_character"]
    legacy = {**lead, "character_key": "old-key", "visual_dna_en": "Wrong legacy face"}
    store, runner, generator = Store([lead, legacy]), Runner(), Generator()
    result = preflight.ensure_character_references(row, structure, tmp_path, runner=runner, store=store, generator=generator)
    assert runner.contexts[0]["existing_character_anchors"]["main_character"]["character_key"] == lead["character_key"]
    assert result["main_character"]["visual_dna_en"] == lead["visual_dna_en"]
    assert len(generator.prompts) == 2


def test_missing_final_script_or_invalid_census_stops_before_images(tmp_path):
    row, structure = fixture()
    store, generator = Store([]), Generator()
    with pytest.raises(RuntimeError, match="Final pregenerated_script"):
        preflight.ensure_character_references({**row, "pregenerated_script": ""}, structure, tmp_path,
                                              store=store, generator=generator)
    class InvalidRunner(Runner):
        def finalize_character_identity(self, *args):
            identity = super().finalize_character_identity(*args)
            identity["scene_cast"].pop()
            return identity
    with pytest.raises(ValueError, match="every final scene"):
        preflight.ensure_character_references(row, structure, tmp_path, runner=InvalidRunner(), store=store, generator=generator)
    assert generator.prompts == [] and store.linked == []


def test_export_handoff_preflights_legacy_topic_and_attaches_new_sons(monkeypatch, tmp_path):
    import cowork_scene_assets as exporter
    row, structure = fixture()
    structure["image_grid_prompts"] = [{"scene_numbers": [1, 2, 1, 2], "prompt": "The family in four panels."}]
    store, runner, generator = Store([structure["character_anchors"]["main_character"]]), Runner(), Generator()
    ensure = preflight.ensure_character_references
    monkeypatch.setattr(preflight, "ensure_character_references",
                        lambda row, structure, output: ensure(row, structure, output,
                            runner=runner, store=store, generator=generator))
    monkeypatch.setattr(exporter, "_topic", lambda _: (row, structure, "", {}))
    png = io.BytesIO()
    Image.new("RGB", (512, 512), "blue").save(png, format="PNG")
    monkeypatch.setattr(exporter, "_download_gcs_bytes", lambda *args: png.getvalue())
    path = exporter.export_manifest("3373", tmp_path / "manifest.json", "test")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert len(generator.prompts) == 2
    assert [ref["name"] for ref in manifest["grids"][0]["character_references"]] == ["Father", "Older son", "Younger son"]
    assert "Exact shaved scalp and knot for Older son" in manifest["grids"][0]["prompt"]
    assert "Exact shaved scalp and knot for Younger son" in manifest["grids"][0]["prompt"]
