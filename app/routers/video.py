"""
Video Rendering & Subtitle Router
영상 렌더링 및 자막 생성 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Query, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Union
import os
import json
import time
import datetime
import re

from config import config
import database as db
from services.video_service import video_service
from services.storage_service import storage_service

router = APIRouter(prefix="/api", tags=["video"])


# ===========================================
# Pydantic Models
# ===========================================

class RenderRequest(BaseModel):
    project_id: Union[int, str]
    use_subtitles: bool = True
    resolution: str = "1080p"  # 1080p or 720p


class SubtitleGenerationRequest(BaseModel):
    project_id: Union[int, str]
    text: Optional[str] = None


# ===========================================
# Helper Functions
# ===========================================

def get_project_output_dir(project_id: int):
    """프로젝트 ID를 기반으로 '프로젝트명_날짜' 형식의 폴더를 생성하고 경로를 반환합니다."""
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output"  # Fallback

    # 폴더명 생성 (프로젝트명 + 생성일자 YYYYMMDD)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip().replace(" ", "_")
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_name = f"{safe_name}_{today}"
    
    # 전체 경로
    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    os.makedirs(abs_path, exist_ok=True)
    
    # 웹 접근 경로
    web_path = f"/output/{folder_name}"
    
    return abs_path, web_path


# ===========================================
# API: 자막 (Subtitle)
# ===========================================

@router.get("/subtitle/{project_id}")
async def get_subtitles(project_id: int):
    """자막 데이터 조회"""
    try:
        # 1. Project & TTS Check
        tts_data = db.get_tts(project_id)
        if not tts_data or not tts_data.get('audio_path'):
            return {"status": "error", "error": "TTS 오디오가 없습니다. 먼저 TTS를 생성해주세요."}
            
        settings = db.get_project_settings(project_id)
        
        # 2. Audio URL
        audio_path = tts_data['audio_path']
        web_url = None
        if audio_path.startswith(config.OUTPUT_DIR):
             rel = os.path.relpath(audio_path, config.OUTPUT_DIR).replace("\\", "/")
             web_url = f"/output/{rel}"
        
        # Calculate accurate duration for frontend sync
        audio_duration = 0.0
        try:
            import pydub
            audio_seg = pydub.AudioSegment.from_file(audio_path)
            audio_duration = audio_seg.duration_seconds
        except:
            try:
                from moviepy.editor import AudioFileClip
                with AudioFileClip(audio_path) as clip:
                    audio_duration = clip.duration
            except:
                pass

        # 3. Load Subtitles (JSON) if exists
        subtitles = []
        subtitle_path = settings.get('subtitle_path')
        if subtitle_path and os.path.exists(subtitle_path):
            try:
                with open(subtitle_path, "r", encoding="utf-8") as f:
                    subtitles = json.load(f)
            except:
                pass
        
        # 4. Images for preview
        image_prompts = db.get_image_prompts(project_id)
        source_images = []
        for p in image_prompts:
            if p.get('video_url'):
                source_images.append(p['video_url'])
            elif p.get('image_url'):
                source_images.append(p['image_url'])

        # Timeline Images (Used in Video)
        timeline_images_path = settings.get('timeline_images_path')
        timeline_images = []
        if timeline_images_path and os.path.exists(timeline_images_path):
            try:
                with open(timeline_images_path, "r", encoding="utf-8") as f:
                    timeline_images = json.load(f)
                
                # Auto-update Timeline with Video URLs if available
                img_to_vid_map = {}
                for p in image_prompts:
                    if p.get('image_url') and p.get('video_url'):
                        img_to_vid_map[p['image_url']] = p['video_url']
                        img_to_vid_map[os.path.basename(p['image_url'])] = p['video_url']
                        try:
                            import urllib.parse
                            decoded = urllib.parse.unquote(p['image_url'])
                            img_to_vid_map[decoded] = p['video_url']
                            img_to_vid_map[os.path.basename(decoded)] = p['video_url']
                        except:
                            pass

                # Patch Timeline
                patched = False
                for idx, t_img in enumerate(timeline_images):
                    if not t_img:
                        continue
                    
                    if t_img in img_to_vid_map:
                        timeline_images[idx] = img_to_vid_map[t_img]
                        patched = True
                    elif os.path.basename(t_img) in img_to_vid_map:
                        timeline_images[idx] = img_to_vid_map[os.path.basename(t_img)]
                        patched = True

                if patched:
                    try:
                        with open(timeline_images_path, "w", encoding="utf-8") as f:
                            json.dump(timeline_images, f, indent=2)
                    except:
                        pass
            except Exception as e:
                print(f"[Timeline Patch Error] {e}")
        
        # Default to source if no timeline
        if not timeline_images:
            timeline_images = source_images[:]

        # Calculate Image Timings for Frontend Preview
        image_timings = []
        saved_timings_path = settings.get('image_timings_path')
        if saved_timings_path and os.path.exists(saved_timings_path):
             try:
                 with open(saved_timings_path, "r") as f:
                     image_timings = json.load(f)
             except:
                 pass
        
        # Calculate Only if NO saved timings
        if not image_timings:
            try:
                num_img = len(timeline_images)
                num_sub = len(subtitles)
                
                if num_img > 0 and num_sub > 0:
                    if num_sub >= num_img:
                        step = num_sub / num_img
                        image_timings = [0.0]
                        for i in range(1, num_img):
                            sub_idx = int(i * step)
                            sub_idx = min(sub_idx, num_sub - 1)
                            if sub_idx < len(subtitles):
                                t_start = subtitles[sub_idx]['start']
                                if t_start < image_timings[-1]:
                                    t_start = image_timings[-1]
                                image_timings.append(t_start)
                            else:
                                 image_timings.append(image_timings[-1] + 2.0)
            except Exception as e:
                print(f"Error calc timings in get_subtitles: {e}")

        # Load Image Effects (Zoom/Pan)
        image_effects = []
        effects_path = settings.get('image_effects_path')
        if effects_path and os.path.exists(effects_path):
            try:
                with open(effects_path, "r", encoding="utf-8") as f:
                    image_effects = json.load(f)
            except Exception as e:
                print(f"Failed to load image effects: {e}")

        return {
            "status": "ok",
            "subtitles": subtitles,
            "audio_url": web_url,
            "audio_duration": audio_duration,
            "images": source_images,
            "timeline_images": timeline_images,
            "image_timings": image_timings,
            "image_effects": image_effects
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/subtitle/generate")
async def generate_subtitles_api(req: dict = Body(...)):
    """자막 자동 생성 (Whisper)"""
    project_id = req.get("project_id")
    if not project_id:
        raise HTTPException(400, "project_id required")
        
    try:
        # Load necessary data
        tts_data = db.get_tts(project_id)
        if not tts_data or not tts_data.get('audio_path'):
            return {"status": "error", "error": "TTS 오디오가 없습니다."}
            
        project = db.get_project(project_id)
        
        # Script text for alignment (optional)
        script_data = db.get_script(project_id)
        full_script = script_data['full_script'] if script_data else ""
        
        # Service Call
        subtitles = video_service.generate_aligned_subtitles(tts_data['audio_path'], full_script)
        
        if not subtitles:
            return {"status": "error", "error": "자막 생성 실패 (Whisper 오류)"}
            
        # Save to JSON
        filename = f"subtitles_{project_id}_{int(time.time())}.json"
        save_path = os.path.join(config.OUTPUT_DIR, filename)
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(subtitles, f, ensure_ascii=False, indent=2)
            
        # Update DB
        db.update_project_setting(project_id, 'subtitle_path', save_path)
        
        # Calculate Image Timings for Frontend Preview
        image_timings = []
        image_urls = []
        try:
             images_data = db.get_image_prompts(project_id)
             if images_data:
                 image_urls = []
                 for img in images_data:
                     if img.get('video_url'):
                         image_urls.append(img['video_url'])
                     elif img.get('image_url'):
                         image_urls.append(img['image_url'])
             
             num_img = len(images_data) if images_data else 0
             num_sub = len(subtitles)
             
             if num_img > 0 and num_sub > 0:
                 if num_sub >= num_img:
                     step = num_sub / num_img
                     image_timings = [0.0]
                     for i in range(1, num_img):
                         sub_idx = int(i * step)
                         sub_idx = min(sub_idx, num_sub - 1)
                         t_start = subtitles[sub_idx]['start']
                         if t_start < image_timings[-1]:
                             t_start = image_timings[-1]
                         image_timings.append(t_start)
        except Exception as e:
             pass
        
        return {"status": "ok", "subtitles": subtitles, "image_timings": image_timings, "images": image_urls}
        
    except Exception as e:
        print(f"Subtitle Gen Error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/subtitle/save")
async def save_subtitles_api(req: dict = Body(...)):
    """자막 수동 저장"""
    project_id = req.get("project_id")
    subtitles = req.get("subtitles")
    
    if not project_id or subtitles is None:
        raise HTTPException(400, "Invalid data")
        
    try:
        # Save Subtitles to JSON
        filename = f"subtitles_{project_id}_saved_{int(time.time())}.json"
        save_path = os.path.join(config.OUTPUT_DIR, filename)
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(subtitles, f, ensure_ascii=False, indent=2)
            
        # Update DB
        db.update_project_setting(project_id, 'subtitle_path', save_path)
        
        # Save Image Timings if provided
        image_timings = req.get("image_timings")
        if image_timings:
             timings_filename = f"image_timings_{project_id}_{int(time.time())}.json"
             timings_path = os.path.join(config.OUTPUT_DIR, timings_filename)
             with open(timings_path, "w", encoding="utf-8") as f:
                 json.dump(image_timings, f, indent=2)
             db.update_project_setting(project_id, 'image_timings_path', timings_path)

        # Save Timeline Images (Custom Order/Reuse)
        timeline_images = req.get("images")
        if timeline_images:
             tl_filename = f"timeline_images_{project_id}_{int(time.time())}.json"
             tl_path = os.path.join(config.OUTPUT_DIR, tl_filename)
             with open(tl_path, "w", encoding="utf-8") as f:
                 json.dump(timeline_images, f, indent=2)
             db.update_project_setting(project_id, 'timeline_images_path', tl_path)

        # Save Image Effects
        image_effects = req.get("image_effects")
        if image_effects:
             ef_filename = f"image_effects_{project_id}_{int(time.time())}.json"
             ef_path = os.path.join(config.OUTPUT_DIR, ef_filename)
             with open(ef_path, "w", encoding="utf-8") as f:
                 json.dump(image_effects, f, indent=2)
             db.update_project_setting(project_id, 'image_effects_path', ef_path)

        return {"status": "ok", "subtitles": subtitles, "image_timings": image_timings, "images": timeline_images, "image_effects": image_effects}
    except Exception as e:
        print(f"Save Subtitles Error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/subtitle/auto_sync_images")
async def auto_sync_images_api(req: dict = Body(...)):
    """Gemini를 사용해 이미지와 자막 싱크 자동 맞춤"""
    project_id = req.get("project_id")
    if not project_id:
        raise HTTPException(400, "Project ID required")

    try:
        # 1. Load Data
        settings = db.get_project_settings(project_id)
        
        # Subtitles
        subtitle_path = settings.get('subtitle_path')
        subtitles = []
        if subtitle_path and os.path.exists(subtitle_path):
            with open(subtitle_path, "r", encoding="utf-8") as f:
                subtitles = json.load(f)
        else:
             return {"status": "error", "error": "자막이 없습니다. 먼저 자막을 생성하세요."}

        # Images (Source)
        prompts_data = db.get_image_prompts(project_id)
        valid_images = [p for p in prompts_data if p.get('image_url')]
        
        if not valid_images:
             return {"status": "error", "error": "생성된 이미지가 없습니다."}

        # 2. Hybrid Sync Logic
        new_timeline_images = []
        new_image_timings = []
        
        # Strategy A: Use 'script_start' tags (Deterministic)
        has_tags = any(img.get('script_start') and img.get('script_start').strip() for img in valid_images)
        
        matched_count = 0
        if has_tags:
            print("[AutoSync] 'script_start' tags found. Attempting deterministic sync.")
            
            valid_images.sort(key=lambda x: x.get('scene_number', 0))
            current_sub_idx = 0
            
            for img in valid_images:
                tag = img.get('script_start', '').strip()
                if not tag:
                    continue
                    
                found_idx = -1
                for i in range(current_sub_idx, len(subtitles)):
                    sub_clean = re.sub(r'\s+', '', subtitles[i]['text'])
                    tag_clean = re.sub(r'\s+', '', tag)
                    
                    if tag_clean in sub_clean or sub_clean in tag_clean:
                        found_idx = i
                        break
                
                if found_idx != -1:
                    new_timeline_images.append(img['image_url'])
                    new_image_timings.append(subtitles[found_idx]['start'])
                    current_sub_idx = found_idx
                    matched_count += 1
                else:
                    print(f"[AutoSync] Could not match tag: '{tag}'")
                    
        # Strategy B: Gemini AI Match (Fallback)
        if matched_count < len(valid_images) * 0.3:
            print(f"[AutoSync] Tag match rate low ({matched_count}/{len(valid_images)}). Falling back to Gemini.")
            
            new_timeline_images = []
            new_image_timings = []
            
            result = await gemini_service.match_images_to_subtitles(subtitles, valid_images)
            assignments = result.get('assignments', [])
            assignments.sort(key=lambda x: x.get('subtitle_id', 0))
            
            for assign in assignments:
                img_id = assign.get('image_id')
                sub_id = assign.get('subtitle_id')
                
                if img_id is not None and sub_id is not None:
                    if 0 <= img_id < len(valid_images) and 0 <= sub_id < len(subtitles):
                        img_url = valid_images[img_id]['image_url']
                        start_time = subtitles[sub_id]['start']
                        new_timeline_images.append(img_url)
                        new_image_timings.append(start_time)
            
            if len(new_timeline_images) < len(valid_images) * 0.8:
                print(f"[AutoSync] Low coverage ({len(new_timeline_images)}/{len(valid_images)}). Fallback to Even Distribution.")
                new_timeline_images = []
                new_image_timings = []
        
        # Strategy C: Even Distribution (Final Fallback)
        if not new_timeline_images:
             print("[AutoSync] AI/Tag sync failed. Falling back to even distribution.")
             new_timeline_images = [p['image_url'] for p in valid_images]
             duration = subtitles[-1]['end'] if subtitles else 60
             step = duration / len(new_timeline_images) if new_timeline_images else 5
             new_image_timings = [i * step for i in range(len(new_timeline_images))]

        # 4. Save Results
        tl_filename = f"timeline_images_{project_id}_auto_{int(time.time())}.json"
        tl_path = os.path.join(config.OUTPUT_DIR, tl_filename)
        with open(tl_path, "w", encoding="utf-8") as f:
            json.dump(new_timeline_images, f, indent=2)
        db.update_project_setting(project_id, 'timeline_images_path', tl_path)
        
        timings_filename = f"image_timings_{project_id}_auto_{int(time.time())}.json"
        timings_path = os.path.join(config.OUTPUT_DIR, timings_filename)
        with open(timings_path, "w", encoding="utf-8") as f:
             json.dump(new_image_timings, f, indent=2)
        db.update_project_setting(project_id, 'image_timings_path', timings_path)

        return {
            "status": "ok", 
            "message": f"{len(new_timeline_images)}개 이미지 싱크 완료",
            "timeline_images": new_timeline_images,
            "image_timings": new_image_timings
        }

    except Exception as e:
        print(f"Auto Sync Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/project/{project_id}/subtitle/regenerate")
async def regenerate_subtitles_api(project_id: int):
    """자막 강제 재생성"""
    return await generate_subtitles_api({"project_id": project_id})


@router.post("/projects/{project_id}/subtitle/reset")
async def reset_subtitle_timeline(project_id: int):
    """타임라인 이미지/타이밍/효과 설정을 초기화"""
    try:
        db.update_project_setting(project_id, 'timeline_images_path', None)
        db.update_project_setting(project_id, 'image_timings_path', None)
        db.update_project_setting(project_id, 'image_effects_path', None)
        
        return {"status": "ok", "message": "타임라인이 초기화되었습니다."}
    except Exception as e:
        print(f"Reset Error: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/projects/{project_id}/subtitles")
async def get_project_subtitles(project_id: int, force_refresh: bool = False):
    """프로젝트 자막 및 이미지 싱크 데이터 조회"""
    try:
        settings = db.get_project_settings(project_id) or {}
        subtitle_path = settings.get('subtitle_path')
        image_timings_path = settings.get('image_timings_path')
        timeline_images_path = settings.get('timeline_images_path')

        subtitles = []
        image_timings = []
        timeline_images = []

        if force_refresh:
            print(f"DEBUG: Force Refresh requested for Project {project_id}. Ignoring saved timeline/timings.")
            image_timings_path = None
            timeline_images_path = None

        # Load subtitles
        if subtitle_path and os.path.exists(subtitle_path):
             with open(subtitle_path, "r", encoding="utf-8") as f:
                 subtitles = json.load(f)
        
        # Load image timings
        if image_timings_path and os.path.exists(image_timings_path):
             with open(image_timings_path, "r", encoding="utf-8") as f:
                 image_timings = json.load(f)
        
        # Load timeline images
        if timeline_images_path and os.path.exists(timeline_images_path):
             with open(timeline_images_path, "r", encoding="utf-8") as f:
                 timeline_images = json.load(f)
        
        # Source images from DB
        prompts = db.get_image_prompts(project_id)
        source_images = [p['image_url'] for p in prompts if p.get('image_url')]

        # Fallback to source images if timeline is empty
        if not timeline_images:
             timeline_images = source_images[:]
             
             if not image_timings or len(image_timings) != len(timeline_images):
                  image_timings = [0.0]
                  if subtitles and len(timeline_images) > 0:
                      if len(subtitles) > len(timeline_images):
                          step = len(subtitles) / len(source_images)
                          for i in range(1, len(source_images)):
                              idx = min(int(i * step), len(subtitles) - 1)
                              image_timings.append(subtitles[idx]['start'])

        # Patch timeline with video URLs if available
        try:
            img_to_vid_map = {}
            for p in prompts:
                if p.get('image_url') and p.get('video_url'):
                    img_to_vid_map[p['image_url']] = p['video_url']
                    img_to_vid_map[os.path.basename(p['image_url'])] = p['video_url']
                    try:
                        import urllib.parse
                        dec = urllib.parse.unquote(p['image_url'])
                        img_to_vid_map[dec] = p['video_url']
                        img_to_vid_map[os.path.basename(dec)] = p['video_url']
                    except:
                        pass
            
            patched = False
            for idx, t_img in enumerate(timeline_images):
                if not t_img:
                    continue
                
                if t_img in img_to_vid_map:
                    timeline_images[idx] = img_to_vid_map[t_img]
                    patched = True
                elif os.path.basename(t_img) in img_to_vid_map:
                    timeline_images[idx] = img_to_vid_map[os.path.basename(t_img)]
                    patched = True
            
            if patched and timeline_images_path:
                try:
                    with open(timeline_images_path, "w", encoding="utf-8") as f:
                        json.dump(timeline_images, f, indent=2)
                except:
                    pass
        except Exception as e:
            print(f"Timeline Patch Error: {e}")

        # Update source_images to use video_url if available
        source_images = []
        for p in prompts:
            if p.get('video_url'):
                source_images.append(p['video_url'])
            elif p.get('image_url'):
                source_images.append(p['image_url'])

        # Load Image Effects
        image_effects = []
        effects_path = settings.get('image_effects_path')
        if effects_path and os.path.exists(effects_path):
             try:
                 with open(effects_path, "r", encoding="utf-8") as f:
                     image_effects = json.load(f)
             except Exception as e:
                 print(f"Error loading effects: {e}")

        return {
            "status": "ok",
            "subtitles": subtitles,
            "image_timings": image_timings,
            "timeline_images": timeline_images,
            "source_images": source_images,
            "image_effects": image_effects,
            "settings": settings 
        }

    except Exception as e:
        print(f"Get Subtitles Error: {e}")
        return {"status": "error", "error": str(e)}


# ===========================================
# API: 영상 렌더링
# ===========================================

@router.post("/video/create-slideshow")
async def create_slideshow(
    background_tasks: BackgroundTasks,
    images: List[str],
    audio_url: Optional[str] = None,
    duration_per_image: float = 5.0
):
    """이미지 슬라이드쇼 영상 생성"""
    now_kst = config.get_kst_time()
    output_filename = f"video_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"

    async def process_video_generation():
        try:
            video_path = video_service.create_slideshow(
                images=images,
                audio_path=audio_url,
                output_filename=output_filename,
                duration_per_image=duration_per_image
            )
            
            if audio_url:
                try:
                    from moviepy.editor import AudioFileClip
                    audio_clip = AudioFileClip(audio_url)
                    duration = audio_clip.duration
                    audio_clip.close()
                    print(f"영상 생성 완료: {video_path}")
                except Exception as e:
                    print(f"자막 처리 중 오류: {e}")

        except Exception as e:
            print(f"영상 생성 실패: {e}")

    background_tasks.add_task(process_video_generation)

    return {
        "status": "processing",
        "message": "영상 생성 시작",
        "output_file": output_filename
    }


@router.post("/projects/{project_id}/render")
async def render_project_video(
    project_id: int,
    request: RenderRequest,
    background_tasks: BackgroundTasks
):
    """프로젝트 영상 최종 렌더링 (이미지 + 오디오 + 자막)"""
    try:
        from services.settings_service import settings_service
        global_settings = settings_service.get_settings()
        app_mode = global_settings.get("app_mode", "longform")

        # 해상도 설정
        if app_mode == 'shorts':
            target_resolution = (1080, 1920)  # 9:16
        else:
            target_resolution = (1920, 1080)  # 16:9
            
        if request.resolution == "720p":
            if app_mode == 'shorts':
                target_resolution = (720, 1280)
            else:
                target_resolution = (1280, 720)
        
        print(f"DEBUG: Rendering in {app_mode} mode at {target_resolution}")
        
        # 1. 데이터 조회
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        
        if not images_data:
            raise HTTPException(400, "이미지 데이터가 없습니다.")
        if not tts_data:
            raise HTTPException(400, "TTS 오디오 데이터가 없습니다.")
        
        # Load Timeline Images from Config if available
        p_settings = db.get_project_settings(project_id)
        timeline_path = p_settings.get('timeline_images_path') if p_settings else None
        
        images = []
        loaded_from_timeline = False
        
        if timeline_path and os.path.exists(timeline_path):
             try:
                 with open(timeline_path, "r", encoding="utf-8") as f:
                     timeline_urls = json.load(f)
                 
                 print(f"DEBUG: Loading images from timeline path: {timeline_path} ({len(timeline_urls)} images)")
                 
                 for url in timeline_urls:
                     if not url:
                         continue
                     if url.startswith("/static/"):
                        rel = url.replace("/static/", "", 1).replace("/", os.sep)
                        fpath = os.path.join(config.STATIC_DIR, rel)
                     elif url.startswith("/output/"):
                        rel = url.replace("/output/", "", 1).replace("/", os.sep)
                        fpath = os.path.join(config.OUTPUT_DIR, rel)
                     else:
                        continue
                     
                     if os.path.exists(fpath):
                         images.append(fpath)
                         
                 if images:
                     loaded_from_timeline = True
             except Exception as e:
                 print(f"Failed to load timeline images: {e}")
                 
        # Fallback to DB if no timeline
        if not loaded_from_timeline:
            print("DEBUG: No timeline found, loading from DB prompts")
            for img in images_data:
                if img.get("image_url"):
                    if img["image_url"].startswith("/static/"):
                        relative_path = img["image_url"].replace("/static/", "", 1)
                        relative_path = relative_path.replace("/", os.sep)
                        fpath = os.path.join(config.STATIC_DIR, relative_path)
                    elif img["image_url"].startswith("/output/"):
                        relative_path = img["image_url"].replace("/output/", "", 1)
                        fpath = os.path.join(config.OUTPUT_DIR, relative_path)
                    else:
                        continue

                    if os.path.exists(fpath):
                        images.append(fpath)
        
        if not images:
             project_settings = db.get_project_settings(project_id)
             bg_video_url = project_settings.get("background_video_url")
             if not bg_video_url:
                 raise HTTPException(400, "유효한 이미지 파일 또는 배경 동영상이 없습니다.")
        else:
             project_settings = db.get_project_settings(project_id)
             bg_video_url = project_settings.get("background_video_url")
            
        # 오디오 경로
        audio_path = tts_data.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(400, "오디오 파일을 찾을 수 없습니다.")

        # 2. 백그라운드 렌더링 준비
        output_dir, web_dir = get_project_output_dir(project_id)
        
        now_kst = config.get_kst_time()
        final_output_filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"
        final_output_path = os.path.join(output_dir, final_output_filename)

        def render_executor_func(target_dir_arg, use_subtitles_arg, target_resolution_arg, bg_video_url_arg, intro_video_path_arg):
            import PIL.Image
            import datetime
            if not hasattr(PIL.Image, 'ANTIALIAS'):
                PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Starting render for project {project_id}\n")
                    rf.write(f"[{datetime.datetime.now()}] Images: {len(images)}, Audio: {audio_path}\n")

                # 1. 자막 데이터 및 설정 준비
                subs = []
                s_settings = {}
                if use_subtitles_arg:
                    s_settings = db.get_project_settings(project_id) or {}
                    s_settings = {
                        "font": s_settings.get("subtitle_font", config.DEFAULT_FONT_PATH),
                        "font_color": s_settings.get("subtitle_base_color", "white"),
                        "style_name": s_settings.get("subtitle_style_enum", "Basic_White"),
                        "font_size": float(s_settings.get("subtitle_font_size", 5.4)),
                        "stroke_color": s_settings.get("subtitle_stroke_color", "black"),
                        "stroke_width": float(s_settings.get("subtitle_stroke_width") or 0.0),
                        "subtitle_stroke_enabled": int(s_settings.get("subtitle_stroke_enabled", 0)), 
                        "position_y": s_settings.get("subtitle_pos_y"), 
                        "bg_enabled": int(s_settings.get("subtitle_bg_enabled", 1)),
                        "line_spacing": float(s_settings.get("subtitle_line_spacing", 0.1)),
                        "bg_color": s_settings.get("subtitle_bg_color", "#000000"),
                        "bg_opacity": float(s_settings.get("subtitle_bg_opacity", 0.5))
                    }

                    # 자막 데이터 로드
                    inner_output_dir, _ = get_project_output_dir(project_id)
                    p_settings = db.get_project_settings(project_id)
                    db_sub_path = p_settings.get('subtitle_path') if p_settings else None
                    
                    subs = None
                    if db_sub_path and os.path.exists(db_sub_path):
                        print(f"DEBUG_RENDER: Loading subtitles from DB path: {db_sub_path}")
                        try:
                            with open(db_sub_path, "r", encoding="utf-8") as f:
                                subs = json.load(f)
                        except Exception as e:
                            print(f"DEBUG_RENDER: Failed to load DB sub path: {e}")
                    
                    if not subs:
                        saved_sub_path = os.path.join(inner_output_dir, f"subtitles_{project_id}.json")
                        if os.path.exists(saved_sub_path):
                            print(f"DEBUG_RENDER: Loading subtitles from default path: {saved_sub_path}")
                            with open(saved_sub_path, "r", encoding="utf-8") as f:
                                subs = json.load(f)
                    
                    if not subs:
                        print("DEBUG_RENDER: No saved subtitles found. Generating from scratch.")
                        script = script_data.get("full_script") if script_data else ""
                        subs = video_service.generate_aligned_subtitles(audio_path, script)

                # 2. 오디오 정보
                audio_duration = 0.0
                try:
                    import pydub
                    audio_seg = pydub.AudioSegment.from_file(audio_path)
                    audio_duration = audio_seg.duration_seconds
                except:
                    from moviepy.editor import AudioFileClip
                    with AudioFileClip(audio_path) as audio_clip:
                        audio_duration = audio_clip.duration
                
                print(f"DEBUG_RENDER: Audio duration: {audio_duration}s")
                
                # Dynamic Image Pacing
                num_img = len(images) if images else 0
                num_sub = len(subs) if subs else 0
                duration_per_image = 5.0
                
                if num_img > 0:
                    forced_timings = None
                    i_settings = db.get_project_settings(project_id)
                    tm_path = i_settings.get('image_timings_path') if i_settings else None
                    if tm_path and os.path.exists(tm_path):
                        try:
                            with open(tm_path, "r", encoding="utf-8") as f:
                                forced_timings = json.load(f)
                            print(f"DEBUG_RENDER: Loaded explicit image timings from {tm_path}")
                        except Exception as e:
                            print(f"DEBUG_RENDER: Failed to load image timings: {e}")

                    if num_sub >= num_img and num_sub > 0:
                        durations = []
                        
                        if forced_timings and len(forced_timings) > 0:
                             print(f"DEBUG_RENDER: Using FORCED timings")
                             
                             if len(forced_timings) > num_img:
                                 current_start_times = forced_timings[:num_img]
                             elif len(forced_timings) < num_img:
                                 current_start_times = forced_timings[:]
                                 last_t = forced_timings[-1]
                                 for _ in range(num_img - len(forced_timings)):
                                     current_start_times.append(last_t + 5.0)
                             else:
                                 current_start_times = forced_timings
                        else:
                             print(f"DEBUG_RENDER: Using Dynamic Pacing")
                             step = num_sub / num_img
                             current_start_times = [0.0]
                             for i in range(1, num_img):
                                 sub_idx = int(i * step)
                                 sub_idx = min(sub_idx, num_sub - 1)
                                 t_start = subs[sub_idx]['start']
                                 if t_start < current_start_times[-1]:
                                     t_start = current_start_times[-1]
                                 current_start_times.append(t_start)
                        
                        for i in range(len(current_start_times)):
                            start_t = current_start_times[i]
                            if i < len(current_start_times) - 1:
                                end_t = current_start_times[i+1]
                                duration = end_t - start_t
                            else:
                                duration = max(0.1, audio_duration - start_t)
                            
                            if duration < 0.1:
                                duration = 0.1
                            durations.append(duration)
                        
                        if len(durations) != len(images):
                            if len(durations) > len(images):
                                durations = durations[:len(images)]
                            else:
                                while len(durations) < len(images):
                                    durations.append(5.0)
                        
                        duration_per_image = durations
                    else:
                        duration_per_image = audio_duration / num_img
                
                # Thumbnail Path for Shorts
                thumbnail_path_arg = None
                p_settings = db.get_project_settings(project_id) or {}

                if app_mode == 'shorts':
                    thumb_url = p_settings.get("thumbnail_url")
                    
                    if thumb_url:
                        if thumb_url.startswith("/static/"):
                            t_rel = thumb_url.replace("/static/", "", 1).replace("/", os.sep)
                            t_path = os.path.join(config.STATIC_DIR, t_rel)
                        elif thumb_url.startswith("/output/"):
                            t_rel = thumb_url.replace("/output/", "", 1).replace("/", os.sep)
                            t_path = os.path.join(config.OUTPUT_DIR, t_rel)
                        else:
                            t_path = None
                        
                        if t_path and os.path.exists(t_path):
                            thumbnail_path_arg = t_path

                # Load fade-in and effects
                fade_in_flags = []
                image_effects = []
                
                try:
                    prompts_data = db.get_image_prompts(project_id)
                    if prompts_data and prompts_data.get('prompts'):
                        fade_in_flags = [p.get('fade_in', False) for p in prompts_data['prompts']]
                except Exception as e:
                    print(f"Failed to load prompts: {e}")

                try:
                    ef_path = p_settings.get('image_effects_path')
                    if ef_path and os.path.exists(ef_path):
                        with open(ef_path, "r", encoding="utf-8") as f:
                            image_effects = json.load(f)
                except Exception as e:
                    print(f"Failed to load image effects: {e}")

                # 3. 단일 패스 영상 생성
                video_path = video_service.create_slideshow(
                    images=images,
                    audio_path=audio_path,
                    output_filename=final_output_path,
                    resolution=target_resolution_arg,
                    subtitles=subs,
                    subtitle_settings=s_settings,
                    background_video_url=bg_video_url_arg,
                    thumbnail_path=thumbnail_path_arg,
                    duration_per_image=duration_per_image,
                    fade_in_flags=fade_in_flags,
                    image_effects=image_effects,
                    intro_video_path=intro_video_path_arg,
                    project_id=project_id
                )

                final_path = video_path

                # DB 업데이트
                web_video_path = f"{web_dir}/{os.path.basename(final_path)}"
                db.update_project_setting(project_id, "video_path", web_video_path)
                db.update_project(project_id, status="rendered")
                print(f"프로젝트 {project_id} 렌더링 완료: {final_path}")

            except Exception as e:
                import traceback
                error_msg = f"프로젝트 렌더링 실패: {e}"
                print(error_msg)
                traceback.print_exc()
                
                try:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                         rf.write(f"[{datetime.datetime.now()}] Render Error: {e}\n{traceback.format_exc()}\n")
                except:
                    pass
                
                db.update_project(project_id, status="failed")

        print(f"Adding background task for project {project_id}")

        # 상태 업데이트
        db.update_project(project_id, status="rendering")
        db.update_project_setting(project_id, "video_path", "")

        intro_v_path = project_settings.get("intro_video_path")
        background_tasks.add_task(render_executor_func, output_dir, request.use_subtitles, target_resolution, bg_video_url, intro_v_path)

        return {
            "status": "processing",
            "message": "최종 영상 렌더링이 시작되었습니다.",
            "output_file": final_output_filename
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        error_msg = f"렌더링 요청 처리 중 오류: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": error_msg, "traceback": traceback.format_exc()})


@router.get("/projects/{project_id}/status")
async def get_project_status(project_id: int):
    """프로젝트 상태 및 결과물 조회 (Polling용)"""
    try:
        project = db.get_project(project_id)
        if not project:
             raise HTTPException(404, "Project not found")
        
        settings = db.get_project_settings(project_id)
        video_path = settings.get("video_path")
        
        return {
            "status": "ok",
            "project_status": project["status"],
            "video_path": video_path
        }
    except Exception as e:
        print(f"Status check failed: {e}")
        return {"status": "error", "error": str(e)}
@router.post("/video/upload-external/{project_id}")
async def upload_external_video(project_id: int, file: UploadFile = File(...)):
    """외부 영상 파일 업로드"""
    try:
        # 파일 확장자 검증
        allowed_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(400, f"지원하지 않는 파일 형식입니다. {', '.join(allowed_extensions)} 파일만 업로드 가능합니다.")
        
        # 파일 크기 검증 (2GB)
        max_size = 2 * 1024 * 1024 * 1024
        file.file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.file.tell()
        file.file.seek(0)  # 파일 처음으로 되돌리기
        
        if file_size > max_size:
            raise HTTPException(400, "파일 크기가 너무 큽니다. 최대 2GB까지 업로드 가능합니다.")
        
        # 저장 경로 생성
        upload_dir = os.path.join(config.OUTPUT_DIR, "external", str(project_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # 파일 저장
        safe_filename = f"external_video{file_ext}"
        file_path = os.path.join(upload_dir, safe_filename)
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 웹 접근 경로
        rel_path = os.path.relpath(file_path, config.OUTPUT_DIR)
        web_url = f"/output/{rel_path}".replace("\\", "/")
        
        # DB에 저장
        db.update_project_setting(project_id, 'external_video_path', file_path)
        
        return {
            "status": "ok",
            "path": file_path,
            "url": web_url,
            "size": file_size,
            "filename": file.filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"External video upload error: {e}")
        raise HTTPException(500, f"업로드 중 오류가 발생했습니다: {str(e)}")


@router.post("/video/sync-cloud/{project_id}")
async def sync_video_to_cloud(project_id: int):
    """로컬 영상을 클라우드(Supabase)로 업로드하고 경로 반환"""
    try:
        settings = db.get_project_settings(project_id)
        # 1. 우선순위: 외부 업로드 영상 -> 렌더링된 영상
        video_path = settings.get("external_video_path")
        
        # 만약 외부 경로가 없거나 존재하지 않는다면 렌더링 경로 시도
        if not video_path or not os.path.exists(video_path):
            video_path = settings.get("video_path")
            
        # 렌더링 경로는 웹 경로(/output/...)로 저장되어 있을 수 있으므로 변환 시도
        if video_path and not os.path.exists(video_path) and video_path.startswith('/output/'):
            rel_path = video_path.replace('/output/', '', 1).replace('/', os.sep)
            video_path = os.path.join(config.OUTPUT_DIR, rel_path)
            
        if not video_path or not os.path.exists(video_path):
            return {"status": "error", "error": "업로드되거나 렌더링된 영상 파일이 없습니다."}
            
        license_key = ""
        if os.path.exists("license.key"):
            with open("license.key", "r") as f:
                license_key = f.read().strip()
                
        if not license_key:
            return {"status": "error", "error": "라이선스 키를 찾을 수 없습니다."}
            
        cloud_path = storage_service.upload_video_to_cloud(license_key, video_path)
        
        if not cloud_path:
            return {"status": "error", "error": "클라우드 업로드 실패"}
            
        # Mark as uploaded/reserved locally
        db.update_project_setting(project_id, 'is_uploaded', 1)
        
        return {"status": "ok", "cloud_path": cloud_path}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.delete("/video/delete-external/{project_id}")
async def delete_external_video(project_id: int):
    """업로드된 외부 영상 삭제"""
    try:
        # DB에서 경로 조회
        settings = db.get_project_settings(project_id)
        if not settings or not settings.get('external_video_path'):
            raise HTTPException(404, "업로드된 영상이 없습니다.")
        
        file_path = settings['external_video_path']
        
        # 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # DB에서 경로 제거
        db.update_project_setting(project_id, 'external_video_path', None)
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"External video delete error: {e}")
        raise HTTPException(500, f"삭제 중 오류가 발생했습니다: {str(e)}")


@router.post("/projects/{project_id}/upload")
async def upload_project_to_youtube(
    project_id: int,
    privacy_status: str = "private", # public, unlisted, private
    publish_at: Optional[str] = None # ISO 8601
):
    """프로젝트 영상 유튜브 업로드 (예약 발행 지원)"""
    from services.youtube_upload_service import youtube_upload_service

    # 1. 데이터 조회
    project = db.get_project(project_id)
    settings = db.get_project_settings(project_id)
    metadata = db.get_metadata(project_id)
    
    if not settings or not settings.get("video_path"):
        raise HTTPException(400, "렌더링된 영상이 없습니다.")

    # Convert web path to local path
    v_path = settings["video_path"]
    if v_path.startswith('/output/'):
        rel = v_path.replace('/output/', '', 1).replace('/', os.sep)
        video_path = os.path.join(config.OUTPUT_DIR, rel)
    else:
        video_path = v_path
        
    if not os.path.exists(video_path):
        raise HTTPException(400, f"영상을 찾을 수 없습니다: {video_path}")
    
    # 2. 메타데이터 구성
    title = settings.get("title", f"Project {project_id}")
    description = ""
    tags = []
    
    if metadata:
        if metadata.get("titles"):
            title = metadata["titles"][0]
        description = metadata.get("description", "")
        tags = (metadata.get("tags", []) + metadata.get("hashtags", []))[:15]

    if not description:
        description = f"{title}\n\n#Shorts #YouTubeShorts"

    try:
        response = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            publish_at=publish_at
        )
        db.update_project_setting(project_id, "is_uploaded", 1)
        return {"status": "ok", "video_id": response.get("id"), "url": f"https://youtu.be/{response.get('id')}"}
    except Exception as e:
        print(f"Upload failed: {e}")
        return {"status": "error", "error": str(e)}
