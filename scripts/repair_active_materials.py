"""Review full material packages, preserving completed projects and media assets.

Builds a local candidate before any write. Every publish operation is backed up,
version checked, and read back. Conflicts stop that topic, never erase user work.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_active_content import OUT, ACTIVE, PROTECTED, fetch, obj, write_report
from scripts.repair_existing_topic_scripts import (
    _headers, _repair_with_codex, CodexContentConfig, CodexStagedContentRunner,
    _duration_seconds, _existing_sections, repair_missing_scene_durations,
)
from worker.codex_content_runner import _validate_video_prompt
from worker.senior_script_guard import contract, review_issues, text_issues
from services.category_writing_profiles import resolve_category_writing_profile
import requests

VERSION = "active_materials_v1"
MEDIA_KEYS = ("image_url", "video_url", "image_path", "video_path", "asset_status", "metadata")
TEXT_KEYS = ("scene_text", "narration", "script_excerpt", "scene_summary", "scene_situation", "scene_title", "scene_emotion",
    "image_prompt", "video_prompt", "retention_hook", "emotional_shift", "character_choice",
    "scene_purpose", "dramatic_function", "reveal_or_question")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_patch(base, patch):
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        merged[key] = merge_patch(merged[key], value) if isinstance(merged.get(key), dict) and isinstance(value, dict) else copy.deepcopy(value)
    return merged


def refresh_grids(structure):
    """Compose approved scene prompts without creating new visual instructions."""
    from services.image_grid_prompts import grid_windows, make_compact_image_grid_prompt
    old_grids = structure.get("image_grid_prompts") or []
    positions = ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right")
    grids = []
    for index, (start, end) in enumerate(grid_windows(len(structure["scenes"]))):
        grid = copy.deepcopy(old_grids[index]) if index < len(old_grids) else {}
        panels = [{"position": positions[i], "scene_id": f"scene{start+i+1:03d}",
            "scene_number": start+i+1, "panel_prompt": scene["image_prompt"]}
            for i, scene in enumerate(structure["scenes"][start:end])]
        grid["panels"] = panels
        grid.update(template="strict_2x2_compact_v1", grid_number=index+1, panel_count=4,
            scene_numbers=[p["scene_number"] for p in panels], scene_ids=[p["scene_id"] for p in panels])
        grid["prompt"] = make_compact_image_grid_prompt(panels,
            shared_style="Preserve the exact character appearances and visual style specified in each approved panel.")
        grids.append(grid)
    structure["image_grid_prompts"] = grids
    structure["image_grid_prompt_status"] = "ready"


def user_script_changed(project, original_topic_script):
    editor, source = obj(project.get("project_payload")), obj(project.get("source_payload"))
    original = editor.get("original_worker_script") or source.get("pregenerated_script") or original_topic_script
    if editor.get("script") and editor["script"] != original:
        return True
    # Do not overwrite independently edited subtitles when no provenance is available.
    subtitles = editor.get("subtitles") or []
    normalize = lambda s: re.sub(r"[\W_]+", "", str(s or ""))
    if subtitles:
        text = "".join(str(s.get("text") or "") for s in subtitles)
        if normalize(text) != normalize(original):
            return True
    return False


def contains_visual_reference(value):
    """Check nested editor/source records, not just topic scene URL columns."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"image_url", "video_url", "image_path", "video_path", "storage_object_path"} and child:
                return True
            if contains_visual_reference(child):
                return True
    elif isinstance(value, list):
        return any(contains_visual_reference(child) for child in value)
    return False


def merge_structure(original, revised):
    """Project snapshots can contain media absent from the topic's source."""
    original = obj(original)
    old_scenes = original.get("scenes") or []
    new_scenes = revised["scenes"]
    if old_scenes and len(old_scenes) != len(new_scenes):
        raise RuntimeError("Project scene count differs from source; reconciliation required")
    merged = {**copy.deepcopy(original), **copy.deepcopy(revised)}
    if old_scenes:
        for i, (old, new) in enumerate(zip(old_scenes, new_scenes)):
            if int(old.get("scene_number") or old.get("scene_order") or i+1) != i+1:
                raise RuntimeError("Project scene numbering differs; reconciliation required")
            # The project's visual/timing fields remain authoritative.
            merged["scenes"][i] = {**copy.deepcopy(new), **copy.deepcopy(old),
                **{k: new[k] for k in TEXT_KEYS if k in new}}
    return merged


