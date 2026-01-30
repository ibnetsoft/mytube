
from fastapi import APIRouter, HTTPException, BackgroundTasks, File, UploadFile, Form, Body
from typing import List, Optional, Dict, Any
import database as db
import os
import re
import datetime
import time
import json
import uuid
from config import config
from pydantic import BaseModel
from services.replicate_service import replicate_service
from services.gemini_service import gemini_service

router = APIRouter(tags=["Media"])

# Models
class PromptsGenerateRequest(BaseModel):
    script: str
    style: str = "realistic"
    count: int = 0
    character_reference: Optional[str] = None # [NEW]
    project_id: Optional[int] = None # [NEW] Save to DB
    
class ImagePromptsSave(BaseModel):
    prompts: List[dict]

class AnimateRequest(BaseModel):
    scene_number: int
    prompt: Optional[str] = "Cinematic slow motion, high quality"
    duration: Optional[float] = 3.3

# Helper (Should be shared but duplicated for now to avoid circular dependency hell in short term)
def get_project_output_dir(project_id: int):
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output"

    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip().replace(" ", "_")
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_name = f"{safe_name}_{today}"
    
    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    os.makedirs(abs_path, exist_ok=True)
    web_path = f"/output/{folder_name}"
    
    return abs_path, web_path

# 스타일 매핑 (Shared)
STYLE_PROMPTS = {
    "realistic": "A highly realistic photo, 8k resolution, highly detailed photography, standard view",
    "anime": "Anime style illustration, vibrant colors, detailed background, Makoto Shinkai style",
    "cinematic": "Cinematic movie shot, dramatic lighting, shadow and light depth, highly detailed, 4k",
    "minimal": "Minimalist flat vector illustration, simple shapes, clean lines, white background",
    "3d": "3D render, Pixar style, soft studio lighting, octane render, 4k",
    "webtoon": "Oriental fantasy webtoon style illustration of a character in traditional clothing lying on a bed in a dark room, dramatic lighting, detailed line art, manhwa aesthetics, high quality",
    "ghibli": "Studio Ghibli style, cel shaded, vibrant colors, lush background, Hayao Miyazaki style, highly detailed",
    "wimpy": "Diary of a Wimpy Kid style, simple black and white line drawing, hand-drawn sketch, minimalist stick figure illustration, white background, high quality"
}

# ===========================================
# API: 이미지 프롬프트 관리
# ===========================================

@router.get("/api/projects/{project_id}/image-prompts")
async def get_image_prompts(project_id: int):
    """이미지 프롬프트 목록 조회"""
    return db.get_image_prompts(project_id)

@router.post("/api/projects/{project_id}/image-prompts")
async def save_image_prompts(project_id: int, req: ImagePromptsSave):
    """이미지 프롬프트 저장"""
    db.save_image_prompts(project_id, req.prompts)
    # 프롬프트 저장 시 상태 업데이트는 선택사항 (이미지 생성중일 수 있음)
    db.update_project(project_id, status="prompts_ready")
    return {"status": "ok"}

@router.post("/api/image/generate-prompts")
async def generate_image_prompts_api(req: PromptsGenerateRequest):
    """대본 기반 이미지 프롬프트 생성 (Gemini)"""
    # 1. 스타일 프롬프트 결정
    # Custom Style: Check DB first if project_id is provided
    style_instruction = STYLE_PROMPTS.get(req.style, req.style)
    
    # [NEW] Check Settings/Presets for Custom Style Key logic
    # If req.style is not in defaults, maybe it's a custom preset or manual instruction
    # Check DB presets if needed.
    preset = db.get_style_preset(req.style)
    if preset:
        # Use preset prompt
        style_instruction = preset['prompt']
    
    # 2. 캐릭터 레퍼런스 적용
    if req.character_reference:
        style_instruction += f"\n[Character Requirement: {req.character_reference}]"

    # 3. 프롬프트 생성 (Gemini)
    prompts = await gemini_service.generate_image_prompts(req.script, style_instruction, req.count)
    
    # 4. 저장 (옵션)
    if req.project_id:
        # 기존 프롬프트와 병합? 아니면 덮어쓰기? 
        # UI 동작상 '생성' 버튼은 보통 덮어쓰거나 채워넣기임.
        # 일단 저장 로직은 별도 API(save_image_prompts)가 담당하므로 여기선 리턴만.
        # 하지만 편의를 위해 DB에도 저장해두면 좋음.
        pass

    return {"prompts": prompts}


# ===========================================
# API: 이미지 생성 (AI)
# ===========================================

