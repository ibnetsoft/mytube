"""Queue current-standard regeneration for previously audited visible scripts.

This tool never overwrites a published row itself.  It submits the existing
topic/title/scene structure to Hermes; the worker replaces Supabase fields only
after the regenerated script and its media prompts pass the current gates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "worker")]


def load_env() -> None:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def as_object(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def target_ids() -> list[int]:
    audit = json.loads((ROOT / "worknote" / "visible_script_reaudit.json").read_text(encoding="utf-8"))
    return [
        int(item["id"])
        for item in audit.get("results", [])
        if item.get("disposition") in {"재생성", "부분 보완"} and item.get("id") is not None
    ]


def duration_seconds(row: dict, structure: dict) -> int:
    configured = row.get("target_duration_seconds") or row.get("duration_seconds")
    try:
        if configured and float(configured) > 0:
            return round(float(configured))
    except (TypeError, ValueError):
        pass
    scene_total = sum(
        float(scene.get("duration_seconds") or 0)
        for scene in structure.get("scenes") or []
        if isinstance(scene, dict)
    )
    return round(scene_total) if scene_total > 0 else max(60, len(structure.get("scenes") or []) * 10)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="submit jobs; default is dry-run")
    args = parser.parse_args()
    load_env()

    base_url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/") + "/rest/v1/topics_queue"
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    audit = json.loads((ROOT / "worknote" / "visible_script_reaudit.json").read_text(encoding="utf-8"))
    audit_by_id = {int(item["id"]): item for item in audit.get("results", []) if item.get("id") is not None}

    import job_store

    existing = {
        str((job.get("payload") or {}).get("topic_queue_id"))
        for job in job_store.list_jobs(limit=1000)
        if job.get("job_type") == "script_generate"
        and job.get("source") == "visible-script-regeneration"
        and job.get("status") in {job_store.QUEUED, job_store.CLAIMED, job_store.PREPARING, job_store.RENDERING, job_store.UPLOADING}
    }

    queued = []
    skipped = []
    for row_id in target_ids():
        response = requests.get(
            base_url,
            headers=headers,
            params={"select": "*", "id": f"eq.{row_id}"},
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if len(rows) != 1:
            skipped.append({"id": row_id, "reason": "row not found"})
            continue
        row = rows[0]
        structure = as_object(row.get("pregenerated_structure"))
        scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
        if row.get("status") != "pending" or not scenes:
            skipped.append({"id": row_id, "reason": "not pending or structure missing"})
            continue
        if str(row_id) in existing:
            skipped.append({"id": row_id, "reason": "regeneration already queued"})
            continue

        title = str(row.get("generated_title") or row.get("topic") or "").strip()
        if not title:
            skipped.append({"id": row_id, "reason": "title missing"})
            continue
        audit_item = audit_by_id[row_id]
        issues = audit_item.get("critical_issues") or audit_item.get("revision_notes") or []
        payload = {
            "topic_queue_id": str(row_id),
            "category": row.get("category_name") or row.get("category") or "",
            "category_name": row.get("category_name") or row.get("category") or "",
            "category_id": row.get("category_id"),
            "topic": str(row.get("topic") or title),
            "structure": structure,
            "target_duration_seconds": duration_seconds(row, structure),
            "script_style": row.get("script_style") or row.get("assigned_script_style") or "default",
            "image_style": row.get("image_style") or row.get("assigned_image_style") or "realistic",
            "image_style_selection": as_object(row.get("image_style_selection")),
            "language": row.get("language") or "ko",
            "narration_mode": row.get("narration_mode") or "dramatic_single",
            "narration_pace": row.get("narration_pace") or "normal",
            "tts_speed": row.get("tts_speed") or 1.0,
            "upload_title": title,
            "title_generation": as_object(row.get("title_generation")),
            "learning_profile": as_object(row.get("learning_profile")),
            "repair_instruction": "Current-standard QA findings to fix while preserving this exact title and scene structure:\n- " + "\n- ".join(str(issue) for issue in issues[:5]),
            "defer_ready_until_quality_gate": True,
            "existing_result_replacement": True,
        }
        item = {"id": row_id, "title": title, "scene_count": len(scenes), "payload": payload}
        if args.execute:
            item["job_id"] = job_store.submit_job(
                job_type="script_generate",
                payload=payload,
                priority=90,
                source="visible-script-regeneration",
                max_retries=0,
            )
        queued.append(item)

    summary = [
        {key: item[key] for key in ("id", "title", "scene_count", "job_id") if key in item}
        for item in queued
    ]
    print(json.dumps({"execute": args.execute, "queued": summary, "skipped": skipped}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
