"""Prepare missing recurring designs before exporting scene-image work.

The registry stores the cast census, so legacy topic rows need not be replaced.
Existing projects are linked only through the character store's script/CAS guard.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .character_continuity import character_design_anchors, validate_character_identity
    from .content_language import resolve_setting
except ImportError:
    from character_continuity import character_design_anchors, validate_character_identity
    from content_language import resolve_setting


POLICY = "main_and_every_person_in_two_distinct_scenes"


def census_fingerprint(script: str, scenes: list[dict]) -> str:
    source = {"script": script, "scenes": [
        {"scene_number": scene.get("scene_number") or scene.get("scene_order") or index,
         "scene_id": scene.get("scene_id"),
         "scene_text": scene.get("scene_text") or scene.get("narration"),
         "image_prompt": scene.get("image_prompt")}
        for index, scene in enumerate(scenes, 1)]}
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _characters(anchors: dict) -> list[dict]:
    return [item for item in [anchors.get("main_character"), *(anchors.get("supporting_characters") or [])]
            if isinstance(item, dict)]


def _ready_identity(identity: dict, scenes: list[dict]) -> dict | None:
    try:
        validated = validate_character_identity(identity, scenes)
    except (ValueError, TypeError, KeyError):
        return None
    characters = _characters(validated)
    keys = [str(character.get("character_key") or "").strip() for character in characters]
    if (any(not key for key in keys) or len(set(keys)) != len(keys)
            or any(not character.get("image_url") or not (character.get("gcs_path")
                       or character.get("storage_object_path")) for character in characters)):
        return None
    return character_design_anchors(validated)


def _apply(structure: dict, anchors: dict) -> dict:
    result = copy.deepcopy(structure)
    result.update(main_character=anchors["main_character"], supporting_characters=anchors["supporting_characters"],
                  character_anchors=anchors, scene_cast=anchors["scene_cast"], character_reference_status="ready")
    return result


def _existing_designs(anchors: dict, saved: list[dict]) -> dict:
    prior = _characters(copy.deepcopy(anchors))
    for index, character in enumerate(prior):
        exact = [reference for reference in saved if character.get("character_key")
                 and reference.get("character_key") == character["character_key"]]
        matches = exact or [reference for reference in saved if reference.get("name") == character.get("name")]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple saved designs for character {character.get('name')}; select the canonical design first")
        if matches:
            prior[index] = {**character, **matches[0]}
    names = {character.get("name") for character in prior}
    for name in dict.fromkeys(reference.get("name") for reference in saved):
        if not isinstance(name, str) or not name.strip() or name in names:
            continue
        matches = [reference for reference in saved if reference.get("name") == name]
        if len(matches) != 1:
            raise RuntimeError(f"Multiple saved designs for character {name}; select the canonical design first")
        prior.append(matches[0])
        names.add(name)
    return {"main_character": prior[0] if prior else None, "supporting_characters": prior[1:]}


def ensure_character_references(row: dict, structure: dict, output_dir: Path, *,
                                runner=None, store=None, generator=None) -> dict:
    script = str(row.get("pregenerated_script") or "")
    scenes = structure.get("scenes")
    if not script.strip():
        raise RuntimeError("Final pregenerated_script is required before character reference preflight")
    if not isinstance(scenes, list) or not scenes or any(not isinstance(scene, dict) for scene in scenes):
        raise RuntimeError("Final scenes are required before character reference preflight")
    topic_id = int(row["id"])
    fingerprint = census_fingerprint(script, scenes)
    anchors = structure.get("character_anchors") or {
        "main_character": structure.get("main_character"),
        "supporting_characters": structure.get("supporting_characters") or [],
        "scene_cast": structure.get("scene_cast"),
    }
    census = anchors.get("cast_census") or {}
    if census.get("fingerprint") == fingerprint and census.get("reference_policy") == POLICY:
        ready = _ready_identity({**anchors, "scene_cast": census.get("scene_cast")}, scenes)
        if ready:
            return _apply(structure, ready)

    if store is None:
        from codex_character_assets import CharacterAssetStore
        store = CharacterAssetStore()
    saved = store.load_references(topic_id)
    censuses = [reference.get("cast_census") for reference in saved
                if isinstance(reference.get("cast_census"), dict)
                and reference["cast_census"].get("fingerprint") == fingerprint
                and reference["cast_census"].get("reference_policy") == POLICY]
    for census in censuses:
        names = census.get("character_names")
        if (not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names)
                or len(set(names)) != len(names)):
            continue
        candidates = [[reference for reference in saved if reference.get("name") == name
                       and reference.get("cast_census") == census] for name in names]
        if any(len(matches) != 1 for matches in candidates):
            continue
        ordered = [matches[0] for matches in candidates]
        ready = _ready_identity({"main_character": ordered[0], "supporting_characters": ordered[1:],
                                 "scene_cast": census.get("scene_cast"), "cast_census": census,
                                 "reference_policy": POLICY}, scenes)
        if ready:
            store.sync_matching_projects(topic_id, script, ready, output_dir / "project-link-backups")
            return _apply(structure, ready)

    # Registry references override the same saved identity while retaining every
    # other approved design. A new census may add people, never discard portraits.
    existing = _existing_designs(anchors, saved)
    setting_payload = {**row, **structure, **(structure.get("content_setting") or {}),
                       "topic_queue_id": topic_id}
    setting_payload["image_style"] = setting_payload.get("image_style") or row.get("assigned_image_style") or "realistic"
    setting = resolve_setting(setting_payload)
    if runner is None:
        from codex_content_runner import CodexStagedContentRunner
        runner = CodexStagedContentRunner()
    identity = runner.finalize_character_identity(f"reference-preflight-{topic_id}-{fingerprint[:12]}",
        {"script": script, "scenes": scenes, "existing_character_anchors": existing,
         "declared_characters": structure.get("characters") or [],
         "topic": row.get("generated_title") or row.get("topic"), "content_setting": setting}, setting)
    identity = validate_character_identity(identity, scenes, existing)
    census = {"fingerprint": fingerprint, "scene_cast": identity["scene_cast"],
              "character_names": [character["name"] for character in _characters(identity)],
              "reference_policy": POLICY}
    from codex_character_assets import generate_character_references
    ready = generate_character_references({"script": script, **identity},
        {**setting_payload, **setting, "_character_census": census}, getattr(runner, "config", None),
        output_dir / "portraits", generator=generator, store=store)
    ready.update(scene_cast=identity["scene_cast"], cast_census=census, reference_policy=POLICY)
    if _ready_identity(ready, scenes) is None:
        raise RuntimeError("Recurring character references are incomplete after preflight")
    store.sync_matching_projects(topic_id, script, ready, output_dir / "project-link-backups")
    return _apply(structure, ready)