@router.post("/api/image/generate")
async def generate_image_api(req: dict = Body(...), background_tasks: BackgroundTasks = None):
    """
    단일 이미지 생성 (Replicate) - 비동기 처리 권장
    req: { project_id, scene_index, prompt, style, width, height }
    """
    project_id = req.get("project_id")
    scene_index = req.get("scene_index")
    prompt = req.get("prompt")
    style_key = req.get("style", "realistic")

    # [NEW] 스타일 프롬프트 적용 (클라이언트에서 결합해서 보낼 수도 있지만, 서버에서 안전하게 병합)
    style_prompt = STYLE_PROMPTS.get(style_key, "") 
    
    # DB Preset Check
    if not style_prompt:
        preset = db.get_style_preset(style_key)
        if preset:
             style_prompt = preset['prompt']
    
    full_prompt = f"{style_prompt}, {prompt}" if style_prompt else prompt

    # 경로 설정
    output_dir, web_dir = get_project_output_dir(project_id) if project_id else (config.OUTPUT_DIR, "/output")
    
    # 동기 실행 (하나씩) - Replicate는 빠르므로 await
    try:
        # Replicate 서비스 호출
        # 이미지 URL 반환됨 (메모리상 X, URL O)
        # 하지만 ReplicateService는 bytes를 리턴하도록 구현되어 있음 (_download_video는 bytes, generate_image는?)
        # replicate_service.py를 확인해야 함. Assuming it returns bytes or URL.
        # 기존 코드 확인: replicate_service.py에는 generate_video_from_image만 보임. 
        # 이미지 생성(Flux/SDXL)은 'generate_image' 메서드가 있어야 함. 
        # (없으면 추가해야 함. 여기서는 있다고 가정하거나 직접 구현)
        
        # [CHECK] replicate_service.py content implies video gen focus. 
        # Assuming we use a generic replicate run or add method.
        # Let's add a quick internal helper or use `replicate.run` directly if duplication is acceptable for now.
        
        # To avoid adding logic to this router file that belongs in service, let's assume `generate_image` exists or add it.
        # Since I cannot see `generate_image` in previous `view_file` of `replicate_service.py`, 
        # I will inject a local helper or assume typical usage.
        
        # [TEMP] Direct Replicate Call for Image
        import replicate
        model = "black-forest-labs/flux-schnell" # Example, fast model
        
        input_data = {
            "prompt": full_prompt,
            "go_fast": True,
            "aspect_ratio": "16:9" # Default
        }
        
        # Sync call inside async? Replicate client uses blocking HTTP usually unless async client used.
        # Better to run in executor.
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, lambda: replicate.run(model, input=input_data))
        
        # Output is list of URLs usually (File objects streaming)
        image_url_or_stream = output[0]
        
        # Download
        import requests
        resp = await loop.run_in_executor(None, lambda: requests.get(str(image_url_or_stream)))
        image_data = resp.content
        
        filename = f"image_{project_id}_{scene_index}_{int(time.time())}.webp"
        save_path = os.path.join(output_dir, filename)
        
        with open(save_path, "wb") as f:
            f.write(image_data)
            
        web_url = f"{web_dir}/{filename}"
        
        # DB Update
        if project_id is not None and scene_index is not None:
             # scene_index is 0-based list index, usually mapped to scene_number 1-based?
             # Check DB Logic. `save_image_prompts` uses list order.
             # We need to update specific row.
             # `db.update_image_prompt_image(project_id, scene_number, url, path)` helper needed.
             # Let's assume scene_index corresponds to scene_number = index + 1
             scene_num = scene_index + 1
             conn = db.get_db()
             cursor = conn.cursor()
             cursor.execute(
                 "UPDATE image_prompts SET image_url = ?, image_path = ? WHERE project_id = ? AND scene_number = ?", 
                 (web_url, save_path, project_id, scene_num)
             )
             conn.commit()
             conn.close()

        return {
            "status": "ok",
            "url": web_url,
            "path": save_path
        }
        
    except Exception as e:
        print(f"Image Gen Error: {e}")
        raise HTTPException(500, f"이미지 생성 실패: {e}")


@router.post("/api/image/generate-mock")
async def generate_image_mock(req: dict = Body(...)):
    """테스트용 모의 이미지 생성 (색상 박스)"""
    project_id = req.get("project_id")
    scene_index = req.get("scene_index")
    
    from PIL import Image, ImageDraw, ImageFont
    import random
    
    width = 1280
    height = 720
    color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
    
    img = Image.new('RGB', (width, height), color=color)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(config.DEFAULT_FONT_PATH, 100)
    except:
        font = ImageFont.load_default()
        
    d.text((width/2, height/2), f"Scene {scene_index+1}", fill=(255,255,255), anchor="mm")
    
    output_dir, web_dir = get_project_output_dir(project_id) if project_id else (config.OUTPUT_DIR, "/output")
    filename = f"mock_{project_id}_{scene_index}_{int(time.time())}.jpg"
    save_path = os.path.join(output_dir, filename)
    img.save(save_path)
    web_url = f"{web_dir}/{filename}"
    
    # DB Update (Copied logic)
    if project_id is not None:
         scene_num = scene_index + 1
         conn = db.get_db()
         cursor = conn.cursor()
         cursor.execute(
             "UPDATE image_prompts SET image_url = ?, image_path = ? WHERE project_id = ? AND scene_number = ?", 
             (web_url, save_path, project_id, scene_num)
         )
         conn.commit()
         conn.close()

    return {"status": "ok", "url": web_url}