def validate_package(package, original):
    scenes = package["structure"]["scenes"]
    old = obj(original.get("pregenerated_structure")).get("scenes") or []
    if len(scenes) != len(old) or not scenes:
        raise ValueError("Scene count changed or empty")
    errors = text_issues([{"scene_order": i, "text": s["scene_text"]} for i, s in enumerate(scenes, 1)], original)
    errors += review_issues(package["script_quality_report"])
    if package.get("repair_scope") == "narration_only":
        for scene, source in zip(scenes, old):
            for key in (*MEDIA_KEYS, "image_prompt", "video_prompt"):
                if scene.get(key) != source.get(key):
                    errors.append(f"Narration-only repair cannot change {key}")
        if errors:
            raise ValueError("; ".join(errors))
        return
    if len(scenes) >= 4:
        from services.image_grid_prompts import validate_image_grid_prompt_readiness
        validate_image_grid_prompt_readiness(scenes, package["structure"].get("image_grid_prompts") or [],
            status=package["structure"].get("image_grid_prompt_status"), require_status="ready", require_compact_template=True)
    for i, (scene, source) in enumerate(zip(scenes, old), 1):
        for key in MEDIA_KEYS:
            if scene.get(key) != source.get(key):
                errors.append(f"scene {i}: existing media changed ({key})")
        if len(str(scene.get("image_prompt") or "")) < 120:
            errors.append(f"scene {i}: missing image prompt")
        if i <= 12:
            try:
                _validate_video_prompt(scene.get("video_prompt"), i)
            except RuntimeError as exc:
                errors.append(str(exc))
    for key, subset in (("image_prompt", scenes), ("video_prompt", scenes[:12]), ("scene_summary", scenes)):
        values = [s.get(key) for s in subset]
        if len(set(values)) != len(values):
            errors.append(f"duplicate {key}")
    meta = package["publish_metadata"]
    if len(str(meta.get("description") or "")) < 120 or not meta.get("tags"):
        errors.append("Incomplete metadata")
    report = package.get("material_quality_report") or {}
    for key in ("title_payoff", "engagement", "prompt_alignment", "character_continuity", "metadata_accuracy"):
        item = obj(obj(report.get("checks")).get(key))
        if item.get("pass") is not True or len(str(item.get("evidence") or "")) < 12:
            errors.append(f"Material review failed: {key}")
    if report.get("verdict") != "pass" or report.get("critical_issues") != []:
        errors.append("Material review not approved")
    if errors:
        raise ValueError("; ".join(errors[:20]))


def compact_candidate(package):
    compact = {k: v for k,v in package.items() if k not in ("source_hash", "structure", "script_quality_report")}
    compact["structure"] = {"story_core": package["structure"].get("story_core"), "scenes": [
        {k: s[k] for k in ("scene_order", "scene_number", "duration_seconds", *TEXT_KEYS) if k in s}
        for s in package["structure"]["scenes"]]}
    return compact


