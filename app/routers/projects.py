from fastapi import APIRouter, HTTPException, Body, Request, UploadFile, File
from typing import List, Optional
import database as db
from app.models.project import ProjectCreate, ProjectUpdate, ProjectSettingUpdate, ProjectSettingsSave
from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    ids: List[int]

class ProjectCopyMoveRequest(BaseModel):
    project_id: int
    target_mode: str
    action: str  # 'copy' | 'move'

class BulkCopyMoveRequest(BaseModel):
    ids: List[int]
    target_mode: str
    action: str  # 'copy' | 'move'

router = APIRouter(prefix="/api", tags=["Projects"])

@router.post("/projects/bulk-delete")
async def bulk_delete_projects(req: BulkDeleteRequest):
    try:
        count = 0
        for pid in req.ids:
            try:
                db.delete_project(pid)
                count += 1
            except Exception: pass
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/projects/bulk-copy-move")
async def bulk_copy_move(req: BulkCopyMoveRequest):
    try:
        count = 0
        for pid in req.ids:
            try:
                if req.action == 'copy':
                    db.copy_project(pid, req.target_mode)
                else:
                    db.move_project(pid, req.target_mode)
                count += 1
            except Exception as inner_e:
                print(f"Error in bulk {req.action}: {inner_e}")
        return {"status": "success", "processed_count": count}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/projects/current")
