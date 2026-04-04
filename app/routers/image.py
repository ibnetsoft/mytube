"""
이미지 생성 라우터
/api/image/* 엔드포인트
"""
import os
import datetime
import aiofiles
from fastapi import APIRouter, Body, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time

import database as db
from config import config
from app.models.media import PromptsGenerateRequest
from app.utils import (
    validate_upload as _validate_upload,
    get_project_output_dir,
    ALLOWED_IMAGE_EXT as _ALLOWED_IMAGE_EXT,
    ALLOWED_VIDEO_EXT as _ALLOWED_VIDEO_EXT,
    MAX_IMAGE_SIZE as _MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE as _MAX_VIDEO_SIZE,
    STYLE_PROMPTS,
)
from services.gemini_service import gemini_service
from services.replicate_service import replicate_service
from services.akool_service import akool_service
from services.video_service import video_service

router = APIRouter(tags=["Image"])


class ImageGenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "9:16"  # 숏폼 전용 (9:16)


class ThumbnailTextRequest(BaseModel):
    """AI 썸네일 문구 생성 요청"""
    project_id: int
    thumbnail_style: str = "face"
    target_language: str = "ko"


class ThumbnailTextLayer(BaseModel):
    text: str
    position: str = "center" # top, center, bottom, custom
    y_offset: int = 0
    x_offset: int = 0
    font_family: str = "malgun"
    font_size: int = 72
    color: str = "#FFFFFF"
    stroke_color: Optional[str] = None
    stroke_width: int = 0
    bg_color: Optional[str] = None

class ThumbnailShapeLayer(BaseModel):
    x: int
    y: int
    width: int
    height: int
    color_start: str = "#000000"
    color_end: Optional[str] = None # 그라디언트 끝 색상 (없으면 단색)
    opacity: float = 1.0
    opacity_end: Optional[float] = None # 그라디언트 끝 투명도 (없으면 opacity와 동일)
    gradient_direction: str = "horizontal" # horizontal, vertical

class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    shape_layers: List[ThumbnailShapeLayer] = []
    text_layers: List[ThumbnailTextLayer] = []
    # Legacy support
    text: Optional[str] = None
    text_position: str = "center"
    text_color: str = "#FFFFFF"
    font_size: int = 72
    language: str = "ko"
    background_path: Optional[str] = None # 기존 이미지 사용 시 경로

class ThumbnailBackgroundRequest(BaseModel):
    prompt: str
    aspect_ratio: Optional[str] = "16:9"  # [NEW] Aspect Ratio
    thumbnail_style: Optional[str] = None # [NEW] Layout/Composition Reference
    project_id: Optional[int] = None # [NEW] Project reference for Style Inheritance

class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    layers: Optional[List[dict]] = None
    shape_layers: Optional[List[dict]] = None
    # Legacy support
    text: Optional[str] = None
    text_position: str = "center"
    text_color: str = "#FFFFFF"
    font_size: int = 72
    language: str = "ko"
    background_path: Optional[str] = None
    aspect_ratio: Optional[str] = "16:9"  # [NEW] Aspect Ratio