def refine_candidate(package, row, path):
    """Address review findings without regenerating already-correct assets or DNA."""
    fresh_review = package.get("material_quality_report", {}).get("script_quality_report")
    if fresh_review and not review_issues(fresh_review):
        package["script_quality_report"] = fresh_review
    runner = CodexStagedContentRunner(CodexContentConfig.from_environment())
    context = {"candidate": compact_candidate(package), "category_contract": contract(row),
        "character_reference_plan": package.get("character_reference_plan") or [],
        "required_fields": list(TEXT_KEYS)}
    print(f"[{row['id']}] targeted correction of material-review findings", flush=True)
    result = runner._stage(f"materials-{row['id']}-{VERSION}", "targeted-review-correction", context,
        "Correct only the issues identified in candidate.material_quality_report. Preserve valid narration and visual DNA. "
        "Return {'scene_patches':[{'scene_order':N, ...only changed required_fields...}], 'publish_metadata':{...optional}, "
        "'narrative_blueprint':{...optional}, 'story_core':{...optional}}. "
        "In particular align every scene_emotion with its actual action and emotional_shift; no obsolete emotional labels. "
        "If changing narration or an action, update its image/video prompts consistently. Maintain scene order/count and durations; "
        "retain character faces and wardrobe exactly. Opening narration must flow across 5-second cuts, not a list of short completed sentences. "
        "Resolve missing movements explicitly without adding new characters. Do not repeat generic hooks. "
        "No scores or approval claims. Never output media URLs or replace assets."
    )
    old_script = package["script"]
    scenes = package["structure"]["scenes"]
    for edit in result.get("scene_patches") or []:
        number = edit.get("scene_order")
        if type(number) is not int or not 1 <= number <= len(scenes):
            raise ValueError("Invalid correction scene mapping")
        scene = scenes[number-1]
        for key in TEXT_KEYS:
            if key in edit:
                scene[key] = edit[key]
        if "scene_text" in edit:
            scene["narration"] = scene["script_excerpt"] = scene["scene_text"]
    if result.get("publish_metadata"):
        package["publish_metadata"].update(result["publish_metadata"])
        if result["publish_metadata"].get("title"):
            package["generated_title"] = result["publish_metadata"]["title"]
    if result.get("narrative_blueprint"):
        package["narrative_blueprint"] = merge_patch(obj(package.get("narrative_blueprint")), result["narrative_blueprint"])
        package["structure"]["narrative_blueprint"] = package["narrative_blueprint"]
    if result.get("story_core"):
        package["structure"]["story_core"] = merge_patch(obj(package["structure"].get("story_core")), result["story_core"])
    package["script"] = "\n\n".join(s["scene_text"].strip() for s in scenes)
    refresh_grids(package["structure"])
    if package["script"] != old_script:
        review = runner._stage(f"materials-{row['id']}-{VERSION}", "corrected-script-review",
            {"candidate": compact_candidate(package), "category_contract": contract(row)},
            "Independently review the full narration using every required senior_listening_v3 check. "
            "Return {'script_quality_report':{...}} with all nine checks and specific scene evidence. Do not trust prior author scores.")
        package["script_quality_report"] = review.get("script_quality_report") or {}
        if review_issues(package["script_quality_report"]):
            dump(path, package)
            raise ValueError("Corrected narration still fails independent review")
    review = runner._stage(f"materials-{row['id']}-{VERSION}", "corrected-material-review",
        {"candidate": compact_candidate(package), "category_contract": contract(row)},
        "Independently review the full corrected material package. Return {'material_quality_report':{'verdict':'pass' or 'revise',"
        "'critical_issues':[], 'checks':{'title_payoff':{'pass':true,'evidence':'concrete scenes'}, 'engagement':{...},"
        "'prompt_alignment':{...},'character_continuity':{...},'metadata_accuracy':{...}}}}. "
        "Check every scene, including emotions and chronological locations. Actual image pixels were not inspected. "
        "Do not approve unresolved errors or repeated clipped narration. Do not trust previous scores.")
    package["material_quality_report"] = review.get("material_quality_report") or {}
    dump(path, package)
    validate_package(package, row)
    return package


def resolve_repair_duration(scene, report, index, scene_count):
    duration = scene.get("duration_seconds") or scene.get("target_duration")
    if duration:
        return duration
    durations = report.get("repaired_scene_durations") or []
    if len(durations) != scene_count:
        raise ValueError("Missing scene timing; cannot safely apply a partial duration schedule")
    return durations[index]


