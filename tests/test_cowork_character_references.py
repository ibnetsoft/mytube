import io
import json
import pathlib
import sys

import pytest
from PIL import Image


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worker"))
import cowork_scene_assets as assets
import image_recovery
import manga_layer_generation


def _character(index, scenes):
    return {
        "name": f"Person {index}", "character_key": f"person-{index}", "aliases": [f"Role {index}"],
        "image_url": f"/api/std/assets/gcs-file?path=person-{index}.png",
        "gcs_path": f"person-{index}.png", "scene_numbers": scenes,
        "visual_dna_en": f"Distinct face {index}", "wardrobe_en": f"Robe color {index}",
        "hair_design_en": f"Shaved scalp width {index}, low topknot pointed left {index}",
        "continuity_instruction": "Keep this person's approved design unchanged.",
    }


def _export(monkeypatch, path, characters, census=None):
    structure = {
        "scenes": [{"scene_number": n, "image_prompt": f"Original visual beat {n}."} for n in range(1, 9)],
        "image_grid_prompts": [
            {"grid_number": 1, "scene_numbers": [1, 2, 3, 4], "prompt": "First four panels."},
            {"grid_number": 2, "scene_numbers": [5, 6, 7, 8], "prompt": "Last four panels."},
        ],
        "character_anchors": {"main_character": characters[0], "supporting_characters": characters[1:]},
    }
    if census is not None:
        structure["scene_cast"] = census
    png = io.BytesIO()
    Image.new("RGB", (512, 512), "blue").save(png, format="PNG")
    monkeypatch.setattr(assets, "_topic", lambda _: ({"id": 123}, structure, "", {}))
    monkeypatch.setattr(assets, "_download_gcs_bytes", lambda *args: png.getvalue())
    assets.export_manifest("123", path, "air-studio-prod")
    return json.loads(path.read_text(encoding="utf-8"))


def test_exports_every_recurring_person_with_stable_named_identity_and_exact_hair(monkeypatch, tmp_path):
    characters = [_character(n, [1, 2, 5, 6]) for n in range(1, 7)]
    first = _export(monkeypatch, tmp_path / "first" / "manifest.json", characters)
    second = _export(monkeypatch, tmp_path / "second" / "manifest.json",
                     [characters[0], *reversed(characters[1:])])
    assert len(first["character_references"]) == 6
    assert all(len(grid["character_references"]) == 6 for grid in first["grids"])
    first_files = {ref["character_key"]: pathlib.Path(ref["local_file"]).name for ref in first["character_references"]}
    second_files = {ref["character_key"]: pathlib.Path(ref["local_file"]).name for ref in second["character_references"]}
    assert first_files == second_files
    for reference, source in zip(first["character_references"], characters):
        assert pathlib.Path(reference["local_file"]).is_file()
        for field in ("hair_design_en", "visual_dna_en", "wardrobe_en", "scene_numbers", "aliases"):
            assert reference[field] == source[field]
        assert source["hair_design_en"] in first["grids"][0]["prompt"]
        assert source["hair_design_en"] in first["grids"][1]["prompt"]


def test_complete_cast_filters_grid_attachments_and_recovery_jobs(monkeypatch, tmp_path):
    characters = [_character(n, [1, 2] if n <= 4 else [5, 6]) for n in range(1, 7)]
    census = [{"scene_number": n, "characters":
               [f"Person {i}" for i in (range(1, 5) if n <= 4 else range(5, 7))]}
              for n in range(1, 9)]
    manifest = _export(monkeypatch, tmp_path / "manifest.json", characters, census)
    assert len(manifest["character_references"]) == 6
    assert [len(grid["character_references"]) for grid in manifest["grids"]] == [4, 2]
    jobs = image_recovery.initialize(manifest)["jobs"]
    assert [ref["character_key"] for ref in jobs[1]["references"]] == ["person-5", "person-6"]
    assert characters[5]["hair_design_en"] in jobs[1]["prompt"]
    assert characters[0]["hair_design_en"] not in jobs[1]["prompt"]
    state = image_recovery.initialize(manifest)
    state["jobs"][1]["status"] = "quality_failed"
    split = image_recovery.transition(state, {"action": "split_quality", "job_id": "grid-002"})
    assert split["jobs"][2]["scene_numbers"] == [5]
    assert characters[5]["hair_design_en"] in split["jobs"][2]["prompt"]
    assert split["jobs"][2]["references"] == jobs[1]["references"]


