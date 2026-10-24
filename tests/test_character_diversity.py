import json

import pytest

from worker.character_diversity import (
    CATEGORY_ARCHETYPES,
    archetype_pool,
    diversity_contract,
    enrich_and_validate,
    record_designs,
)


def character(name="민준"):
    return {
        "name": name,
        "facial_signature": "long face, downturned eyes, mole below left eye",
        "silhouette_signature": "thin build, slightly stooped shoulders, cropped jacket",
        "prop_behavior_signature": "touches an old watch when tense",
        "palette": ["navy", "rust", "ivory"],
        "reference_sheet_prompt": "Same person: front, profile, waist-up, full-body, expression sheet.",
        "scene_variation_rules": "Keep identity geometry; vary only wardrobe, grooming, fatigue, and expression when the story requires it.",
    }


def test_every_product_category_has_a_large_archetype_pool():
    required = {"옛날이야기", "탈북사연", "한국사연", "해외감동", "무협", "황혼19금",
                "English Folktales", "日本昔話", "일본사건", "판타지/sf", "일상/웹툰", "지식/미스터리", "힐링/동화"}
    assert required <= set(CATEGORY_ARCHETYPES)
    assert all(len(CATEGORY_ARCHETYPES[key]) >= 8 for key in required)
    assert archetype_pool({"category_name": "판타지·SF"}) == CATEGORY_ARCHETYPES["판타지/sf"]


def test_contract_contains_all_six_character_diversity_rules(monkeypatch, tmp_path):
    monkeypatch.setenv("AIR_CHARACTER_DIVERSITY_REGISTRY", str(tmp_path / "registry.json"))
    contract = diversity_contract({"category_name": "한국사연"})
    for phrase in ("visual_dna_en", "Recent designs", "three signature", "palette", "reference_sheet_prompt", "scene_variation_rules"):
        assert phrase in contract


def test_designs_are_recorded_and_two_matching_signature_slots_are_rejected(monkeypatch, tmp_path):
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("AIR_CHARACTER_DIVERSITY_REGISTRY", str(registry))
    payload = {"category_name": "한국사연"}
    first = {"main_character": character(), "supporting_characters": []}
    enrich_and_validate(first, payload)
    record_designs(first, payload)
    saved = json.loads(registry.read_text(encoding="utf-8"))
    assert saved["한국사연"][0]["facial_signature"]

    duplicate = character("서준")
    duplicate["prop_behavior_signature"] = "folds a paper receipt when worried"
    with pytest.raises(ValueError, match="duplicates at least two"):
        enrich_and_validate({"main_character": duplicate, "supporting_characters": []}, payload)


def test_unknown_categories_receive_the_same_six_rule_system(monkeypatch, tmp_path):
    monkeypatch.setenv("AIR_CHARACTER_DIVERSITY_REGISTRY", str(tmp_path / "registry.json"))
    identity = {"main_character": character(), "supporting_characters": []}
    result = enrich_and_validate(identity, {"category_name": "새로운 카테고리"})
    assert len(result["character_design_system"]["archetype_pool"]) >= 8
    assert result["character_design_system"]["rules"] == [
        "character_dna", "recent_duplicate_check", "three_signature_slots",
        "production_palette", "reference_sheet", "scene_variation",
    ]