def build(row, snapshot):
    topic_id = row["id"]
    decisions_path = OUT / "pending_decisions.json"
    if decisions_path.exists():
        reason = json.loads(decisions_path.read_text(encoding="utf-8")).get(str(topic_id))
        if reason:
            raise ValueError(reason)
    research_path = OUT / "financial_review_sources.json"
    if row.get("category_id") in (3, 8) and research_path.exists():
        row = {**row, "_review_research": json.loads(research_path.read_text(encoding="utf-8"))}
    category = next((c for c in snapshot["categories"] if c["id"] == row["category_id"]), {})
    category_name = category.get("name", "")
    candidate_id = row.get("_project_only_id") or topic_id
    path = OUT / "candidates" / f"{candidate_id}.json"
    source_hash = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if path.exists():
        package = json.loads(path.read_text(encoding="utf-8"))
        if package.get("source_hash") == source_hash:
            refresh_grids(package["structure"])
            try:
                validate_package(package, row)
                dump(path, package)
                return package
            except ValueError as exc:
                return refine_candidate(package, row, path)
    if not obj(row.get("pregenerated_structure")).get("scenes"):
        raise ValueError("No original scene structure: needs new planning, not repair")
    print(f"[{topic_id}] narration repair and independent review", flush=True)
    sections, report = _repair_with_codex(row, category_name, OUT, os.getenv("CODEX_CONTENT_MODEL", ""))
    structure = copy.deepcopy(obj(row["pregenerated_structure"]))
    structure["story_core"] = report["repaired_story_core"]
    structure["narrative_blueprint"] = report["repaired_narrative_blueprint"]
    for i, (scene, section) in enumerate(zip(structure["scenes"], sections)):
        scene["scene_text"] = scene["narration"] = section["text"].strip()
        scene["script_excerpt"] = scene["scene_text"]
        if not scene.get("duration_seconds"):
            scene["duration_seconds"] = resolve_repair_duration(scene, report, i, len(structure["scenes"]))
    script = "\n\n".join(s["text"].strip() for s in sections)
    runner = CodexStagedContentRunner(CodexContentConfig.from_environment())
    context = {
        "topic": row["topic"], "upload_title": row.get("generated_title") or row["topic"],
        "category_id": row["category_id"], "category_name": category_name,
        "language": row.get("language") or "ko", "script": script,
        "narrative_blueprint": report["repaired_narrative_blueprint"],
        "category_contract": contract(row), "writing_profile": resolve_category_writing_profile(category_name),
        "image_style": row.get("assigned_image_style") or "Preserve the concrete style specified by existing prompts/character assets; do not substitute the category default for existing assets.",
        "category_default_for_reference_only": category.get("default_image_style"),
        "character_assets": [c for c in snapshot["characters"] if c.get("topic_queue_id") == topic_id],
        "other_story_character_descriptions": [{k: c.get(k) for k in ("name", "role", "visual_dna_en", "wardrobe_en", "image_style")}
            for c in snapshot["characters"] if c.get("topic_queue_id") != topic_id and str(c.get("category")) == str(row["category_id"])][-30:],
        "existing_metadata": obj(row.get("publish_metadata")),
        "supplemental_verified_research": row.get("_review_research") or {},
        "other_titles": [t.get("generated_title") or t.get("topic") for t in snapshot["topics"] if t["id"] != topic_id],
        "asset_rule": "Preserve the existing story, characters, visual identity, wardrobe, props, scene order and chronology. These are existing projects, not new stories. Do not invent a new style for existing imagery. Do not claim actual image pixels were reviewed; this stage reviews text and recorded asset descriptions.",
    }
    if not context["character_assets"]:
        existing_images = contains_visual_reference(structure)
        for project in snapshot["projects"]:
            if project.get("topic_queue_id") == topic_id:
                existing_images = existing_images or contains_visual_reference(obj(project.get("project_payload"))) or contains_visual_reference(obj(project.get("source_payload")))
                assets = fetch("std_project_assets", project_id=f"eq.{project['id']}")
                existing_images = existing_images or any(a.get("asset_type") in {"image", "video"} for a in assets)
                existing_images = existing_images or contains_visual_reference(fetch("std_project_scenes", project_id=f"eq.{project['id']}"))
        if existing_images:
            raise ValueError("Existing images lack registered character DNA: visual inspection required before redefining appearances")
        print(f"[{topic_id}] establish concrete character descriptions for ungenerated visuals", flush=True)
        anchors = runner._stage(f"materials-{topic_id}-{VERSION}", "character-descriptions", context,
            "There are no recorded character references or generated scene visuals for this topic. "
            "Define stable ORIGINAL visual descriptions for recurring characters from the revised story, before writing scene prompts. "
            "Do not change narrative roles, kinship, age constraints or period. Return {'characters':[{'character_key':'stable-slug',"
            "'name':'story name','role':'role','gender':'...','age_group':'...', 'visual_dna_en':'detailed concrete English face, hair, build, distinguishing features',"
            "'wardrobe_en':'specific period-compatible wardrobe','image_prompt':'English standalone portrait prompt in selected style',"
            "'continuity_instruction':'...'}]}. Give each a distinct appearance; names/roles alone are not DNA. "
            "Describe all recurring named characters but do not invent additional people. Do not claim any reference image exists. "
            "Different stories must not reuse the same stock face. Contrast the new designs with other_story_character_descriptions while respecting the script. "
            "If the content is purely explanatory with no recurring characters, return an empty list and explain why.")
        context["character_assets"] = anchors.get("characters") or []
        if row.get("category_id") not in (3, 8) and not context["character_assets"]:
            raise ValueError("Missing concrete character descriptions")
        for character in context["character_assets"]:
            if len(str(character.get("visual_dna_en") or "")) < 80 or not character.get("wardrobe_en"):
                raise ValueError("Character description is not concrete")
        structure["character_reference_plan"] = context["character_assets"]
        structure["character_reference_status"] = "descriptions_ready_images_pending"
    for start in range(0, len(structure["scenes"]), 12):
        part = structure["scenes"][start:start + 12]
        print(f"[{topic_id}] scene prompts {start + 1}-{start + len(part)}", flush=True)
        task = (
            "Repair each supplied scene's material for an engaging, coherent spoken video. "
            "Return {'scenes':[{'scene_order':N,'scene_title':'...','scene_summary':'...','scene_situation':'...',"
            "'image_prompt':'...','video_prompt':'...','retention_hook':'...','emotional_shift':'...',"
            "'scene_emotion':'one accurate dominant emotion in story language',"
            "'character_choice':'...','scene_purpose':'...','dramatic_function':'...','reveal_or_question':'...'}]}. "
            "Use the actual GLOBAL scene_order from input. Write distinct, plot-specific summaries and motivations in the story language; no generic repeated hooks. "
            "Every image_prompt must be detailed ENGLISH, at least 120 characters: selected style, stable character appearance, setting, "
            "one exact action matching this narration, readable composition and light, 16:9, no text, no watermark. "
            "Preserve existing character DNA; role words like grandmother are not a visual identity. Do not replace the existing protagonist or props. "
            "Include the supplied concrete face/hair/wardrobe traits of each visible character; never substitute 'established face' or 'unspecified gender' for actual descriptions. "
            "For scene numbers 1 through 12, video_prompt must be at least 260 ENGLISH characters and specify a single feasible 5-second action "
            "matching its image, consistent face/clothes/props, no cuts, with exactly ONE camera phrase from: slow push-in, slow pull-back, gentle pan, "
            "gentle tilt, slow dolly, slow tracking shot, locked-off shot, subtle crane movement, slow drift. "
            "End with: no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio. "
            "No copied generic video prompts. For later scenes keep existing video prompt or empty. Never rewrite narration in this stage."
        )
        part_context = {**context, "scenes": [{**s, "scene_order": start+i+1} for i, s in enumerate(part)],
            "already_approved_visual_descriptions": [
                {"scene_order": i+1, "image_prompt": s["image_prompt"]}
                for i, s in enumerate(structure["scenes"][:start])],
            "continuity_requirement": "Reuse the exact character appearance established in prior approved prompts. Do not change age, hair, clothes or face between batches unless the narration explicitly requires it."}
        for attempt in range(2):
            revised = runner._stage(f"materials-{topic_id}-{VERSION}", f"prompts-{start}", part_context, task)
            edits = revised.get("scenes") or []
            try:
                if [s.get("scene_order") for s in edits] != list(range(start + 1, start + len(part) + 1)):
                    raise ValueError("Missing/reordered media scenes")
                for edit in edits:
                    if len(str(edit.get("image_prompt") or "")) < 120:
                        raise ValueError("Image prompt too short")
                    if edit["scene_order"] <= 12:
                        _validate_video_prompt(edit.get("video_prompt"), edit["scene_order"])
                break
            except (ValueError, RuntimeError) as exc:
                if attempt == 1:
                    raise
                part_context = {**part_context, "previous_output": revised, "validation_rejection": str(exc)}
        for source, edit in zip(part, edits):
            for key in TEXT_KEYS:
                if key not in ("scene_text", "narration") and key in edit:
                    source[key] = edit[key]
    refresh_grids(structure)
    print(f"[{topic_id}] publishing metadata and full-package review", flush=True)
    meta_result = runner._stage(f"materials-{topic_id}-{VERSION}", "metadata", context,
        "Create publish_metadata with title, description (>=120 characters), tags (array), hashtags (array), "
        "and thumbnail_hook_texts (three distinct short phrases) in the story language. Keep the current title unless it is misleading "
        "or duplicates another queued title; correct that precisely without changing the actual story. "
        "Description must establish the actual protagonist/conflict, invite curiosity without spoiling the ending, "
        "and explicitly distinguish fictional/reconstructed stories from sourced real testimony. Do not call fictional work a true story. "
        "For finance/economy, distinguish a hypothetical example from verified dated claims; do not invent sources, prices, or investment advice. "
        "No production internals, repeated keywords, false promises, empty chapter timings, or unsupported hype. "
        "Return {'publish_metadata':{...},'title_change_reason':'...'}.")
    metadata = {**obj(row.get("publish_metadata")), **obj(meta_result.get("publish_metadata"))}
    package = {"source_hash": source_hash, "script": script, "structure": structure,
        "script_quality_report": report, "publish_metadata": metadata,
        "narrative_blueprint": report["repaired_narrative_blueprint"],
        "generated_title": metadata.get("title") or context["upload_title"],
        "title_change_reason": meta_result.get("title_change_reason")}
    package["character_reference_plan"] = structure.get("character_reference_plan") or []
    review_package = {k: v for k,v in package.items() if k not in ("source_hash", "structure", "script_quality_report")}
    review_package["structure"] = {"story_core": structure.get("story_core"), "scenes": [
        {k: s[k] for k in ("scene_order", "scene_number", "duration_seconds", *TEXT_KEYS) if k in s}
        for s in structure["scenes"]]}
    review = runner._stage(f"materials-{topic_id}-{VERSION}", "independent-material-review",
        {"category_contract": context["category_contract"], "category_name": category_name,
            "original_title": context["upload_title"], "character_assets": context["character_assets"],
            "asset_rule": context["asset_rule"], "supplemental_verified_research": context["supplemental_verified_research"],
            "candidate": review_package},
        "Independently review the FULL candidate, not author claims. Check title payoff, listening engagement without repetitive padding, "
        "every image/video prompt's correspondence with its scene, character DNA and chronology, metadata factual honesty and language. "
        "Use the category contract. Return {'material_quality_report':{'verdict':'pass' or 'revise','critical_issues':[],"
        "'checks':{'title_payoff':{'pass':true,'evidence':'specific scene references'},'engagement':{...},"
        "'prompt_alignment':{...},'character_continuity':{...},'metadata_accuracy':{...}}}}. "
        "Every evidence must cite concrete scenes/phrases. List unresolved issues even if prose is beautiful. Actual image pixels were not inspected.")
    package["material_quality_report"] = review.get("material_quality_report")
    dump(path, package)
    validate_package(package, row)
    return package


