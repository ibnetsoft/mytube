from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Body
from typing import List, Optional
import json
import database as db
from app.models.autopilot import AutopilotPresetSave, AutoPilotStartRequest
from services.autopilot_service import autopilot_service

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])

@router.get("/presets")
async def get_autopilot_presets_api():
    presets = db.get_autopilot_presets()
    for p in presets:
        try:
            p['settings'] = json.loads(p['settings_json'])
        except Exception:
            p['settings'] = {}
    return {"status": "ok", "presets": presets}

@router.post("/presets")
async def save_autopilot_preset_api(req: AutopilotPresetSave):
    try:
        db.save_autopilot_preset(req.name, req.settings)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.delete("/presets/{preset_id}")
async def delete_autopilot_preset_api(preset_id: int):
    try:
        db.delete_autopilot_preset(preset_id)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/start")
async def start_autopilot_api(
    req: AutoPilotStartRequest,
    background_tasks: BackgroundTasks
):
    """오토파일럿 시작 (API)"""
    # 1. Preset Loading — subtitle_settings 외 모든 필드 채움
    if req.preset_id:
        presets = db.get_autopilot_presets()
        preset = next((p for p in presets if p['id'] == req.preset_id), None)
        if preset:
            try:
                p_settings = json.loads(preset['settings_json'])
                # 요청에서 명시적으로 보내지 않은 필드만 프리셋 값으로 채움
                field_map = {
                    "subtitle_settings": "subtitle_settings",
                    "image_style":       "image_style",
                    "thumbnail_style":   "thumbnail_style",
                    "script_style":      "script_style",
                    "voice_provider":    "voice_provider",
                    "voice_id":          "voice_id",
                    "motion_method":     "motion_method",
                    "video_scene_count": "video_scene_count",
                    "all_video":         "all_video",
                    "duration_seconds":  "duration_seconds",
                    "duration_minutes":  "duration_minutes",
                    "use_character_analysis": "use_character_analysis",
                    "upload_privacy":    "upload_privacy",
                    "youtube_channel_id":"youtube_channel_id",
                }
                for req_field, preset_key in field_map.items():
                    if preset_key in p_settings:
                        current = getattr(req, req_field, None)
                        # None 이거나 기본값(빈문자열/0/False)이면 프리셋 값으로 덮어쓰기
                        if current is None or current == "" or current == 0 or current is False:
                            try:
                                setattr(req, req_field, p_settings[preset_key])
                            except Exception:
                                pass
            except Exception:
                pass

    # 2. Topic Resolve
    topic = req.topic or req.keyword
    if not topic:
         return {"status": "error", "error": "Topic (or keyword) is required"}

    # 3. Create Project & Get ID (Atomic)
    pid = db.create_project(name=f"[Auto] {topic}", topic=topic, app_mode=req.mode)

    # 4. Save Initial Settings to DB
    db.update_project_setting(pid, "upload_privacy", req.upload_privacy)
    if req.upload_schedule_at:
        db.update_project_setting(pid, "upload_schedule_at", req.upload_schedule_at)
    if req.youtube_channel_id:
        db.update_project_setting(pid, "youtube_channel_id", req.youtube_channel_id)
    
    db.update_project_setting(pid, "creation_mode", req.creation_mode)
    if req.product_url:
        db.update_project_setting(pid, "product_url", req.product_url)
    
    # [NEW] Save other core settings for Batch Mode compatibility
    db.update_project_setting(pid, "image_style", req.image_style)
    db.update_project_setting(pid, "thumbnail_style", req.thumbnail_style)
    db.update_project_setting(pid, "video_scene_count", req.video_scene_count)
    db.update_project_setting(pid, "all_video", 1 if req.all_video else 0)
    db.update_project_setting(pid, "motion_method", req.motion_method)
    db.update_project_setting(pid, "script_style", req.script_style)
    db.update_project_setting(pid, "voice_provider", req.voice_provider)
    db.update_project_setting(pid, "voice_name", req.voice_id)
    db.update_project_setting(pid, "use_character_analysis", "1" if req.use_character_analysis else "0")
    if req.duration_seconds:
        db.update_project_setting(pid, "duration_seconds", req.duration_seconds)


    if req.is_queued:
        db.update_project(pid, status="queued")
        return {
            "status": "ok",
            "project_id": pid,
            "message": f"'{topic}' 작업이 대기열에 추가되었습니다. 큐에서 순차적으로 제작됩니다."
        }

    # 4. Trigger Background Task
    background_tasks.add_task(
        autopilot_service.run_workflow,
        keyword=topic,
        project_id=pid,
        config_dict=req.dict()
    )

    return {
        "status": "ok",
        "project_id": pid,
        "message": f"오토파일럿 '{topic}' 작업이 백그라운드에서 시작되었습니다."
    }