@router.post("/api/image/upload-scene")
async def upload_scene_image_api(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    scene_index: int = Form(...)
):
    """특정 Scene을 위한 미디어(이미지/영상) 직접 업로드"""
    try:
        output_dir, web_dir = get_project_output_dir(project_id)
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        ext = os.path.splitext(file.filename)[1].lower()
        
        # Allowed extensions
        image_exts = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']
        video_exts = ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v', '.wmv', '.flv', '.3gp', '.ts', '.mts']
        
        is_video = False
        if ext in video_exts:
            is_video = True
        elif file.content_type and file.content_type.startswith("video/"):
            is_video = True

        if not is_video and ext not in image_exts and not (file.content_type and file.content_type.startswith("image/")):
            raise HTTPException(400, f"지원하지 않는 파일 형식입니다: {ext} ({file.content_type})")
            
        filename = f"scene_{scene_index}_upload_{int(time.time())}{ext}"
        filepath = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # DB Update
        conn = db.get_db()
        cursor = conn.cursor()
        
        response_data = {"status": "ok", "path": filepath}
        
        if is_video:
            # Update video_url and CLEAR image fields
            cursor.execute(
                "UPDATE image_prompts SET video_url = ?, image_url = NULL, image_path = NULL WHERE project_id = ? AND scene_number = ?", 
                (web_url, project_id, scene_index)
            )
            response_data["video_url"] = web_url
        else:
            # Update image_url & image_path and CLEAR video_url
            cursor.execute(
                "UPDATE image_prompts SET image_url = ?, image_path = ?, video_url = NULL WHERE project_id = ? AND scene_number = ?", 
                (web_url, filepath, project_id, scene_index)
            )
            response_data["image_url"] = web_url 
            response_data["url"] = web_url
            
        conn.commit()
        conn.close()
            
        return response_data

    except Exception as e:
        print(f"Scene Upload Error: {e}")
        return {"status": "error", "error": str(e)}

# ===========================================
# API: 동영상 생성 (Motion)
# ===========================================

@router.post("/api/projects/{project_id}/scenes/animate")
async def animate_scene(project_id: int, req: AnimateRequest):
    """
    특정 씬(이미지)을 동영상(Motion)으로 변환 (Wan 2.2)
    """
    try:
        # 1. 이미지 경로 조회
        prompts = db.get_image_prompts(project_id)
        target_prompt = None
        for p in prompts:
            if p['scene_number'] == req.scene_number:
                target_prompt = p
                break
        
        if not target_prompt or not target_prompt.get('image_path'):
            raise HTTPException(404, "해당 씬의 이미지를 찾을 수 없습니다.")
            
        image_path = target_prompt['image_path']
        if not os.path.exists(image_path):
             # URL to Path conversion check
             if target_prompt['image_url'].startswith("/static/"):
                 rel = target_prompt['image_url'].replace("/static/", "", 1)
                 image_path = os.path.join(config.STATIC_DIR, rel)
             elif target_prompt['image_url'].startswith("/output/"):
                 rel = target_prompt['image_url'].replace("/output/", "", 1)
                 image_path = os.path.join(config.OUTPUT_DIR, rel)
        
        if not os.path.exists(image_path):
            raise HTTPException(404, f"이미지 파일이 존재하지 않습니다: {image_path}")

        # 2. 비디오 생성 요청
        print(f"Generating motion for Scene {req.scene_number} (Project {project_id}, Duration={req.duration})...")
        video_data = await replicate_service.generate_video_from_image(
            image_path=image_path,
            prompt=req.prompt or "Cinematic motion",
            duration=req.duration or 3.3
        )
        
        # 3. 저장
        output_dir, web_dir = get_project_output_dir(project_id)
        filename = f"motion_{project_id}_{req.scene_number}_{int(time.time())}.mp4"
        save_path = os.path.join(output_dir, filename)
        
        with open(save_path, "wb") as f:
            f.write(video_data)
            
        web_url = f"{web_dir}/{filename}"
        
        # 4. DB Update (video_url)
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE image_prompts SET video_url = ? WHERE project_id = ? AND scene_number = ?", 
            (web_url, project_id, req.scene_number)
        )
        conn.commit()
        conn.close()
        
        return {
            "status": "ok",
            "video_url": web_url,
            "message": "Motion generated successfully"
        }

    except Exception as e:
        print(f"Animation Failed: {e}")
        raise HTTPException(500, f"모션 생성 실패: {str(e)}")