def patch_row(table, original, changes):
    url, headers = _headers()
    params = {"id": f"eq.{original['id']}"}
    if "updated_at" in original:
        params["updated_at"] = f"eq.{original['updated_at']}" if original["updated_at"] else "is.null"
    if "status" in original:
        params["status"] = f"eq.{original['status']}"
    if table == "topics_queue":
        params["progress_updated_at"] = f"eq.{original['progress_updated_at']}" if original.get("progress_updated_at") else "is.null"
        params["completed_at"] = "is.null"
    result = requests.patch(f"{url}/rest/v1/{table}", headers=headers, params=params, json=changes, timeout=60)
    result.raise_for_status()
    rows = result.json()
    if len(rows) != 1:
        raise RuntimeError(f"Concurrent change: {table}/{original['id']}")
    actual = fetch(table, id=f"eq.{original['id']}")[0]
    if any(actual.get(k) != v for k, v in changes.items()):
        raise RuntimeError(f"Read-back mismatch: {table}/{original['id']}")
    return actual


def register_character_descriptions(row, package):
    """Register text provenance; never mark a not-yet-generated portrait ready."""
    plan = package.get("character_reference_plan") or []
    if not plan:
        return 0
    existing = fetch("topic_character_assets", topic_queue_id=f"eq.{row['id']}")
    by_key = {c["character_key"]: c for c in existing}
    url, headers = _headers()
    saved_count = 0
    for character in plan:
        key = "material-review-" + str(character["character_key"])
        if key in by_key:
            if by_key[key].get("visual_dna_en") != character.get("visual_dna_en"):
                raise RuntimeError("Character registry changed; preserve newer DNA")
            continue
        record = {k: character[k] for k in ("name", "role", "gender", "age_group", "visual_dna_en", "wardrobe_en", "continuity_instruction", "image_prompt") if k in character}
        record.update({"topic_queue_id": row["id"], "character_key": key,
            "category": str(row.get("category_id") or ""), "script_style": row.get("assigned_script_style"),
            "story_style": row.get("assigned_script_style"), "image_style": row.get("assigned_image_style"),
            "prompt_en": character.get("image_prompt"), "source": "codex_material_review",
            "dna": {"visual_dna_en": character.get("visual_dna_en"), "wardrobe_en": character.get("wardrobe_en")},
            "usage_context": {"title": package["generated_title"], "reference_image_status": "pending", "review_version": VERSION}})
        response = requests.post(f"{url}/rest/v1/topic_character_assets", headers=headers, json=record, timeout=60)
        response.raise_for_status()
        stored = fetch("topic_character_assets", topic_queue_id=f"eq.{row['id']}", character_key=f"eq.{key}")
        if len(stored) != 1 or any(stored[0].get(k) != v for k, v in record.items()):
            raise RuntimeError("Character description failed read-back verification")
        saved_count += 1
    return saved_count


