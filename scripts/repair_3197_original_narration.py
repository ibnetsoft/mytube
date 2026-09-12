"""Apply the explicitly chosen original narration, leaving visual prompts unchanged."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import repair_active_materials as repair


def main():
    row = repair.fetch("topics_queue", id="eq.3197")[0]
    project = repair.fetch("std_projects", id="eq.10b3d223-1457-415a-ba40-7b947c6c1b3d")[0]
    if not repair.approved_original_source(project, 3197):
        raise RuntimeError("Original-source approval no longer matches this project")
    if repair.obj(project["project_payload"]).get("original_worker_script") != row["pregenerated_script"]:
        raise RuntimeError("Original scripts diverged; preserve current data")
    sections, report = repair._repair_with_codex(row, "옛날이야기", repair.OUT, "")
    structure = copy.deepcopy(row["pregenerated_structure"])
    structure["story_core"] = report["repaired_story_core"]
    structure["narrative_blueprint"] = report["repaired_narrative_blueprint"]
    for scene, section in zip(structure["scenes"], sections):
        scene["scene_text"] = scene["narration"] = scene["script_excerpt"] = section["text"].strip()
    package = {"repair_scope": "narration_only", "script": "\n\n".join(s["text"].strip() for s in sections),
        "structure": structure, "script_quality_report": report, "publish_metadata": row["publish_metadata"],
        "narrative_blueprint": report["repaired_narrative_blueprint"], "generated_title": row["generated_title"],
        "material_quality_report": {"scope": "narration_only", "visual_prompts": "unchanged_not_revalidated"}}
    repair.dump(repair.OUT / "candidates" / "3197_original_narration.json", package)
    count = repair.publish(row, package)
    repair.dump(repair.OUT / "3197_original_narration_result.json", {
        "status": "narration_saved_and_verified", "projects": count, "scene_count": len(sections),
        "score": report["score"], "visual_prompts": "unchanged", "audio_regeneration_required": True})
    print(json.dumps({"status": "narration_saved_and_verified", "projects": count, "score": report["score"]}))


if __name__ == "__main__":
    main()