def test_incomplete_census_preserves_legacy_references_and_empty_cast_stays_empty(monkeypatch, tmp_path):
    characters = [_character(1, []), _character(2, [])]
    census = [{"scene_number": n, "characters": []} for n in range(1, 8)]
    manifest = _export(monkeypatch, tmp_path / "manifest.json", characters, census)
    assert manifest["grids"][0]["character_references"] == []
    assert len(manifest["grids"][1]["character_references"]) == 2
    jobs = image_recovery.initialize(manifest)["jobs"]
    assert jobs[0]["references"] == []
    assert len(jobs[1]["references"]) == 2


def test_aliases_and_saved_occurrences_keep_applicable_references():
    references = [_character(1, []), _character(2, [2]), _character(3, [8])]
    census = [{"scene_number": n, "characters": ["Role 1"]} for n in range(1, 5)]
    assert [ref["character_key"] for ref in assets._grid_character_references(references, census, [1, 2, 3, 4])] == [
        "person-1", "person-2"]


@pytest.mark.parametrize("invalid", ["missing_key", "duplicate_key", "missing_portrait"])
def test_missing_or_ambiguous_saved_reference_stops_export(monkeypatch, tmp_path, invalid):
    characters = [_character(n, [1, 2]) for n in range(1, 6)]
    if invalid == "missing_key":
        characters[-1].pop("character_key")
    elif invalid == "duplicate_key":
        characters[-1]["character_key"] = characters[0]["character_key"]
    else:
        characters[-1].pop("image_url")
    with pytest.raises(RuntimeError, match="character|Character"):
        _export(monkeypatch, tmp_path / "manifest.json", characters)
    assert not (tmp_path / "manifest.json").exists()


def test_manga_layer_keeps_full_identity_and_exact_hair_prompt(monkeypatch, tmp_path):
    character = _character(4, [1, 2])
    manifest_path = tmp_path / "manifest.json"
    manifest = _export(monkeypatch, manifest_path, [character])
    references = manga_layer_generation._references(manifest, manifest_path)
    reference = {"character_key": character["character_key"], **references[character["character_key"]]}
    prompt = manga_layer_generation._prompt(
        {"scene_text": "The younger son waits.", "image_prompt": "An ordinary historical family scene."},
        {"scene_number": 1, "template": "ink_splat_impact"}, "character", reference)
    assert character["hair_design_en"] in prompt
    assert character["visual_dna_en"] in prompt
    assert "shaved-scalp area" in prompt
    assert "Never swap another person's hairstyle or face" in prompt


def test_hair_locks_do_not_change_publish_source_and_survive_single_scene_recovery(monkeypatch, tmp_path):
    character = _character(1, [1, 2])
    manifest = _export(monkeypatch, tmp_path / "manifest.json", [character])
    for scene in manifest["scene_specs"]:
        original = {"scene_number": scene["scene_number"], "image_prompt": f"Original visual beat {scene['scene_number']}."}
        assert assets._publish_source_snapshot(scene, 1) == assets._publish_source_snapshot(original, 1)
        assert character["hair_design_en"] in scene["generation_image_prompt"]
    state = image_recovery.initialize(manifest)
    state["jobs"][0].update(status="quality_failed", attempts=1)
    split = image_recovery.transition(state, {"action": "split_quality", "job_id": "grid-001"})
    children = [job for job in split["jobs"] if job["layout"] == "single"]
    assert len(children) == 4
    assert all(character["hair_design_en"] in job["prompt"] for job in children)
