"""Publish the ten reviewed dialogue stills and freeze the scene-19+ mouth-work scope."""
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "worker")]
from dotenv import load_dotenv
from PIL import Image, ImageOps
from supabase import create_client
from worker.cowork_scene_assets import _download_gcs_bytes, _upload_gcs_file

load_dotenv(ROOT / ".env", override=False)
PROJECT_ID = "6b46f709-b4bf-4ccd-ac12-9c8c3981e249"
SCENES = [25, 29, 31, 32, 33, 34, 36, 39, 40, 41]
OUT = ROOT / "output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package"
SRC = OUT / "ae-mouth-sources"
NORMALIZED = OUT / "ae-mouth-sources-1920x1080"
NORMALIZED.mkdir(exist_ok=True)
DB = create_client(os.environ["NEXT_PUBLIC_SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def main():
    project = DB.table("std_projects").select("*").eq("id", PROJECT_ID).single().execute().data
    payload = project["project_payload"]
    for row in payload.get("subtitles", []):
        number = int(row.get("scene_number", row.get("scene", row.get("sceneNumber", -1))))
        if number == 31 and row.get("dialogue_kind") == "dialogue" and row.get("text") == "これからはちゃんとする":
            row["dialogue_speaker"] = "高橋健太"
    payload["mouth_work_policy"] = {"enabled": True, "start_scene": 19, "max_dialogue_scenes": 10}
    payload["ae_mouth"] = {**(payload.get("ae_mouth") or {}), "enabled": True}
    DB.table("std_projects").update({"project_payload": payload}).eq("id", PROJECT_ID).execute()

    existing = DB.table("std_project_assets").select("*").eq("project_id", PROJECT_ID).execute().data or []
    published = []
    for number in SCENES:
        source = SRC / f"scene-{number:03d}-dialogue.png"
        target = NORMALIZED / f"scene-{number:03d}-dialogue.png"
        with Image.open(source) as image:
            image = ImageOps.fit(image.convert("RGB"), (1920, 1080), method=Image.Resampling.LANCZOS)
            image.save(target, "PNG", optimize=True)
        data = target.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        object_path = f"std/{PROJECT_ID}/ae-mouth/sources/scene-{number:03d}-{digest[:20]}.png"
        bucket, gcs_path, url = _upload_gcs_file(target, object_path, "image/png")
        remote = _download_gcs_bytes(bucket, gcs_path)
        if hashlib.sha256(remote).hexdigest() != digest:
            raise RuntimeError(f"scene {number} upload verification failed")
        old = next((a for a in existing if a.get("asset_type") == "image" and int(a.get("scene_number") or -1) == number and (a.get("metadata") or {}).get("kind") == "ae_dialogue_source" and (a.get("metadata") or {}).get("sha256") == digest), None)
        metadata = {"kind": "ae_dialogue_source", "source": "codex_builtin_image_gen", "visual_review": "passed", "visual_reviewed_by": "codex", "visual_reviewed_at": datetime.now(timezone.utc).isoformat(), "storage_provider": "gcs", "gcs_bucket": bucket, "gcs_path": gcs_path, "storage_bucket": bucket, "storage_path": gcs_path, "sha256": digest, "width": 1920, "height": 1080, "mouth_default": "closed", "selection_basis": "first_10_dialogue_scenes_at_or_after_19"}
        if old:
            asset = old
        else:
            asset = DB.table("std_project_assets").insert({"project_id": PROJECT_ID, "scene_number": number, "asset_type": "image", "status": "uploaded", "file_name": target.name, "mime_type": "image/png", "file_size": len(data), "metadata": metadata}).execute().data[0]
        published.append({"scene_number": number, "asset_id": asset["id"], "sha256": digest, "gcs_bucket": bucket, "gcs_path": gcs_path, "local_file": str(target), "verified": True})

    if not any((a.get("metadata") or {}).get("kind") == "mouth_work_selection" for a in existing):
        DB.table("std_project_assets").insert({"project_id": PROJECT_ID, "asset_type": "other", "status": "uploaded", "file_name": "mouth-work-selection.json", "mime_type": "application/json", "metadata": {"kind": "mouth_work_selection", "state": "frozen", "scene_numbers": SCENES, "start_scene": 19, "max_dialogue_scenes": 10, "selection_basis": "first_10_dialogue_scenes_at_or_after_19", "selected_by": "codex", "selected_at": datetime.now(timezone.utc).isoformat()}}).execute()
    manifest = {"project_id": PROJECT_ID, "scene_numbers": SCENES, "selection_basis": "first_10_dialogue_scenes_at_or_after_19", "assets": published}
    (OUT / "ae-mouth-source-upload-receipt.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project_id": PROJECT_ID, "scenes": SCENES, "uploaded_and_verified": len(published)}))


if __name__ == "__main__":
    main()