@router.post("/api/image/generate-prompts")
async def generate_image_prompts_api(req: PromptsGenerateRequest):
    """대본 기반 이미지 프롬프트 생성 (Unified API)"""
    try:
        # 1. Project Context & Duration Estimation
        duration = 60
        style_key = req.style
        characters = []

        character_ref_image_url = None
        if req.project_id:
            # Get latest script info
            p_data = db.get_script(req.project_id)
            if p_data:
                duration = p_data.get('estimated_duration', 60)

            # Get project settings (to resolve style key if generic)
            settings = db.get_project_settings(req.project_id)
            if settings:
                if not style_key:
                    style_key = settings.get('image_style', style_key)
                # 캐릭터 레퍼런스 이미지 경로 읽기 (여러 개면 첫 번째 사용)
                _ref_paths = settings.get('character_ref_image_path') or ''
                character_ref_image_url = _ref_paths.split(',')[0].strip() or None

            # Get existing characters for the project
            characters = db.get_project_characters(req.project_id)

        if not duration:
            duration = len(req.script) // 5 # very rough char count est

        # 2. Style Prompt Resolution (Key -> Description)
        db_presets = db.get_style_presets()
        style_key_lower = (style_key or '').lower()
        style_data = db_presets.get(style_key_lower)

        if style_data and isinstance(style_data, dict):
            style_prompt = style_data.get('prompt_value', style_key)
            gemini_instruction = style_data.get('gemini_instruction') or None
            # 캐릭터 시트 업로드 우선, 없으면 스타일 레퍼런스 이미지 사용
            reference_image_url = character_ref_image_url or style_data.get('image_url') or None
        else:
            style_prompt = STYLE_PROMPTS.get(style_key_lower, style_key or '')
            gemini_instruction = None
            reference_image_url = character_ref_image_url

        # 3. Call Gemini via Unified Service
        target_count = req.count if req.count and req.count > 0 else None

        # [사람 제외 등 추가 지시문] character_reference를 gemini_instruction에 합산
        if req.character_reference and req.character_reference.strip():
            extra = req.character_reference.strip()
            gemini_instruction = (gemini_instruction + "\n" + extra) if gemini_instruction else extra
            print(f"[Prompts] character_reference injected into gemini_instruction: {extra[:80]}...")

        print(f"[Prompts] Generating for Project {req.project_id}, Style: {style_key}, Target scenes: {target_count or 'auto'}, has_gemini_instruction: {bool(gemini_instruction)}, has_ref_image: {bool(reference_image_url)}")

        # [SAFETY] Truncate script to prevent Token Limit Exceeded / Timeout
        # 30000자로 늘림 (긴 대본도 전체 대사 포함)
        safe_script = req.script[:30000] if len(req.script) > 30000 else req.script
        if len(req.script) > 30000:
            print(f"[Prompts] Script truncated: {len(req.script)} → 30000 chars")

        prompts_list = await gemini_service.generate_image_prompts_from_script(
            safe_script,
            duration,
            style_prompt=style_prompt,
            characters=characters,
            target_scene_count=target_count,
            style_key=style_key,
            gemini_instruction=gemini_instruction,
            reference_image_url=reference_image_url
        )

        if not prompts_list:
            # Retry once if empty
            print("[Prompts] Empty result, retrying...")
            prompts_list = await gemini_service.generate_image_prompts_from_script(
                safe_script,
                duration,
                style_prompt=style_prompt,
                characters=characters,
                target_scene_count=target_count,
                style_key=style_key,
                gemini_instruction=gemini_instruction,
                reference_image_url=reference_image_url
            )

        if not prompts_list:
             raise HTTPException(500, "프롬프트 생성 실패 (AI 응답 오류)")

        # 4. Post-processing for UI consistency
        for p in prompts_list:
            # Ensure mandatory fields
            s_text = p.get('scene_text') or p.get('scene') or p.get('narrative') or ''
            p['scene_text'] = s_text
            
            if not p.get('scene_title'):
                p['scene_title'] = s_text[:15] + "..." if len(s_text) > 15 else f"Scene {p.get('scene_number', '?')}"
            
            # Ensure script bits exist
            if not p.get('script_start'):
                p['script_start'] = " ".join(s_text.split()[:2]) if s_text else ""
            if not p.get('script_end'):
                p['script_end'] = " ".join(s_text.split()[-2:]) if s_text else ""

            # Default empty states for UI
            if 'image_url' not in p: p['image_url'] = ""
            if 'image_path' not in p: p['image_path'] = ""

        # 5. [CRITICAL] DB에 실시간 저장 (UI에서 '적용' 버튼 누르기 전 미리 백업)
        if req.project_id:
            try:
                db.save_image_prompts(req.project_id, prompts_list)
                print(f"[Main] Auto-saved {len(prompts_list)} image prompts for project {req.project_id}")
            except Exception as e:
                print(f"[DB] Auto-save image prompts failed: {e}")

        return {"prompts": prompts_list}
        
    except Exception as e:
        print(f"Scene analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"분석 실패: {str(e)}")


@router.post("/api/projects/{project_id}/random-cooking")
async def generate_random_cooking_video(project_id: int):
    """랜덤 요리 선정 및 단계별 Veo 영상 자동 생성 (Shorts 전용)"""
    try:
        # 1. 대본 기반 길이 추정
        script_data = db.get_script(project_id)
        if not script_data or not script_data.get('full_script'):
            duration = 30 # Default 30s
        else:
            duration = script_data.get('estimated_duration', 30)
        
        # 5초당 1클립 계산
        num_clips = max(3, (duration + 4) // 5)
        print(f"[Cooking] Requested Project: {project_id}, Duration: {duration}s -> Clips: {num_clips}")
        
        # 2. 요리 계획 생성 (Gemini)
        plan = await gemini_service.generate_random_cooking_plan(count=num_clips)
        
        if not plan or not plan.get('steps'):
            return {"status": "error", "error": "요리 계획을 생성하지 못했습니다."}
        
        dish_name = plan.get('dish_name', '오늘의 요리')
        print(f"[Cooking] Selected Dish: {dish_name}")
        
        # 3. 단계별 영상 생성 (Veo)
        scenes = []
        output_abs, output_web = get_project_output_dir(project_id)
        
        # [주의] 여러 영상을 순차적으로 생성하므로 시간이 걸림 (타임아웃 주의)
        for i, step in enumerate(plan['steps']):
            print(f"[Cooking] Generating Clip {i+1}/{num_clips}: {step['action']}")
            
            # Veo API 호출 (dict 반환)
            import aiohttp
            veo_res = await gemini_service.generate_video(
                prompt=step['video_prompt'],
                aspect_ratio="9:16", # Shorts
                duration_seconds=5
            )
            
            video_bytes = None
            if veo_res and veo_res.get("status") == "ok":
                veo_uri = veo_res.get("video_url")
                async with aiohttp.ClientSession() as session:
                    async with session.get(veo_uri) as resp:
                        if resp.status == 200: video_bytes = await resp.read()
            
            video_url = ""
            if video_bytes:
                import time
                # 파일 저장
                filename = f"veo_cooking_{project_id}_{i+1}_{int(time.time())}.mp4"
                filepath = os.path.join(output_abs, filename)
                with open(filepath, "wb") as f:
                    f.write(video_bytes)
                video_url = f"{output_web}/{filename}"
                print(f"   -> Saved: {video_url}")
            else:
                print(f"   -> ⚠️ Clip generation failed for step {i+1}")
            
            scenes.append({
                "scene_number": i + 1,
                "scene_text": step['action'],
                "prompt_en": step['video_prompt'],
                "video_url": video_url,
                "image_url": "",
                "engine": "veo",
                "estimated_seconds": 5,
                "script_start": "", 
                "script_end": ""
            })
        
        # 4. DB 저장 (기존 프롬프트 대체)
        db.save_image_prompts(project_id, scenes)
        
        # 5. 프로젝트 설정 업데이트 (요리 이름 등 기록)
        db.update_project_setting(project_id, 'cooking_dish', dish_name)
        
        return {
            "status": "ok",
            "dish_name": dish_name,
            "description": plan.get('description', ''),
            "scenes": scenes
        }
    except Exception as e:
        import traceback, sys
        module_path = sys.modules[gemini_service.__class__.__module__].__file__
        err_msg = f"Random Cooking Error: {str(e)} (from: {module_path})\n{traceback.format_exc()}"
        print(err_msg)
        return {"status": "error", "error": str(e) + f" (gemini_service path: {module_path})"}


@router.post("/api/projects/{project_id}/image-prompts/auto")


@router.post("/api/image/generate-thumbnail-background")
async def generate_thumbnail_background(req: ThumbnailBackgroundRequest):
    """썸네일 배경 이미지만 생성 (텍스트 없음)"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        # 1. gemini-3.1-fast-image-preview로 배경 이미지 생성
        clean_prompt = req.prompt
        
        # [NEW] Style Inheritance architecture
        # 1. Art Style (from Project Settings)
        art_style_desc = ""
        if req.project_id:
            settings = db.get_project_settings(req.project_id)
            if settings:
                # Use image_style_prompt if available (this is the refined AI prompt)
                art_style_desc = settings.get('image_style_prompt') 
                if not art_style_desc and settings.get('image_style'):
                    # Fallback to fetching preset by key
                    presets = db.get_style_presets()
                    style_key = settings.get('image_style')
                    preset = presets.get(style_key)
                    if preset:
                        art_style_desc = preset.get('prompt_value')
        
        # 2. Layout/Composition Style (from Thumbnail Settings)
        layout_desc = ""
        if req.thumbnail_style:
            # 1. DB에서 스타일 설명 가져오기 (이제 레이아웃 중심)
            presets = db.get_thumbnail_style_presets() # Returns Dict[str, Dict]
            target_preset = presets.get(req.thumbnail_style)
            if target_preset:
                layout_desc = target_preset.get('prompt', '') # get_thumbnail_style_presets uses 'prompt' key
                print(f"[{req.thumbnail_style}] Using Layout preset description: {layout_desc}")
            
            # 2. 이미지 파일 분석 (있다면 추가/덮어쓰기)
            sample_img_dir = "static/thumbnail_samples"
            if os.path.exists(sample_img_dir):
                for f in os.listdir(sample_img_dir):
                    if f.startswith(req.thumbnail_style + '.'):
                        try:
                            with open(os.path.join(sample_img_dir, f), "rb") as img_f:
                                sample_img_bytes = img_f.read()
                            
                            print(f"[{req.thumbnail_style}] Analyzing sample image layout/style...")
                            analyze_prompt = "Describe the visual style, lighting, color palette, and composition of this image in 5 keywords for AI image generation. format: style1, style2, style3, ..."
                            vision_desc = await gemini_service.generate_text_from_image(analyze_prompt, sample_img_bytes)
                            layout_desc = f"{layout_desc}, {vision_desc}" if layout_desc else vision_desc
                            print(f"[{req.thumbnail_style}] Composition keywords from image: {vision_desc}")
                            break
                        except Exception as e:
                            print(f"Layout analysis failed: {e}")
                            pass
        
        final_style_components = []
        if art_style_desc:
            final_style_components.append(f"Visual Art Style: {art_style_desc}")
        if layout_desc:
            final_style_components.append(f"Composition & Layout: {layout_desc}")
        
        final_style_prefix = ". ".join(final_style_components) + ". " if final_style_components else ""

        # negative_constraints 강화
        negative_constraints = (
            "text, words, letters, alphabet, typography, watermark, signature, speech bubble, "
            "logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi, "
            "extra arms, multiple arms, four arms, too many arms, more than 2 arms, "
            "extra hands, too many hands, extra fingers, too many fingers, more than 10 fingers, "
            "additional limbs, additional arms, floating arms, disconnected arms, "
            "deformed arms, deformed hands, mutated arms, mutated hands, mutated fingers, "
            "fused arms, fused hands, fused fingers, wrong anatomy, bad anatomy, anatomical error, "
            "abnormal anatomy, disfigured, worst quality, low quality"
        )

        final_prompt = (
            f"ABSOLUTELY NO TEXT. CRITICAL ANATOMY RULES: EXACTLY TWO ARMS ONLY. EXACTLY TWO HANDS ONLY. "
            f"EXACTLY FIVE FINGERS PER HAND. PERFECT ANATOMICALLY CORRECT HUMAN BODY. "
            f"{final_style_prefix}{clean_prompt}. "
            f"High quality, 8k, YouTube thumbnail background, no watermark. DO NOT INCLUDE: {negative_constraints}."
        )

        # 이미지 생성 (전략: gemini_service (gemini-3.1-fast-image-preview))
        images_bytes = None
        
        try:
            print(f"🎨 [ThumbnailBG] Generating image using Gemini Service...")
            images_bytes = await gemini_service.generate_image(
                prompt=final_prompt,
                num_images=1,
                aspect_ratio=req.aspect_ratio
            )
        except Exception as e:
            print(f"⚠️ [ThumbnailBG] Gemini generation failed: {e}")
            return {"status": "error", "error": f"이미지 생성 실패: {str(e)}"}

        if not images_bytes:
            return {"status": "error", "error": "이미지 생성 결과가 없습니다."}
        
        # 2. 이미지 저장 (raw bytes → 파일)
        save_dir = "static/img/thumbnails"
        os.makedirs(save_dir, exist_ok=True)

        filename = f"bg_{uuid.uuid4().hex}.png"
        filepath = os.path.join(save_dir, filename)

        async with aiofiles.open(filepath, "wb") as f:
            f.write(images_bytes[0])
        
        # URL 및 절대 경로 반환
        return {
            "status": "ok",
            "url": f"/static/img/thumbnails/{filename}",
            "path": os.path.abspath(filepath)
        }

    except Exception as e:
        print(f"Error generating background: {e}")
        return {"status": "error", "error": str(e)}

@router.post("/api/projects/{project_id}/thumbnail/save")


@router.post("/api/image/generate-thumbnail")
async def generate_thumbnail(req: ThumbnailGenerateRequest):
    """썸네일 생성 (이미지 + 텍스트 합성)"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        import platform # Import platform for OS detection
        import re # Import regex

        # If background_path is provided, use it. Otherwise, generate new image.
        img = None
        
        # [NEW] Dynamic Resolution
        target_size = (1280, 720) # Default 16:9
        if req.aspect_ratio == "9:16":
            target_size = (720, 1280)
        
        if req.background_path and os.path.exists(req.background_path):
            # 기존 이미지 로드
            try:
                img = Image.open(req.background_path)
                img = img.resize(target_size, Image.LANCZOS)
                print(f"Loaded background from: {req.background_path} (Resize: {target_size})")
            except Exception as e:
                pass

        if img is None: # If no bg or failed to load, generate
            # [MODIFIED] 통일된 gemini_service 사용 (hardcoded model 적용됨)
            clean_prompt = req.prompt
            negative_constraints = "text, words, letters, alphabet, typography, watermark, signature, speech bubble, logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi"
            
            final_prompt = f"ABSOLUTELY NO TEXT. NO CHINESE/JAPANESE/KOREAN CHARACTERS. {clean_prompt}. High quality, 8k, detailed, YouTube thumbnail background, empty background, no watermark. DO NOT INCLUDE: {negative_constraints}. INVISIBLE TEXT."
            
            try:
                print(f"🎨 [ThumbnailGen] Generating background via gemini_service...")
                images_bytes = await gemini_service.generate_image(
                    prompt=final_prompt,
                    num_images=1,
                    aspect_ratio=req.aspect_ratio or "16:9"
                )
                
                if images_bytes:
                    img = Image.open(io.BytesIO(images_bytes[0]))
                    img = img.resize(target_size, Image.LANCZOS)
                else:
                    return {"status": "error", "error": "배경 이미지 생성 실패 (No data)"}
                    
            except Exception as e:
                print(f"❌ [ThumbnailGen] Generation Error: {e}")
                return {"status": "error", "error": f"배경 생성 실패: {str(e)}"}


        # 3. 텍스트 오버레이

        # 3. 도형 및 텍스트 오버레이

        # Helper: 그라디언트 사각형 그리기 (Alpha Interpolation 지원)
        def draw_gradient_rect(draw, img, x, y, w, h, start_color, end_color, direction="horizontal", start_opacity=1.0, end_opacity=None):
            if end_opacity is None:
                end_opacity = start_opacity

            # PIL Draw는 그라디언트 미지원 -> 이미지 합성으로 처리
            # 1. 그라디언트 마스크 생성
            base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw_base = ImageDraw.Draw(base)
            
            # 색상 파싱
            from PIL import ImageColor
            c1 = ImageColor.getrgb(start_color)
            c2 = ImageColor.getrgb(end_color) if end_color else c1
            
            # Alpha 값 (0-255 scaling)
            a1 = int(255 * start_opacity)
            a2 = int(255 * end_opacity)

            if not end_color or (start_color == end_color and start_opacity == end_opacity):
                # 단색 (색상도 같고 투명도도 같을 때)
                draw_base.rectangle([(0, 0), (w, h)], fill=c1 + (a1,))
            else:
                # 그라디언트 (색상 OR 투명도가 다를 때)
                for i in range(w if direction == 'horizontal' else h):
                    ratio = i / float((w if direction == 'horizontal' else h))
                    
                    # RGB Interpolation
                    r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
                    g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
                    b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
                    
                    # Alpha Interpolation
                    a = int(a1 * (1 - ratio) + a2 * ratio)
                    
                    if direction == 'horizontal':
                        draw_base.line([(i, 0), (i, h)], fill=(r, g, b, a))
                    else:
                        draw_base.line([(0, i), (w, i)], fill=(r, g, b, a))
            
            # 원본 이미지에 합성
            img.paste(base, (x, y), base)

        # 3.1 도형 렌더링 (텍스트보다 뒤에)
        if hasattr(req, 'shape_layers') and req.shape_layers:
            draw = ImageDraw.Draw(img) # Draw 객체 생성 (단색은 직접 그리지만 그라디언트는 paste 사용)
            for shape in req.shape_layers:
                draw_gradient_rect(
                    draw, img, 
                    shape.x, shape.y, shape.width, shape.height,
                    shape.color_start, shape.color_end,
                    shape.gradient_direction, 
                    start_opacity=shape.opacity,
                    end_opacity=shape.opacity_end
                )

        # 3.2 텍스트 오버레이
        draw = ImageDraw.Draw(img)
        system = platform.system()

        # 레거시 요청을 새로운 형식으로 변환
        layers = req.text_layers
        if not layers and req.text:
            layers = [ThumbnailTextLayer(
                text=req.text,
                position=req.text_position,
                color=req.text_color,
                font_size=req.font_size
            )]

        for layer in layers:
            # 폰트 결정 (static/fonts 우선 탐색)
            font_candidates = []
            
            # [Smart Fix] 일본어/한자 포함 여부 확인 (Gmarket Sans는 한자 미지원)
            has_japanese = bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', layer.text))
            
            # 1. 프로젝트 내 폰트
            if layer.font_family == "gmarket":
                if has_japanese:
                    # Gmarket 요청이지만 일본어가 있으면 -> 윈도우용 굵은 일본어 폰트 파일명으로 대체
                    # Meiryo Bold, Malgun Gothic Bold, Yu Gothic Bold
                    font_candidates.extend(["meiryob.ttc", "malgunbd.ttf", "YuGothB.ttc", "msgothic.ttc"])
                    print(f"[Thumbnail] 'gmarket' requested but Japanese text detected. Fallback to System Bold font filenames.")
                else:
                    font_candidates.extend(["static/fonts/GmarketSansBold.woff", "static/fonts/GmarketSansBold.ttf", "GmarketSansBold.otf"])
            elif layer.font_family == "cookie":
                 # 쿠키런도 한자 지원이 제한적일 수 있음 -> 필요시 유사 로직 추가
                font_candidates.extend(["static/fonts/CookieRun-Regular.woff", "static/fonts/CookieRun-Regular.ttf", "CookieRun-Regular.ttf"])
            
            # 2. 시스템 폰트 Fallback
            if system == 'Windows':
                # Meiryo(일본어), Malgun(한국어) 순서
                font_candidates.extend(["meiryo.ttc", "meiryob.ttc", "malgunbd.ttf", "malgun.ttf", "gulim.ttc", "arial.ttf"])
            else:
                font_candidates.extend(["AppleGothic.ttf", "NotoSansCJK-Bold.ttc", "Arial.ttf"])

            font = None
            for font_file in font_candidates:
                # 1. 절대/상대 경로 직접 확인
                if os.path.exists(font_file):
                    try:
                        font = ImageFont.truetype(font_file, layer.font_size)
                        print(f"[Thumbnail] Loaded font: {font_file}")
                        break
                    except Exception as e:
                        print(f"[Thumbnail] Font load error ({font_file}): {e}")
                        continue
                
                # 2. Windows Fonts 폴더 확인
                if system == 'Windows':
                    win_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', font_file)
                    if os.path.exists(win_path):
                        try:
                            font = ImageFont.truetype(win_path, layer.font_size)
                            break
                        except Exception: continue

            if not font:
                font = ImageFont.load_default()

            # 텍스트 크기 계산 (Bbox)
            bbox = draw.textbbox((0, 0), layer.text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            # X 위치 (중앙 정렬 기반) + X 오프셋 적용
            x = (1280 - tw) // 2 + layer.x_offset
            
            # Y 위치 (720p 기준 5분할 강조) - [FIX] 하단 여백 확보
            if layer.position == "row1" or layer.position == "top":
                y = 60 + layer.y_offset
            elif layer.position == "row2":
                y = 190 + layer.y_offset
            elif layer.position == "row3":
                y = 320 + layer.y_offset
            elif layer.position == "row4":
                y = 450 + layer.y_offset
            elif layer.position == "row5" or layer.position == "bottom":
                y = 550 + layer.y_offset # [FIX] 580 -> 550 (바닥 붙음 방지)
            else: # center
                y = (720 - th) // 2 + layer.y_offset

            # 1. 배경 박스 (Highlights) - 텍스트 아래에 그려야 함
            if layer.bg_color:
                padding_x = 15
                padding_y = 10
                draw.rectangle(
                    [x - padding_x, y - padding_y, x + tw + padding_x, y + th + padding_y],
                    fill=layer.bg_color
                )

            # 2. 외곽선 (Strokes)
            if layer.stroke_color and layer.stroke_width > 0:
                for ox in range(-layer.stroke_width, layer.stroke_width + 1):
                    for oy in range(-layer.stroke_width, layer.stroke_width + 1):
                        draw.text((x + ox, y + oy), layer.text, font=font, fill=layer.stroke_color)

            # 3. 텍스트 그림자 (Stroke가 없을 때 가독성용)
            elif not layer.stroke_color:
                draw.text((x + 2, y + 2), layer.text, font=font, fill="#000000")

            # 4. 본문 텍스트 생성 (가장 위에 그려야 함)
            draw.text((x, y), layer.text, font=font, fill=layer.color)

        # 4. 저장
        now_kst = config.get_kst_time()
        filename = f"thumbnail_{now_kst.strftime('%Y%m%d_%H%M%S')}.png"
        
        output_dir = os.path.join(config.OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, filename)
        img.save(output_path)

        web_url = f"/output/{filename}"
        return {"status": "ok", "url": web_url}

    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"서버 오류: {str(e)}"}



@router.get("/api/trends/keywords")


@router.post("/api/image/analyze-character")
async def analyze_character(
    file: Optional[UploadFile] = File(None),
    image_path: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None) # [NEW] Persistence support
):
    try:
        image_bytes = None
        saved_image_url = None
        
        # 1. Check Uploaded File
        if file:
            image_bytes = await file.read()
            # [NEW] Save file for persistence if project_id provided
            if project_id and image_bytes:
                try:
                    save_dir = f"static/project_data/{project_id}"
                    os.makedirs(save_dir, exist_ok=True)
                    ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
                    filename = f"char_ref_{int(datetime.datetime.now().timestamp())}.{ext}"
                    filepath = os.path.join(save_dir, filename)
                    async with aiofiles.open(filepath, "wb") as f:
                        await f.write(image_bytes)
                    saved_image_url = f"/{save_dir.replace(os.sep, '/')}/{filename}"
                    print(f"Saved character ref to {saved_image_url}")
                except Exception as e:
                    print(f"Failed to save character ref image: {e}")
            
        # 2. Check Local Path (Thumbnail fallback)
        elif image_path:
            saved_image_url = image_path # Reuse provided path
            # Basic path validation
            if os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            else:
                 # Check relative path from current dir
                 rel_path = image_path.lstrip("/").replace("/", os.sep)
                 if os.path.exists(rel_path):
                     with open(rel_path, "rb") as f:
                         image_bytes = f.read()
        
        if not image_bytes:
             return JSONResponse(status_code=400, content={"error": "Image file or valid path required"})

        # 3. Vision Analysis
        # 3. Vision Analysis
        prompt = """
        Analyze this image and provide a highly detailed, identity-focused description of the main character (or subject). 
        
        [CRITICAL REQUIREMENT]
        YOU MUST EXPLICITLY STATE THE RACE / ETHNICITY / NATIONALITY of the person (e.g., "Korean woman", "Japanese man", "Caucasian female"). 
        DO NOT leave this ambiguous. If they look East Asian, say "East Asian" or specific nationality if apparent.
        
        Capture specific facial features (eye shape, nose structure, jawline), exact hair texture/color/style, skin tone, and body proportions.
        Describe the clothing and accessories in detail.
        The goal is to generate a new image of the SAME person in a different setting, so the description must be specific enough to preserve identity.
        Output ONLY the description text. Start with "(Character Reference) A photo of...".
        """
        
        description = await gemini_service.generate_text_from_image(prompt, image_bytes)
        
        return {"description": description.strip(), "image_url": saved_image_url}
        
    except Exception as e:
        print(f"Analyze character failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

class CharacterPromptRequest(BaseModel):
    script: str
    project_id: Optional[int] = None
    style: Optional[str] = "realistic"


@router.post("/api/image/character-prompts")


@router.post("/api/image/character-prompts")
async def generate_character_prompts(req: CharacterPromptRequest):
    """대본 기반 캐릭터 프롬프트 생성"""
    try:
        # [Manual Mode] Always re-analyze when requested via API
        # (Skip logic removed to allow style-consistent re-extraction)


        # [NEW] 비주얼 스타일 결정 (프롬프트 반영)
        db_presets = db.get_style_presets()
        style_prefix = "photorealistic"
        
        if req.style:
            style_data = db_presets.get(req.style.lower())
            if isinstance(style_data, dict):
                style_prefix = style_data.get("prompt_value", req.style)
            else:
                style_prefix = STYLE_PROMPTS.get(req.style.lower(), req.style)
        elif req.project_id:
            # 프로젝트 설정에서 스타일 조회
            settings = db.get_project_settings(req.project_id)
            if settings and settings.get('image_style'):
                image_style_key = settings['image_style'].lower()
                style_data = db_presets.get(image_style_key)
                if isinstance(style_data, dict):
                    style_prefix = style_data.get("prompt_value", image_style_key)
                else:
                    style_prefix = STYLE_PROMPTS.get(image_style_key, image_style_key)

        print(f"👥 [Main] 캐릭터 분석 시작... (Style: {style_prefix})")
        characters = await gemini_service.generate_character_prompts_from_script(req.script, visual_style=style_prefix)

        
        # [NEW] DB 저장
        if req.project_id:
            try:
                db.save_project_characters(req.project_id, characters)
                print(f"[Main] Saved {len(characters)} characters to DB for project {req.project_id}")
            except Exception as db_err:
                print(f"[Main] Failed to save characters: {db_err}")
        
        return {"status": "ok", "characters": characters}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Character prompts generation failed: {e}\n{error_trace}")
        return {"status": "error", "error": f"{str(e)}", "trace": error_trace}


@router.post("/api/projects/{project_id}/characters")
async def save_characters(project_id: int, characters: List[Dict] = Body(...)):
    """캐릭터 목록 저장 (삭제 포함)"""
    try:
        db.save_project_characters(project_id, characters)
        return {"status": "ok", "count": len(characters)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/api/projects/{project_id}/characters")
async def get_characters(project_id: int):
    """캐릭터 목록 조회"""
    try:
        characters = db.get_project_characters(project_id)
        return {"status": "ok", "characters": characters}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# duplicate endpoint removed
@router.post("/api/image/generate-character")


@router.post("/api/image/generate-character")
async def generate_character_image(
    prompt: str = Body(...),
    project_id: int = Body(...),
    style: str = Body("realistic"),
    name: Optional[str] = Body(None)
):
    """캐릭터 이미지를 생성하고 저장 (Character Reference용)"""
    try:
        # [NEW] DB 스타일 프리셋 조회
        db_presets = db.get_style_presets()
        style_data = db_presets.get(style.lower())
        if isinstance(style_data, dict):
            detailed_style = style_data.get("prompt_value", STYLE_PROMPTS.get(style.lower(), style))
        else:
            detailed_style = STYLE_PROMPTS.get(style.lower(), style)
        
        full_prompt = f"{prompt}, {detailed_style}"
        
        print(f"👤 [Char Generation] Style: {style}, Prompt: {prompt[:100]}...")

        # 이미지 생성 (전략: Gemini (Primary) -> Replicate -> AKOOL Fallback)
        images_bytes = None
        
        # 1차 시도: Gemini (gemini-3.1-fast-image-preview)
        try:
            print(f"🎨 [Char Generation] Attempting Gemini (Primary)...")
            images_bytes = await gemini_service.generate_image(
                prompt=full_prompt,
                num_images=1,
                aspect_ratio="1:1"
            )
        except Exception as e:
            print(f"⚠️ [Char Generation] Gemini failed: {e}")

        # 2차 시도: Replicate (flux-schnell)
        if not images_bytes:
            try:
                print(f"🎨 [Char Generation] Attempting Replicate (Fallback 1)...")
                images_bytes = await replicate_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
            except Exception as e:
                print(f"⚠️ [Char Generation] Replicate failed: {e}")

        # 3차 시도: AKOOL (Final Fallback)
        if not images_bytes:
            try:
                print(f"🎨 [Char Generation] Attempting AKOOL (Final Fallback)...")
                images_bytes = await akool_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
            except Exception as e:
                print(f"⚠️ [Char Generation] AKOOL failed: {e}")

        if not images_bytes:
            return {"status": "error", "error": "모든 이미지 생성 서비스가 실패했습니다."}
        
        output_dir, web_dir = get_project_output_dir(project_id)
        filename = f"char_{project_id}_{int(datetime.datetime.now().timestamp())}.png"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"

        async with aiofiles.open(file_path, "wb") as f:
            f.write(images_bytes[0])
            
        print(f"✅ [Char Generation] Saved to {web_url}")
        
        # [NEW] DB 업데이트
        if name:
            try:
                db.update_character_image(project_id, name, web_url)
                print(f"[DB] Updated character image for {name}")
            except Exception as dbe:
                print(f"[DB] Failed to update character image: {dbe}")
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"❌ [Char Generation] Error: {e}")
        return {"status": "error", "error": str(e)}



@router.post("/api/image/generate-motion-from-image")


@router.post("/api/image/generate-motion-from-image")
async def generate_motion_from_image(
    project_id: int = Body(...),
    scene_numbers: list = Body(...)   # 선택된 씬 번호 목록
):
    """생성된 이미지를 Gemini Vision으로 분석해 motion_desc 생성"""
    try:
        scene_prompts = db.get_image_prompts(project_id)
        if not scene_prompts:
            return {"status": "error", "error": "프롬프트가 없습니다."}

        targets = [p for p in scene_prompts if p.get('scene_number') in scene_numbers]
        if not targets:
            return {"status": "error", "error": "선택된 씬을 찾을 수 없습니다."}

        results = []
        errors = []

        for scene in targets:
            scene_num = scene.get('scene_number')
            image_url = scene.get('image_url') or ''
            scene_text = scene.get('scene_text') or scene.get('prompt_ko') or ''

            if not image_url:
                errors.append({"scene_number": scene_num, "error": "이미지가 없습니다. 먼저 이미지를 생성하세요."})
                continue

            # URL → 절대 경로 변환
            image_path = None
            if image_url.startswith("/static/"):
                rel = image_url.replace("/static/", "", 1).replace("/", os.sep)
                image_path = os.path.join(config.STATIC_DIR, rel)
            elif image_url.startswith("/output/"):
                rel = image_url.replace("/output/", "", 1).replace("/", os.sep)
                image_path = os.path.join(config.OUTPUT_DIR, rel)

            if not image_path or not os.path.exists(image_path):
                errors.append({"scene_number": scene_num, "error": f"이미지 파일을 찾을 수 없습니다: {image_url}"})
                continue

            try:
                print(f"🔍 [ImageMotion] Analyzing image for scene {scene_num}: {image_path}")
                motion = await gemini_service.generate_motion_desc_from_image(
                    image_path=image_path,
                    scene_text=scene_text
                )
                # DB 저장
                conn = db.get_db()
                conn.execute(
                    "UPDATE image_prompts SET motion_desc = ? WHERE project_id = ? AND scene_number = ?",
                    (motion, project_id, scene_num)
                )
                conn.commit()
                conn.close()

                results.append({"scene_number": scene_num, "motion_desc": motion})
                print(f"  ✅ Scene {scene_num}: {motion}")

            except Exception as e:
                print(f"  ❌ Scene {scene_num} vision failed: {e}")
                errors.append({"scene_number": scene_num, "error": str(e)})

        return {
            "status": "ok",
            "generated": len(results),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/api/image/bulk-generate-motion")


@router.post("/api/image/bulk-generate-motion")
async def bulk_generate_motion(
    project_id: int = Body(...),
    max_scene: int = Body(5),        # 1~max_scene 씬까지 생성
    scene_numbers: list = Body(None) # 특정 씬만 지정 시 (없으면 1~max_scene)
):
    """씬 목록의 motion_desc(영상 모션 프롬프트)를 Gemini AI로 일괄 자동 생성"""
    try:
        scene_prompts = db.get_image_prompts(project_id)
        if not scene_prompts:
            return {"status": "error", "error": "프롬프트가 없습니다. 먼저 이미지 프롬프트를 생성해주세요."}

        # 대상 씬 결정
        if scene_numbers:
            targets = [p for p in scene_prompts if p.get('scene_number') in scene_numbers]
        else:
            targets = [p for p in scene_prompts if p.get('scene_number', 0) <= max_scene]

        if not targets:
            return {"status": "error", "error": f"씬 1~{max_scene} 범위에 데이터가 없습니다."}

        results = []
        errors = []

        for scene in targets:
            scene_num = scene.get('scene_number')
            scene_text = scene.get('scene_text') or scene.get('prompt_ko') or ''
            prompt_en  = scene.get('prompt_en') or ''

            try:
                print(f"🎬 [MotionGen] Generating motion_desc for scene {scene_num}...")
                motion = await gemini_service.generate_motion_desc(
                    scene_text=scene_text,
                    prompt_en=prompt_en
                )
                # DB 저장
                conn = db.get_db()
                conn.execute(
                    "UPDATE image_prompts SET motion_desc = ? WHERE project_id = ? AND scene_number = ?",
                    (motion, project_id, scene_num)
                )
                conn.commit()
                conn.close()

                results.append({"scene_number": scene_num, "motion_desc": motion})
                print(f"  ✅ Scene {scene_num}: {motion}")

            except Exception as e:
                print(f"  ❌ Scene {scene_num} failed: {e}")
                errors.append({"scene_number": scene_num, "error": str(e)})

        return {
            "status": "ok",
            "generated": len(results),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/api/image/generate")


@router.post("/api/image/generate")
async def generate_image(
    prompt: str = Body(...),
    project_id: int = Body(...),
    scene_number: int = Body(1),
    style: str = Body("realistic"),
    aspect_ratio: str = Body("16:9"),
    no_human: bool = Body(False)
):
    """이미지를 생성하고 저장"""
    try:
        # Validate prompt
        if not prompt or not prompt.strip():
            print(f"❌ [Image Generation] Empty prompt for project {project_id}, scene {scene_number}")
            return {"status": "error", "error": "프롬프트가 비어있습니다. 먼저 프롬프트를 생성해주세요."}

        if len(prompt) > 5000:
            print(f"⚠️ [Image Generation] Prompt too long ({len(prompt)} chars), truncating...")
            prompt = prompt[:5000]

        # [사람 제외] 프롬프트에서 인물 묘사 제거 + 배경/환경 중심으로 변환
        no_human_negative = None
        if no_human:
            import re as _re
            # 인물 관련 단어 제거
            human_pattern = _re.compile(
                r'\b(man|woman|person|people|human|figure|character|face|hands?|arms?|body|'
                r'boy|girl|male|female|he|she|him|her|his|their|wearing|dressed|smiling|'
                r'waving|standing|sitting|holding|looking|pointing|showing|남성|여성|남자|여자|'
                r'사람|인물|인간|얼굴|손|팔|몸|그가|그녀|모델)\b',
                _re.IGNORECASE
            )
            prompt = human_pattern.sub('', prompt)
            prompt = _re.sub(r'\s{2,}', ' ', prompt).strip()
            # 환경/배경 중심 지시어 추가
            prompt = ("A scene with absolutely no humans or people. Environment and objects only. "
                      + prompt +
                      " No person, no human figure, no face, no body parts visible. Pure background scene.")
            no_human_negative = "human, person, people, man, woman, face, hands, body, figure, character"
            print(f"🚫 [No Human Mode] Modified prompt: {prompt[:100]}...")

        print(f"🎨 [Image Generation] Starting for project {project_id}, scene {scene_number}")
        print(f"   Prompt: {prompt[:100]}...")
        print(f"   Aspect ratio: {aspect_ratio}")

        # 이미지 생성 전략
        images_bytes = None

        # DB에서 스타일 prefix 가져오기
        _style_settings = db.get_style_presets().get(style.lower(), {}) if style else {}
        _style_prefix = (_style_settings.get('prompt_value') or STYLE_PROMPTS.get(style.lower(), '')).strip()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # [2-PROMPT COMPOSITE MODE] prompt_char + prompt_bg가 있으면 분리 생성 후 합성
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # DB에서 해당 씬의 prompt_char, prompt_bg 조회
        scene_prompts = db.get_image_prompts(project_id)
        scene_data = next((s for s in scene_prompts if s.get('scene_number') == scene_number), None)
        prompt_char = scene_data.get('prompt_char', '') if scene_data else ''
        prompt_bg = scene_data.get('prompt_bg', '') if scene_data else ''

        if prompt_char and prompt_bg:
            print(f"🎨 [Image Gen] COMPOSITE mode — generating character + background separately...")

            async def _generate_single(p: str) -> bytes | None:
                """단일 프롬프트로 이미지 생성 (Gemini -> Replicate -> AKOOL 폴백)"""
                result = None
                # 1. Gemini (Primary)
                try:
                    result = await gemini_service.generate_image(prompt=p, num_images=1, aspect_ratio="1:1")
                except Exception as e:
                    print(f"⚠️ [Composite] Gemini failed: {e}")
                
                # 2. Replicate (Fallback)
                if not result:
                    try:
                        result = await replicate_service.generate_image(prompt=p, aspect_ratio="1:1")
                    except Exception as e:
                        print(f"⚠️ [Composite] Replicate failed: {e}")
                
                # 3. AKOOL (Final Fallback)
                if not result:
                    try:
                        result = await akool_service.generate_image(prompt=p, aspect_ratio="1:1")
                    except Exception as e:
                        print(f"⚠️ [Composite] AKOOL failed: {e}")
                return result[0] if result else None

            # 캐릭터 이미지 생성
            char_bytes = await _generate_single(prompt_char)
            # 배경 이미지 생성
            bg_bytes = await _generate_single(prompt_bg)

            if char_bytes and bg_bytes:
                print(f"✅ [Composite] Both images generated — compositing...")
                try:
                    composite_bytes = video_service.composite_character_on_background(
                        char_bytes=char_bytes,
                        bg_bytes=bg_bytes,
                        aspect_ratio=aspect_ratio,
                    )
                    images_bytes = [composite_bytes]
                    print(f"✅ [Composite] Compositing complete, size: {len(composite_bytes)} bytes")
                except Exception as e:
                    print(f"⚠️ [Composite] Compositing failed: {e} — falling back to single-prompt mode")
                    images_bytes = None
            else:
                print(f"⚠️ [Composite] Image generation partially failed (char={bool(char_bytes)}, bg={bool(bg_bytes)}) — falling back to single-prompt mode")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # [SINGLE-PROMPT MODE] 기본 단일 프롬프트 생성 (또는 합성 실패 시 폴백)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 스타일 prefix가 프롬프트에 없으면 앞에 추가
        if _style_prefix and _style_prefix[:40].lower() not in prompt.lower():
            effective_prompt = _style_prefix + ', ' + prompt
        else:
            effective_prompt = prompt


        if not images_bytes:
            print(f"🎨 [Image Gen] Attempting Gemini (Primary)...")
            try:
                images_bytes = await gemini_service.generate_image(
                    prompt=effective_prompt,
                    num_images=1,
                    aspect_ratio=aspect_ratio
                )
            except Exception as e:
                print(f"⚠️ [Image Gen] Gemini failed: {e}")

        # Fallback 1: Replicate
        if not images_bytes:
            try:
                print(f"🎨 [Image Gen] Attempting Replicate (Fallback 1)...")
                images_bytes = await replicate_service.generate_image(
                    prompt=effective_prompt,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=no_human_negative
                )
            except Exception as e:
                print(f"⚠️ [Image Gen] Replicate failed: {e}")

        # 최종 폴백: AKOOL
        if not images_bytes:
            try:
                print(f"🎨 [Image Gen] Attempting AKOOL (Final Fallback)...")
                images_bytes = await akool_service.generate_image(prompt=effective_prompt, aspect_ratio=aspect_ratio)
            except Exception as e:
                print(f"⚠️ [Image Gen] AKOOL failed: {e}")

        if not images_bytes:
            return {"status": "error", "error": "모든 이미지 생성 서비스가 실패했습니다."}
        
        print(f"✅ [Image Generation] Successfully generated image, size: {len(images_bytes[0])} bytes")
        
        # 프로젝트별 폴더 경로 가져오기
        output_dir, web_dir = get_project_output_dir(project_id)
        
        filename = f"p{project_id}_s{scene_number}_{int(datetime.datetime.now().timestamp())}.png"
        output_path = os.path.join(output_dir, filename)
        
        # 파일 저장
        async with aiofiles.open(output_path, "wb") as f:
            await f.write(images_bytes[0])

        # [숏츠 Letterbox] 3:4 또는 1:1 비율이면 9:16 캔버스에 합성 (위아래 검정 패딩)
        print(f"📐 [Letterbox] aspect_ratio={aspect_ratio!r}, will_apply={aspect_ratio in ('3:4','1:1')}")
        if aspect_ratio in ("3:4", "1:1"):
            try:
                from PIL import Image as PILImage
                TARGET_W, TARGET_H = 1080, 1920  # 9:16 최종 해상도
                # with 블록 밖에서 저장해야 Windows에서 파일 잠금 문제 없음
                src = PILImage.open(output_path)
                orig_w, orig_h = src.size
                print(f"📐 [Letterbox] Source image: {orig_w}x{orig_h}")
                src = src.convert("RGBA")
                scale = TARGET_W / orig_w
                new_w = TARGET_W
                new_h = int(orig_h * scale)
                src_resized = src.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                src.close()
                canvas = PILImage.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 255))
                paste_y = (TARGET_H - new_h) // 2
                canvas.paste(src_resized, (0, paste_y))
                canvas.convert("RGB").save(output_path, "PNG")
                print(f"📐 [Letterbox] Done: image_w={new_w}, image_h={new_h}, top_pad={paste_y}px")
            except Exception as lb_err:
                print(f"⚠️ [Letterbox] Failed: {lb_err}")
                import traceback; traceback.print_exc()

        print(f"💾 [Image Generation] Saved to: {output_path}")
            
        image_url = f"{web_dir}/{filename}"
        
        # DB 업데이트 (이미지 URL 저장)
        print(f"💿 [Image Generation] Updating DB for Project {project_id}, Scene {scene_number} with URL {image_url}")
        db.update_image_prompt_url(project_id, scene_number, image_url)
        
        return {
            "status": "ok",
            "image_url": image_url
        }

    except Exception as e:
        error_details = f"이미지 생성 실패: {str(e)}"
        print(f"❌ [Image Generation] {error_details}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": error_details}


@router.post("/api/image/upload-scene")
async def upload_scene_media(
    project_id: int = Form(...),
    scene_number: int = Form(...),
    file: UploadFile = File(...)
):
    """
    장면의 이미지 또는 비디오를 직접 업로드하여 교체합니다. (Frontend 'uploadSceneImage' 대응)
    """
    try:
        from app.utils import get_project_output_dir, ALLOWED_IMAGE_EXT, ALLOWED_VIDEO_EXT
        
        # 파일 타입 확인
        ext = os.path.splitext(file.filename)[1].lower()
        is_video = ext in ALLOWED_VIDEO_EXT
        is_image = ext in ALLOWED_IMAGE_EXT
        
        if not (is_video or is_image):
             raise HTTPException(400, f"지원하지 않는 형식입니다: {ext}")
        
        # 프로젝트 폴더 가져오기
        abs_dir, web_dir = get_project_output_dir(project_id)
        
        # 저장 파일명 결정
        prefix = "manual_vid" if is_video else "manual_img"
        timestamp = int(datetime.datetime.now().timestamp())
        filename = f"{prefix}_p{project_id}_s{scene_number}_{timestamp}{ext}"
        abs_path = os.path.join(abs_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        # 파일 저장
        content = await file.read()
        async with aiofiles.open(abs_path, "wb") as f:
            await f.write(content)
            
        # DB 업데이트
        if is_video:
            db.update_image_prompt_video_url(project_id, scene_number, web_url)
        else:
            db.update_image_prompt_url(project_id, scene_number, web_url)
            
        return {
            "status": "ok",
            "url": web_url,
            "is_video": is_video
        }
    except Exception as e:
        print(f"Upload scene error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/system/open-output-folder")
async def open_output_folder(project_id: int = Body(..., embed=True)):
    """
    [EXE/Local Only] 로컬 시스템에서 프로젝트의 출력 폴더를 직접 엽니다.
    """
    try:
        from app.utils import get_project_output_dir
        abs_dir, _ = get_project_output_dir(project_id)
        
        if os.path.exists(abs_dir):
            import platform
            if platform.system() == "Windows":
                 os.startfile(abs_dir)
            elif platform.system() == "Darwin": # macOS
                 import subprocess
                 subprocess.run(["open", abs_dir])
            else: # Linux
                 import subprocess
                 subprocess.run(["xdg-open", abs_dir])
            return {"status": "ok"}
        else:
            # 폴더가 없으면 기본 출력 폴더라도 열기 시도
            os.startfile(config.OUTPUT_DIR) if os.path.exists(config.OUTPUT_DIR) else None
            return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/projects/{project_id}/output-assets")
async def list_output_assets(project_id: int):
    """
    프로젝트 출력 폴더 내에 이미 생성된 이미지/영상의 목록을 탐색합니다.
    """
    try:
        from app.utils import get_project_output_dir
        abs_dir, web_dir = get_project_output_dir(project_id)
        
        files = []
        if os.path.exists(abs_dir):
            for f in os.listdir(abs_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.avi', '.webm')):
                    f_path = os.path.join(abs_dir, f)
                    stats = os.stat(f_path)
                    files.append({
                        "name": f,
                        "url": f"{web_dir}/{f}",
                        "is_video": f.lower().endswith(('.mp4', '.mov', '.avi', '.webm')),
                        "mtime": stats.st_mtime,
                        "size": stats.st_size
                    })
        
        # 최신순 정렬
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return {"status": "ok", "files": files}
    except Exception as e:
         return {"status": "error", "message": str(e)}


@router.post("/api/projects/{project_id}/replace-asset")
async def replace_asset_from_library(
    project_id: int,
    scene_number: int = Body(...),
    asset_url: str = Body(...),
    is_video: bool = Body(...)
):
    """
    탐색 창에서 선택한 기존 에셋으로 장면 미디어를 교체합니다.
    """
    try:
        if is_video:
            db.update_image_prompt_video_url(project_id, scene_number, asset_url)
        else:
            db.update_image_prompt_url(project_id, scene_number, asset_url)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

