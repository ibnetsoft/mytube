from fastapi import APIRouter, HTTPException, Body, Request
from typing import List, Optional
import database as db
from app.models.project import ProjectCreate, ProjectUpdate, ProjectSettingUpdate, ProjectSettingsSave
from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    ids: List[int]

router = APIRouter(prefix="/api", tags=["Projects"])

@router.post("/projects/bulk-delete")
async def bulk_delete_projects(req: BulkDeleteRequest):
    try:
        count = 0
        for pid in req.ids:
            try:
                db.delete_project(pid)
                count += 1
            except: pass
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/projects")
async def get_projects():
    try:
        projects = db.get_projects_with_status()
        return {"status": "success", "projects": projects}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/projects")
async def create_project(request: Request):
    try:
        # Pydantic 모델 대신 원본 JSON을 직접 읽어서 매핑 오류 원천 차단
        data = await request.json()
        
        name = data.get("name", "Untitled")
        topic = data.get("topic")
        
        # 명시적으로 필드 추출
        target_lang = data.get("target_language") or data.get("language") or "ko"
        app_mode = data.get("app_mode") or data.get("mode") or "longform"
        
        # [ROBUST] 만약 app_mode에 언어 코드가 들어왔다면 보정 (매핑 오류 대비)
        if app_mode in ['ko', 'en', 'ja', 'vi', 'es']:
            # 언어가 모드로 잘못 들어온 경우:
            # 1. target_lang이 'ko'라면 app_mode가 진짜 데이터였을 수 있음
            # 2. 하지만 필드명이 'app_mode'인데 'ko'가 들어왔다면 보통 뒤바뀐 것
            real_mode = data.get("target_language") # target_language 필드에 shorts가 있었을 가능성
            if real_mode in ['shorts', 'longform']:
                app_mode = real_mode
                target_lang = data.get("app_mode") # 원래 언어
            else:
                app_mode = "longform" # 기본값 복구
        
        project_id = db.create_project(
            name=name, 
            topic=topic, 
            app_mode=app_mode, 
            language=target_lang
        )
        return {"status": "success", "project_id": project_id}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project

@router.put("/projects/{project_id}")
async def update_project(project_id: int, data: ProjectUpdate):
    try:
        db.update_project(project_id, data.name, data.topic, data.status)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    try:
        db.delete_project(project_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/project-settings/{project_id}")
async def save_project_settings(project_id: int, settings: ProjectSettingsSave):
    try:
        db.save_project_settings(project_id, settings.dict(exclude_unset=True))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.put("/project-settings/{project_id}")
async def update_project_setting(project_id: int, data: ProjectSettingUpdate):
    try:
        db.update_project_setting(project_id, data.key, data.value)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

# [NEW] GET Method for settings
@router.get("/project-settings/{project_id}")
async def get_project_settings_api(project_id: int):
    settings = db.get_project_settings(project_id)
    if not settings:
        raise HTTPException(404, "Settings not found")
    return settings

# [NEW] Motion/Video Asset Studio APIs

class MotionDescUpdate(BaseModel):
    scene_number: int
    motion_desc: str

@router.post("/projects/{project_id}/update-motion")
async def update_motion_desc(project_id: int, data: MotionDescUpdate):
    """씬별 모션 프롬프트 업데이트"""
    try:
        # 1. Update project_settings (for fast lookup)
        db.update_project_setting(project_id, f"scene_{data.scene_number}_motion_desc", data.motion_desc)
        
        # 2. Update image_prompts table (for persistence)
        # We need a db function for this specific update or use generic execute
        conn = db.get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE image_prompts SET motion_desc = ? WHERE project_id = ? AND scene_number = ?", 
            (data.motion_desc, project_id, data.scene_number)
        )
        conn.commit()
        conn.close()
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