def approved_original_source(project, topic_id):
    path = OUT / "priority_user_scope.json"
    if not path.exists():
        return False
    scope = json.loads(path.read_text(encoding="utf-8"))
    approval = scope.get("original_script_approvals", {}).get(project.get("id"), {})
    return (approval.get("topic_id") == topic_id and approval.get("updated_at") == project.get("updated_at")
        and project.get("user_id") == scope.get("user_id"))


def publish(row, package):
    validate_package(package, row)
    project_only = row.get("_project_only_id")
    project_scope = {"id": f"eq.{project_only}"} if project_only else {"topic_queue_id": f"eq.{row['id']}"}
    current = row if project_only else fetch("topics_queue", id=f"eq.{row['id']}")[0]
    if not project_only and current != {k: v for k,v in row.items() if not k.startswith("_")}:
        raise RuntimeError("Topic changed after snapshot; re-review current version")
    all_projects = fetch("std_projects", **project_scope)
    if project_only and all_projects != [row["_project_snapshot"]]:
        raise RuntimeError("Project changed after snapshot; re-review current version")
    projects = [p for p in all_projects if p.get("id") not in row.get("_skip_project_ids", [])]
    if current.get("completed_at") or any(p.get("status") not in ACTIVE or p.get("submitted_at") for p in all_projects):
        raise RuntimeError("Submitted/completed project protected")
    for p in projects:
        if not project_only and user_script_changed(p, row.get("pregenerated_script")) and not approved_original_source(p, row["id"]):
            raise RuntimeError(f"User-edited script requires reconciliation: {p['id']}")
    # Build all changes and snapshot BEFORE any PATCH. Only whitelisted text is changed.
    operations = []
    revision = {"version": VERSION, "review": package["material_quality_report"], "requires_audio_regeneration": True}
    for p in projects:
        scene_rows = fetch("std_project_scenes", project_id=f"eq.{p['id']}", order="scene_number.asc")
        source = {**obj(p.get("source_payload")), "pregenerated_script": package["script"],
            "pregenerated_structure": merge_structure(obj(p.get("source_payload")).get("pregenerated_structure"), package["structure"]), "publish_metadata": package["publish_metadata"],
            "narrative_blueprint": package["narrative_blueprint"], "script_quality_report": package["script_quality_report"],
            "generated_title": package["generated_title"]}
        editor = {**copy.deepcopy(obj(p.get("project_payload"))), "script": package["script"], "original_worker_script": package["script"],
            "structure": merge_structure(obj(p.get("project_payload")).get("structure"), package["structure"]), "publish_metadata": package["publish_metadata"],
            "image_grid_prompts": package["structure"]["image_grid_prompts"]}
        # Let the existing UI rebuild subtitle text from the revised script while retaining source media.
        # Retain old timing/voice/media records as a recovery archive, not active stale text.
        if editor.get("subtitles"):
            editor["material_repair_previous_subtitles"] = editor["subtitles"]
            editor["subtitles"] = []
        for key in ("tts_url", "audio_url"):
            if editor.get(key):
                editor[f"material_repair_previous_{key}"] = editor[key]
                editor[key] = None
        if isinstance(editor.get("scenes"), list):
            for i, s in enumerate(editor["scenes"]):
                order = int(s.get("scene_number") or s.get("scene_order") or i+1)
                revised = package["structure"]["scenes"][order-1]
                s.update({k: revised[k] for k in TEXT_KEYS if k in revised})
        progress = {**obj(p.get("progress_payload")), "material_repair": revision,
            "script_changed_requires_audio_regeneration": True, "subtitles_completed": False, "subtitles_saved": False}
        for s in scene_rows:
            number = int(s["scene_number"])
            if not 1 <= number <= len(package["structure"]["scenes"]):
                raise RuntimeError("Project scene mapping out of range; reconcile before write")
            revised = package["structure"]["scenes"][number-1]
            changes = {k: revised[k] for k in ("scene_text", "scene_title", "image_prompt", "video_prompt") if k in revised}
            changes["metadata"] = {**obj(s.get("metadata")), **{k: revised[k] for k in TEXT_KEYS if k in revised}}
            operations.append(("std_project_scenes", s, changes))
        operations.append(("std_projects", p, {"source_payload": source, "project_payload": editor,
            "progress_payload": progress, "title": package["generated_title"]}))
    progress = {**obj(row.get("progress_payload")), "material_repair": revision,
        "publish_metadata": package["publish_metadata"]}
    changes = {"pregenerated_script": package["script"], "pregenerated_structure": package["structure"],
        "script_quality_report": package["script_quality_report"], "publish_metadata": package["publish_metadata"],
        "narrative_blueprint": package["narrative_blueprint"], "generated_title": package["generated_title"],
        "progress_payload": progress}
    if not project_only:
        operations.append(("topics_queue", current, changes))
    journal = OUT / "publish_journals" / f"{project_only or row['id']}_{time.time_ns()}.json"
    record = {"operations": [{"table": t, "before": b, "changes": c} for t,b,c in operations], "completed": []}
    dump(journal, record)
    for table, before, change in operations:
        live = fetch(table, id=f"eq.{before['id']}")[0]
        if live != before:
            raise RuntimeError(f"Concurrent change before write; inspect journal {journal}")
        # Recheck submission immediately before each write.
        if any(p.get("status") not in ACTIVE or p.get("submitted_at") for p in fetch("std_projects", **project_scope)):
            raise RuntimeError(f"Project submitted during update; inspect journal {journal}")
        saved = patch_row(table, before, change)
        record["completed"].append({"table": table, "id": before["id"], "updated_at": saved.get("updated_at")})
        dump(journal, record)
    return len(projects)