async def get_current_project():
    """가장 최근에 작업한 프로젝트 정보 반환 (연결 폴백용)"""
    recent = db.get_recent_projects(limit=1)
    if recent:
        return recent[0]
    return {"id": None, "name": "No Project"}

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
        
        # ── 영상용 프롬프트 빌더 ──────────────────────────────────────────
        # 영상 AI(Seedance/Wan)는 정적 이미지 묘사보다 모션/액션 설명을 우선함.
        # motion_desc(짧고 액션 중심) → 앞에, prompt_en 요약(시각 컨텍스트) → 뒤에.
        def _build_video_prompt(p_en: str, m_desc: str, max_chars: int = 700) -> str:
            m = (m_desc or "").strip()
            v = (p_en or "").strip()
            if m:
                # motion_desc가 있으면 앞에 배치, 뒤에 시각 컨텍스트 요약(150자) 추가
                v_short = v[:150].rstrip(', ') if v else ""
                combined = f"{m}, {v_short}".strip(', ') if v_short else m
            else:
                # motion_desc 없으면 기본 모션 + prompt_en 요약
                v_short = v[:300].rstrip(', ') if v else "smooth cinematic scene"
                combined = f"smooth slow pan, {v_short}"
            return combined[:max_chars]
        # ─────────────────────────────────────────────────────────────────

        # 2. Engine Routing
        # [FIX] motion_desc 없으면 AI로 자동 생성
        effective_motion_desc = req.motion_desc or target_p.get('motion_desc') or ""
        if not effective_motion_desc:
            try:
                from services.gemini_service import gemini_service
                prompt_en_for_motion = target_p.get('prompt_en') or target_p.get('visual_desc') or ""
                scene_text_for_motion = target_p.get('scene_text') or ""
                effective_motion_desc = await gemini_service.generate_motion_desc(
                    scene_text_for_motion, prompt_en_for_motion
                )
                # DB에도 저장 (다음에 재사용)
                if effective_motion_desc:
                    conn = db.get_db()
                    conn.execute(
                        "UPDATE image_prompts SET motion_desc=? WHERE project_id=? AND scene_number=?",
                        (effective_motion_desc, project_id, req.scene_number)
                    )
                    conn.commit()
                    conn.close()
            except Exception as me:
                print(f"⚠️ motion_desc 자동 생성 실패: {me}")

        # [FIX] 웹툰 pan 씬에서 Wan 엔진 자동 전환 (세로 판넬 잘림 방지)
        PAN_KEYWORDS = ("pan_up", "pan_down", "pan up", "pan down", "vertical pan", "tilt up", "tilt down")
        is_pan_scene = any(kw in (effective_motion_desc or "").lower() for kw in PAN_KEYWORDS)
        actual_engine = req.engine
        pan_redirected = False
        if actual_engine == "wan" and is_pan_scene:
            actual_engine = "image"
            pan_redirected = True
            print(f"⚠️ [Studio] Scene {req.scene_number}: pan 씬 감지 → Wan 대신 image 엔진으로 자동 전환")

        if actual_engine == "wan":
            # [Wan] Motion Generation
            # Prioritize: Req(override) > DB(motion_desc) > prompt_en 요약 폴백
            motion_part = effective_motion_desc
            prompt_en   = target_p.get('prompt_en') or target_p.get('visual_desc') or ""
            final_prompt = _build_video_prompt(prompt_en, motion_part, max_chars=1000)
            
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

        elif actual_engine == "seedance":
            # [Seedance 1.5 Pro] Akool v4 API - 가장 저렴한 선택
            # Akool API 700자 제한 → motion_desc 우선 배치로 잘림 방지
            motion_part = effective_motion_desc
            prompt_en   = target_p.get('prompt_en') or target_p.get('visual_desc') or ""
            final_prompt = _build_video_prompt(prompt_en, motion_part, max_chars=650)

            print(f"🌱 [Studio] Generating Akool v4 Video for Scene {req.scene_number}... Prompt: {final_prompt[:80]}...")
            video_data = await akool_service.generate_akool_video_v4(
                local_image_path=image_abs_path,
                prompt=final_prompt,
                duration=req.duration or 5,
                resolution=req.resolution or "720p"
            )

            if video_data:
                filename = f"vid_seedance_{project_id}_{req.scene_number}_{now.strftime('%H%M%S')}.mp4"
                out = os.path.join(config.OUTPUT_DIR, filename)
                with open(out, 'wb') as f: f.write(video_data)
                video_url = f"/output/{filename}"

        elif actual_engine == "akool":
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

        elif actual_engine == "image":
            # [2D Motion] Simple Pan/Zoom
            # Check Webtoon Settings
            s_set = db.get_project_settings(project_id) or {}
            # [NEW] Check Global Webtoon Settings
            w_auto = db.get_global_setting("webtoon_auto_split", True, value_type="bool")
            w_pan = db.get_global_setting("webtoon_smart_pan", True, value_type="bool")
            w_zoom = db.get_global_setting("webtoon_convert_zoom", True, value_type="bool")

            # pan 씬 자동 전환 시 motion_desc에서 판 방향 추출, 아니면 req.motion_desc 사용
            if pan_redirected:
                raw_motion = effective_motion_desc.lower().replace(" ", "_")
            else:
                raw_motion = req.motion_desc.strip().lower().replace(" ", "_") if req.motion_desc else "zoom_in"
            # Map description to supported motion if possible, or default
            motion_part = raw_motion if raw_motion in ["pan_down", "pan_up", "zoom_in", "zoom_out", "pan_left", "pan_right", "static"] else "zoom_in"

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
            result = {"status": "success", "video_url": video_url, "engine_used": actual_engine}
            if pan_redirected:
                result["warning"] = f"pan 씬 감지: Wan → image 엔진으로 자동 전환됨 (세로 잘림 방지)"
            return result
        else:
            raise HTTPException(500, "Video generation returned no data")

    except Exception as e:
        print(f"Generate Single Video Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


class SceneTTSRequest(BaseModel):
    voice_provider: Optional[str] = None  # None이면 DB 설정 사용
    voice_id: Optional[str] = None


@router.post("/projects/{project_id}/generate-tts-scenes")
async def generate_tts_scenes(project_id: int, req: SceneTTSRequest):
    """씬 분할 TTS 생성 (오토파일럿과 동일한 방식 — 수동 워크플로우용)"""
    try:
        from services import tts_service
        from config import config
        import os, uuid

        # 1. 씬 목록 로드 (scene_text 포함)
        image_prompts = db.get_image_prompts(project_id)
        if not image_prompts:
            raise HTTPException(400, "이미지 프롬프트(씬 목록)가 없습니다. 먼저 이미지 프롬프트를 생성하세요.")

        # 2. 보이스 설정 결정 (요청 → DB 설정 → 기본값 순)
        p_settings = db.get_project_settings(project_id) or {}
        provider = req.voice_provider or p_settings.get("voice_provider") or "elevenlabs"
        voice_id = req.voice_id or p_settings.get("voice_id") or p_settings.get("voice_name")
        if provider == "elevenlabs" and not voice_id:
            voice_id = "4JJwo477JUAx3HV0T7n7"
        if not voice_id:
            voice_id = "ko-KR-Neural2-A"

        sorted_prompts = sorted(image_prompts, key=lambda x: x.get('scene_number', 0))
        results = []
        cumulative_time = 0.0
        all_alignments = []

        for p in sorted_prompts:
            scene_num = p.get('scene_number')
            text = p.get('scene_text') or p.get('narrative') or p.get('script') or ""
            if not text:
                results.append({"scene_number": scene_num, "status": "skipped", "reason": "no_text"})
                continue

            # 씬별 보이스 오버라이드 지원
            current_voice = p_settings.get(f"scene_{scene_num}_voice") or voice_id
            scene_filename = f"tts_{project_id}_{scene_num:03d}_{uuid.uuid4().hex[:6]}.mp3"

            try:
                if provider == "elevenlabs":
                    vs_json = p_settings.get(f"scene_{scene_num}_voice_settings")
                    voice_settings = None
                    if vs_json:
                        import json as _json
                        try: voice_settings = _json.loads(vs_json)
                        except Exception: pass
                    result = await tts_service.generate_elevenlabs(text, current_voice, scene_filename, voice_settings=voice_settings)
                    if result and result.get("audio_path"):
                        audio_path = result["audio_path"]
                        duration = result.get("duration", 3.0)
                        for w in result.get("alignment", []):
                            all_alignments.append({
                                "word": w["word"],
                                "start": w["start"] + cumulative_time,
                                "end":   w["end"]   + cumulative_time,
                            })
                        cumulative_time += duration
                        audio_url = f"/output/{os.path.basename(audio_path)}"
                        db.update_project_setting(project_id, f"scene_{scene_num}_audio_path", audio_path)
                        results.append({"scene_number": scene_num, "status": "ok", "audio_url": audio_url, "duration": duration})
                    else:
                        results.append({"scene_number": scene_num, "status": "error", "reason": "elevenlabs_failed"})
                else:
                    s_out = None
                    if provider == "openai":
                        s_out = await tts_service.generate_openai(text, current_voice, model="tts-1", filename=scene_filename)
                    elif provider == "gemini":
                        s_out = await tts_service.generate_gemini(text, current_voice, filename=scene_filename)
                    else:
                        s_out = await tts_service.generate_google_cloud(text, current_voice, filename=scene_filename)

                    if s_out and os.path.exists(s_out):
                        try:
                            try: from moviepy import AudioFileClip
                            except ImportError: from moviepy.audio.io.AudioFileClip import AudioFileClip
                            ac = AudioFileClip(s_out); dur = ac.duration; ac.close()
                        except Exception: dur = 3.0
                        cumulative_time += dur
                        audio_url = f"/output/{os.path.basename(s_out)}"
                        db.update_project_setting(project_id, f"scene_{scene_num}_audio_path", s_out)
                        results.append({"scene_number": scene_num, "status": "ok", "audio_url": audio_url, "duration": dur})
                    else:
                        results.append({"scene_number": scene_num, "status": "error", "reason": "tts_failed"})

            except Exception as te:
                results.append({"scene_number": scene_num, "status": "error", "reason": str(te)})

        # 워드 정렬 데이터 저장 (자막 싱크용)
        if all_alignments:
            import json as _json
            db.update_project_setting(project_id, "tts_word_alignment", _json.dumps(all_alignments, ensure_ascii=False))

        ok_count = sum(1 for r in results if r["status"] == "ok")
        return {
            "status": "success",
            "total": len(results),
            "ok": ok_count,
            "scenes": results,
            "provider": provider,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))
