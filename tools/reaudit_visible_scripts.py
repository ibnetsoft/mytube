"""Read-only re-audit for scripts currently eligible for the user web UI."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))


def _load_env() -> None:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _object(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _is_user_visible(row: dict) -> bool:
    payload = _object(row.get("progress_payload"))
    metadata = _object(row.get("publish_metadata") or payload.get("publish_metadata"))
    structure = _object(row.get("pregenerated_structure"))
    scenes = structure.get("scenes") if isinstance(structure, dict) else []
    if not (
        row.get("status") == "pending"
        and row.get("generated_title")
        and row.get("category_id")
        and row.get("pregenerated_structure_status") == "ready"
        and row.get("pregenerated_script_status") == "ready"
        and structure.get("media_prompt_status") == "ready"
        and structure.get("image_grid_prompt_status") == "ready"
        and metadata.get("description")
        and scenes
    ):
        return False
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or scene.get("media_prompt_status") != "ready":
            return False
        order = int(scene.get("scene_order") or scene.get("scene_number") or index)
        requires_video = scene.get("video_prompt_required") is not False and order <= 4
        if requires_video and not any(
            scene.get(key)
            for key in (
                "video_prompt", "motion_desc", "flow_prompt", "camera_motion",
                "motion_plan", "visual_direction", "scene_situation", "script_excerpt",
            )
        ):
            return False
    return True


async def main() -> None:
    _load_env()
    import hermes_worker
    from config import config
    from services import ai_router
    from services.ai_router import ProviderCreditExhaustedError

    base_url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/") + "/rest/v1/topics_queue"
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    response = requests.get(
        base_url,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"select": "*", "pregenerated_script": "not.is.null", "order": "created_at.desc", "limit": "50"},
        timeout=30,
    )
    response.raise_for_status()
    rows = [row for row in response.json() if _is_user_visible(row)]
    destination = ROOT / "worknote" / "visible_script_reaudit.json"
    results = []
    semaphore = asyncio.Semaphore(3)
    credit_exhausted = asyncio.Event()

    def write_snapshot() -> None:
        destination.write_text(
            json.dumps(
                {"scope": "user-web-visible", "total": len(rows), "completed": len(results), "results": results},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    async def audit_one(row: dict) -> None:
        if credit_exhausted.is_set():
            return
        raw_script = row.get("pregenerated_script") or ""
        script = (
            raw_script.get("script") or raw_script.get("full_script") or ""
            if isinstance(raw_script, dict)
            else str(raw_script)
        )
        async with semaphore:
            if credit_exhausted.is_set():
                return
            try:
                report = await hermes_worker._evaluate_script_quality(
                    ai_router, config.SCRIPT_GENERATION_MODEL,
                    str(row.get("topic") or ""), str(row.get("generated_title") or row.get("topic") or ""),
                    _object(row.get("narrative_blueprint")), _object(row.get("pregenerated_structure")),
                    script, str(row.get("language") or "ko"),
                )
                score = int(report.get("score") or 0)
                verdict = str(report.get("verdict") or "revise").lower()
                result = {
                    "id": row.get("id"), "title": row.get("generated_title") or row.get("topic"),
                    "category_id": row.get("category_id"), "score": score, "verdict": verdict,
                    "disposition": "유지" if verdict == "pass" and score >= 78 and not report.get("critical_issues") else ("부분 보완" if score >= 60 else "재생성"),
                    "critical_issues": (report.get("critical_issues") or [])[:5],
                    "revision_notes": (report.get("revision_notes") or [])[:5],
                }
            except ProviderCreditExhaustedError as exc:
                credit_exhausted.set()
                result = {"id": row.get("id"), "status": "credit_exhausted", "error": str(exc)}
            except Exception as exc:
                result = {"id": row.get("id"), "status": "qa_error", "error": str(exc)[:500]}
            results.append(result)
            write_snapshot()

    await asyncio.gather(*(audit_one(row) for row in rows))


if __name__ == "__main__":
    asyncio.run(main())