def project_variant(project):
    """Use current editor/subtitle content as the source of a project-only repair."""
    source = copy.deepcopy(obj(project.get("source_payload")))
    editor = obj(project.get("project_payload"))
    topic_id = project.get("topic_queue_id") or source.get("id")
    if not topic_id:
        raise ValueError("Project lacks an explicit source ID")
    structure = copy.deepcopy(obj(editor.get("structure") or source.get("pregenerated_structure")))
    scenes = structure.get("scenes") or []
    subtitles = editor.get("subtitles") or []
    if subtitles:
        groups = {}
        for subtitle in subtitles:
            number = subtitle.get("scene_number")
            if not isinstance(number, (int, float)) or not 1 <= int(number) <= len(scenes):
                raise ValueError("Edited subtitle has no reliable scene mapping")
            groups.setdefault(int(number), []).append(str(subtitle.get("text") or ""))
        if set(groups) != set(range(1, len(scenes)+1)):
            raise ValueError("Edited subtitle scene coverage incomplete")
        for i, scene in enumerate(scenes, 1):
            scene["scene_text"] = scene["narration"] = " ".join(groups[i]).strip()
        script = "\n\n".join(s["scene_text"] for s in scenes)
    else:
        script = editor.get("script") or source.get("pregenerated_script") or ""
    return {**source, "id": int(topic_id), "category_id": project.get("category_id") or source.get("category_id"),
        "generated_title": project.get("title"), "topic": project.get("title"), "status": "assigned", "completed_at": None,
        "pregenerated_script": script, "pregenerated_structure": structure,
        "publish_metadata": editor.get("publish_metadata") or source.get("publish_metadata"),
        "_project_only_id": project["id"], "_project_snapshot": project}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", help="Comma-separated IDs, otherwise all snapshot targets")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads((OUT / "source_snapshot.json").read_text(encoding="utf-8"))
    ids = {int(x) for x in args.ids.split(",")} if args.ids else None
    decisions_path = OUT / "pending_decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8")) if decisions_path.exists() else {}
    excluded = {int(k) for k, v in decisions.items() if str(v).startswith("Excluded by user")}
    rows = [t for t in snapshot["topics"] if t["id"] not in excluded and (not ids or t["id"] in ids)]
    if not ids:
        variants = []
        for project in snapshot["projects"] + snapshot["unlinked_active_projects"]:
            if (project.get("topic_queue_id") or obj(project.get("source_payload")).get("id")) in excluded:
                continue
            if approved_original_source(project, project.get("topic_queue_id")):
                continue
            topic = next((t for t in rows if t["id"] == project.get("topic_queue_id")), None)
            if not project.get("topic_queue_id") or user_script_changed(project, (topic or {}).get("pregenerated_script")):
                if topic:
                    topic.setdefault("_skip_project_ids", []).append(project["id"])
                try:
                    variants.append(project_variant(project))
                except ValueError as exc:
                    print(f"Project {project['id']} mapping requires reconciliation: {exc}", flush=True)
                    result_path = OUT / "run_results.json"
                    held = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
                    held[project["id"]] = {"status": "blocked", "error": str(exc), "topic_id": project.get("topic_queue_id")}
                    dump(result_path, held)
        rows = variants + rows
        snapshot["projects"] += snapshot["unlinked_active_projects"]
    active_ids = {p["topic_queue_id"] for p in snapshot["projects"]}
    rows.sort(key=lambda t: (t["id"] not in active_ids, -t["id"]))
    report_path = OUT / "run_results.json"
    results = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    for row in rows:
        key = str(row.get("_project_only_id") or row["id"])
        if results.get(key, {}).get("status") == "saved_and_verified":
            continue
        results[key] = {"status": "reviewing", "started_at_unix": time.time()}
        dump(report_path, results)
        write_report()
        try:
            if str(row.get("pregenerated_script_status") or "").startswith("codex_hidden"):
                raise ValueError("Intentionally hidden source: preserve its publication state")
            for attempt in range(2):
                try:
                    package = build(row, snapshot)
                    break
                except ValueError:
                    if attempt == 1:
                        raise
            count = publish(row, package) if args.publish else 0
            if args.publish and not row.get("_project_only_id"):
                register_character_descriptions(row, package)
                snapshot["characters"] = fetch("topic_character_assets")
            results[key] = {"status": "saved_and_verified" if args.publish else "candidate_approved", "projects": count}
        except Exception as exc:
            results[key] = {"status": "blocked", "error": str(exc)[-1600:]}
        dump(report_path, results)
        write_report()
        print(json.dumps({"id": row["id"], **results[key]}, ensure_ascii=False), flush=True)
        if results[key]["status"] == "blocked" and re.search(r"usage limit|rate.limit|insufficient_quota|insufficient credits|quota exceeded|401 Client Error", results[key].get("error", ""), re.I):
            break
    return int(any(v["status"] == "blocked" for v in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
