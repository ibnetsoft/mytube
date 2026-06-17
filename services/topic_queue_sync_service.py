import datetime
from typing import Any, Dict, List, Optional

import database as db
from services.web_admin_client import web_admin_client


STEP_LABELS = {
    "topic": "주제",
    "plan": "기획",
    "script": "대본",
    "intro": "인트로",
    "image": "이미지",
    "template": "템플릿",
    "tts": "TTS",
    "subtitle": "자막",
    "video": "영상",
    "upload": "업로드",
}

STEP_ORDER = [
    "topic",
    "plan",
    "script",
    "intro",
    "image",
    "template",
    "tts",
    "subtitle",
    "video",
    "upload",
]


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_project_progress_snapshot(project_id: int) -> Dict[str, Any]:
    project = db.get_project(project_id) or {}
    settings = db.get_project_settings(project_id) or {}
    script_structure = db.get_script_structure(project_id)
    script = db.get_script(project_id)
    image_prompts = _safe_list(db.get_image_prompts(project_id) or [])
    tts_data = db.get_tts(project_id)

    steps = {
        "topic": bool(project.get("topic")),
        "plan": bool(script_structure),
        "script": bool((script or {}).get("full_script")),
        "intro": bool(settings.get("intro_video_path") or settings.get("background_video_url")),
        "image": len(image_prompts) > 0,
        "template": bool(
            settings.get("thumbnail_url")
            or settings.get("thumbnail_path")
            or db.get_thumbnails(project_id)
        ),
        "tts": bool(tts_data),
        "subtitle": bool(settings.get("subtitle_path") or (tts_data and settings.get("subtitle_style_enum"))),
        "video": bool(settings.get("video_path") or settings.get("external_video_path")),
        "upload": bool(settings.get("is_uploaded")),
    }

    completed_step_keys = [key for key in STEP_ORDER if steps.get(key)]
    completed_steps = [STEP_LABELS[key] for key in completed_step_keys]
    current_step_key = next((key for key in STEP_ORDER if not steps.get(key)), None)

    return {
        "project_id": project_id,
        "project_name": project.get("name") or "",
        "project_status": project.get("status") or "",
        "completed_step_keys": completed_step_keys,
        "completed_steps": completed_steps,
        "current_step_key": current_step_key,
        "current_step": STEP_LABELS.get(current_step_key, "완료"),
        "completed_count": len(completed_steps),
        "steps": steps,
        "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def sync_topic_progress(project_id: int, topic_queue_id: Optional[int] = None) -> bool:
    if not project_id:
        return False

    settings = db.get_project_settings(project_id) or {}
    topic_queue_id = topic_queue_id or settings.get("topic_queue_id")
    if not topic_queue_id:
        return False

    snapshot = build_project_progress_snapshot(project_id)
    response = web_admin_client.supabase_patch(
        "topics_queue",
        {
            "local_project_id": project_id,
            "progress_payload": snapshot,
            "progress_updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        params={"id": f"eq.{topic_queue_id}"},
        timeout=8,
    )
    return bool(response is not None and response.status_code in (200, 204))