class SingleVideoGenRequest(BaseModel):
    scene_number: int
    engine: str = "wan"  # wan | akool | seedance | image
    motion_desc: Optional[str] = None  # Optional motion description override
    resolution: Optional[str] = "720p"  # For Seedance: 480p / 720p / 1080p
    duration: Optional[int] = 5         # For Seedance: 5 or 10 seconds

@router.post("/projects/{project_id}/generate-video")
async def generate_single_video(project_id: int, req: SingleVideoGenRequest):
    """단일 씬 비디오 생성 (Wan/Akool)"""
    try:
        from services.replicate_service import replicate_service
        from services.akool_service import akool_service
        from services.video_service import video_service
        from config import config
        import os
        from datetime import datetime
        
        # 1. Get Image Path
        prompts = db.get_image_prompts(project_id)
        target_p = next((p for p in prompts if p['scene_number'] == req.scene_number), None)
        if not target_p: raise HTTPException(404, "Scene not found")
        
        image_url = target_p['image_url']
        if not image_url: raise HTTPException(400, "No image generated for this scene")
        
        image_abs_path = os.path.join(config.OUTPUT_DIR, image_url.replace("/output/", ""))
        if not os.path.exists(image_abs_path): raise HTTPException(404, "Image file missing")
        
        now = datetime.now()
        video_url = ""
        
        # 2. Engine Routing
        if req.engine == "wan":
            # [Wan] Motion Generation
            # Prioritize: Req > DB(motion_desc) > DB(prompt_en/visual_desc)
            base_prompt = target_p.get('prompt_en') or target_p.get('visual_desc') or "Cinematic motion"
            motion_part = req.motion_desc or target_p.get('motion_desc') or ""
            
            final_prompt = f"{base_prompt}, {motion_part}" if motion_part else f"{base_prompt}, smooth motion"
            
            # [FIX] Check if full original image exists (prevents character cropping in pan effects)
            p_settings = db.get_project_settings(project_id) or {}
            wan_asset_filename = p_settings.get(f"scene_{req.scene_number}_wan_image", "")
            if wan_asset_filename:
                wan_asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image")
                wan_candidate = os.path.join(wan_asset_dir, wan_asset_filename)
                if os.path.exists(wan_candidate):
                    wan_source_path = wan_candidate
                    print(f"  🎯 [Studio] Using FULL original image for Wan: {wan_asset_filename}")
                else:
                    wan_source_path = image_abs_path
            else:
                wan_source_path = image_abs_path
            
            print(f"🎬 [Studio] Generating Wan Video for Scene {req.scene_number}... Prompt: {final_prompt[:80]}...")
            video_data = await replicate_service.generate_video_from_image(
                wan_source_path,
                prompt=final_prompt,
                duration=5.0, # Fixed for Wan
                method="standard" 
            )
            
            if video_data:
                filename = f"vid_wan_{project_id}_{req.scene_number}_{now.strftime('%H%M%S')}.mp4"
                out = os.path.join(config.OUTPUT_DIR, filename)
                with open(out, 'wb') as f: f.write(video_data)
                video_url = f"/output/{filename}"

        elif req.engine == "seedance":
            # [Seedance 1.5 Pro] Akool v4 API - 가장 저렴한 선택
            # 모델: seedance-1-0-lite-i2v-250428
            base_prompt = target_p.get('prompt_en') or target_p.get('visual_desc') or "Cinematic video"
            motion_part = req.motion_desc or target_p.get('motion_desc') or ""
            final_prompt = f"{base_prompt}, {motion_part}" if motion_part else f"{base_prompt}, smooth cinematic motion"

            print(f"🌱 [Studio] Generating Seedance Video for Scene {req.scene_number}... Prompt: {final_prompt[:80]}...")
            video_data = await akool_service.generate_seedance_video(
                local_image_path=image_abs_path,
                prompt=final_prompt,
                duration=req.duration or 5,
                resolution=req.resolution or "720p",
                model_value="seedance-1-0-lite-i2v-250428"
            )

            if video_data:
                filename = f"vid_seedance_{project_id}_{req.scene_number}_{now.strftime('%H%M%S')}.mp4"
                out = os.path.join(config.OUTPUT_DIR, filename)
                with open(out, 'wb') as f: f.write(video_data)
                video_url = f"/output/{filename}"

        elif req.engine == "akool":
            # [Akool] LipSync
            # Need Audio!
            # We assume TTS is already generated or we can try to find it.
            # Ideally, user should ensure TTS exists. Or we can generate TTS on fly?
            # For now, let's look for existing tts_audio
            conn = db.get_db()
            row = conn.execute("SELECT audio_path FROM tts_audio WHERE project_id=? AND voice_id IS NOT NULL ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
            # Wait, tts_audio table structure? It stores by project... 
            # Actually, autopilot uses file naming or checks a map.
            # Let's check 'scene_{N}_audio' setting or generic path pattern
            
            # Try specific scene audio from settings first
            s_set = db.get_project_settings(project_id)
            audio_path = None
            
            # Pattern check: output/PROJ/tts_scene_N.mp3 ??
            # AutoPilot logic: temp_audios list... 
            # Let's try to find matching TTS file in output dir
            from glob import glob
            candidates = glob(os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio", f"*{req.scene_number:03d}*.mp3"))
            if not candidates:
                 # Try root output
                 candidates = glob(os.path.join(config.OUTPUT_DIR, f"tts_{project_id}_{req.scene_number}_*.mp3"))
            
            if candidates:
                audio_path = candidates[0]
            else:
                 raise HTTPException(400, "No TTS audio found for this scene. Please generate audio first.")

            print(f"👄 [Studio] Generating Akool LipSync for Scene {req.scene_number}...")
            video_bytes = await akool_service.generate_talking_avatar(image_abs_path, audio_path)
            
            if video_bytes:
                filename = f"vid_akool_{project_id}_{req.scene_number}_{now.strftime('%H%M%S')}.mp4"
                out = os.path.join(config.OUTPUT_DIR, filename)
                with open(out, 'wb') as f: f.write(video_bytes)
                video_url = f"/output/{filename}"

        elif req.engine == "image":
            # [2D Motion] Simple Pan/Zoom
            # Check Webtoon Settings
            s_set = db.get_project_settings(project_id) or {}
            # [NEW] Check Global Webtoon Settings
            w_auto = db.get_global_setting("webtoon_auto_split", True, value_type="bool")
            w_pan = db.get_global_setting("webtoon_smart_pan", True, value_type="bool")
            w_zoom = db.get_global_setting("webtoon_convert_zoom", True, value_type="bool")
            
            # Default "zoom_in" if not specified
            motion_part = req.motion_desc.strip().lower().replace(" ", "_") if req.motion_desc else "zoom_in"
            # Map description to supported motion if possible, or default
            if motion_part not in ["pan_down", "pan_up", "zoom_in", "zoom_out", "pan_left", "pan_right", "static"]:
                motion_part = "zoom_in"

            print(f"🖼️ [Studio] Generating 2D Motion Video for Scene {req.scene_number} ({motion_part})...")
            
            video_bytes = await video_service.create_image_motion_video(
                image_path=image_abs_path,
                duration=5.0, # Standard duration
                motion_type=motion_part,
                width=1080, height=1920, # Default vertical
                auto_split=w_auto,
                smart_pan=w_pan,
                convert_zoom=w_zoom
            )

            if video_bytes:
                filename = f"vid_motion_{project_id}_{req.scene_number}_{now.strftime('%H%M%S')}.mp4"
                out = os.path.join(config.OUTPUT_DIR, filename)
                with open(out, 'wb') as f: f.write(video_bytes)
                video_url = f"/output/{filename}"

                
        # 3. Save Result
        if video_url:
            db.update_image_prompt_video_url(project_id, req.scene_number, video_url)
            return {"status": "success", "video_url": video_url}
        else:
            raise HTTPException(500, "Video generation returned no data")

    except Exception as e:
        print(f"Generate Single Video Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))
