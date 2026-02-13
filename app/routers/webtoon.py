
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os
import shutil
import json
import base64
import re
import io
import time
import httpx
from PIL import Image
import numpy as np
from config import config
import database as db
from services.gemini_service import gemini_service
from services.autopilot_service import autopilot_service
from services.tts_service import tts_service
from pydantic import BaseModel
from typing import List, List as PyList, Optional

from services.i18n import Translator
from services.auth_service import auth_service

router = APIRouter(prefix="/webtoon", tags=["Webtoon Studio"])
templates = Jinja2Templates(directory="templates")

# i18n 및 전역 변수 설정 (base.html 호환성)
app_lang = os.environ.get("APP_LANG", "ko")
LANG_FILE = "language.pref"
if os.path.exists(LANG_FILE):
    try:
        with open(LANG_FILE, "r") as f:
            saved_lang = f.read().strip()
            if saved_lang in ['ko', 'en', 'vi']:
                app_lang = saved_lang
    except: pass

translator = Translator(app_lang)
templates.env.globals['t'] = translator.t
templates.env.globals['current_lang'] = app_lang
templates.env.globals['membership'] = auth_service.get_membership()
templates.env.globals['is_independent'] = auth_service.is_independent()

@router.get("", response_class=HTMLResponse)
async def webtoon_studio_page(request: Request):
    """웹툰 스튜디오 메인 페이지"""
    return templates.TemplateResponse("pages/webtoon_studio.html", {
        "request": request,
        "title": "Webtoon Studio",
        "page": "webtoon-studio"
    })

@router.post("/fetch-url")
async def fetch_webtoon_url(
    project_id: int = Form(...),
    url: str = Form(...)
):
    """네이버 웹툰 URL에서 이미지를 크롤링하여 저장"""
    try:
        if "comic.naver.com" not in url:
            raise HTTPException(400, "Only Naver Webtoon URLs are supported currently.")

        # 1. 페이지 소스 가져오기
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise HTTPException(500, f"Failed to fetch page: {res.status_code}")
            
            html = res.text
            
            # 2. 이미지 URL 추출 (네이버 웹툰은 img_tag 또는 script 내에 존재)
            # 보통 <div class="wt_viewer"> 내의 <img> 태그나 data-src에 있음
            img_urls = re.findall(r'src="(https://image-comic\.pstatic\.net/webtoon/[^"]+)"', html)
            if not img_urls:
                # data-src 패턴 시도
                img_urls = re.findall(r'data-src="(https://image-comic\.pstatic\.net/webtoon/[^"]+)"', html)
            
            if not img_urls:
                raise HTTPException(404, "No webtoon images found in the provided URL.")

            # 중복 제거 및 순서 유지
            seen = set()
            img_urls = [x for x in img_urls if not (x in seen or seen.add(x))]

            # 3. 이미지 다운로드 및 병합 (Vertical Stitching)
            project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
            webtoon_dir = os.path.join(project_dir, "webtoon_originals")
            os.makedirs(webtoon_dir, exist_ok=True)
            
            downloaded_images = []
            
            # Naver image servers check Referer
            img_headers = headers.copy()
            img_headers["Referer"] = "https://comic.naver.com/"

            for i, img_url in enumerate(img_urls):
                img_res = await client.get(img_url, headers=img_headers)
                if img_res.status_code == 200:
                    img_data = Image.open(io.BytesIO(img_res.content))
                    downloaded_images.append(img_data)
                
            if not downloaded_images:
                raise HTTPException(500, "Failed to download any images.")

            # 4. 이미지 세로로 합치기
            total_width = max(img.width for img in downloaded_images)
            total_height = sum(img.height for img in downloaded_images)
            
            merged_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
            y_offset = 0
            for img in downloaded_images:
                # 가비 호환을 위해 RGB 변환
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                merged_img.paste(img, (0, y_offset))
                y_offset += img.height

            # 5. 저장
            filename = f"webtoon_merged_{int(time.time())}.jpg"
            file_path = os.path.join(webtoon_dir, filename)
            merged_img.save(file_path, "JPEG", quality=90)
            
            return {
                "status": "ok",
                "filename": filename,
                "path": file_path,
                "url": f"/api/media/view?path={file_path}"
            }
            
    except Exception as e:
        print(f"Fetch URL error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

import urllib.parse

@router.post("/upload")
async def upload_webtoon(
    project_id: int = Form(...),
    file: UploadFile = File(...)
):
    """웹툰 이미지 업로드 (JPG, PNG, WEBP, PSD 지원)"""
    try:
        # 프로젝트 폴더 생성
        project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
        webtoon_dir = os.path.join(project_dir, "webtoon_originals")
        os.makedirs(webtoon_dir, exist_ok=True)
        
        original_filename = file.filename
        file_ext = os.path.splitext(original_filename)[1].lower()
        
        # PSD 파일 처리
        if file_ext == '.psd':
            from psd_tools import PSDImage
            
            # 1. 원본 PSD 저장
            psd_path = os.path.join(webtoon_dir, original_filename)
            with open(psd_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 2. 미리보기 및 분석용 PNG 변환
            # PSD 로드
            psd = PSDImage.open(psd_path)
            
            # 병합된 이미지 추출 (Composite)
            composite_img = psd.composite()
            
            # PNG 파일명 생성
            png_filename = os.path.splitext(original_filename)[0] + ".png"
            png_path = os.path.join(webtoon_dir, png_filename)
            
            # 저장
            if composite_img:
                composite_img.save(png_path)
            else:
                # 합쳐진 이미지가 없는 경우 (매우 드묾), 강제로 합치기 시도
                composite_img = psd.numpy() # numpy 배열로 변환
                Image.fromarray(composite_img).save(png_path)

            return {
                "status": "ok",
                "filename": png_filename, # 분석 단계에서는 이 PNG를 사용하게 됨
                "original_filename": original_filename,
                "path": png_path,
                "url": f"/api/media/view?path={urllib.parse.quote(png_path)}"
            }
            
        else:
            # 일반 이미지 처리
            file_path = os.path.join(webtoon_dir, original_filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            return {
                "status": "ok",
                "filename": original_filename,
                "path": file_path,
                "url": f"/api/media/view?path={urllib.parse.quote(file_path)}"
            }
            
    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

@router.post("/analyze")
async def analyze_webtoon(
    project_id: int = Form(...),
    filename: str = Form(...)
):
    """웹툰 이미지 슬라이싱 및 AI 분석 (OCR + Scene Description)"""
    try:
        project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
        webtoon_path = os.path.join(project_dir, "webtoon_originals", filename)
        sliced_dir = os.path.join(project_dir, "webtoon_sliced")
        os.makedirs(sliced_dir, exist_ok=True)
        
        if not os.path.exists(webtoon_path):
            raise HTTPException(404, "Webtoon file not found")
            
        # 1. Image Slicing
        cuts = slice_webtoon(webtoon_path, sliced_dir)
        
        # 2. AI Analysis for each cut
        scenes = []
        for i, cut_path in enumerate(cuts):
            try:
                analysis = await gemini_service.analyze_webtoon_panel(cut_path)
            except Exception as e:
                print(f"Gemini evaluation failed for cut {i}: {e}")
                analysis = {"dialogue": "", "character": "None", "visual_desc": "Error during analysis", "atmosphere": "Error"}

            scenes.append({
                "scene_number": i + 1,
                "image_path": cut_path,
                "image_url": f"/api/media/view?path={urllib.parse.quote(cut_path)}",
                "analysis": analysis
            })
            
        return {
            "status": "ok",
            "scenes": scenes
        }
    except Exception as e:
        print(f"Analyze error: {e}")
        raise HTTPException(500, str(e))

def slice_webtoon(image_path: str, output_dir: str, min_padding=30, start_idx=1):
    """
    웹툰 긴 이미지를 칸별로 분할.
    수평 픽셀의 표준편차가 낮은 구간(배경색 구간)을 절단점으로 인식.
    """
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Error opening image {image_path}: {e}")
        return []

    if img.mode != 'RGB':
        img = img.convert('RGB')
        
    img_np = np.array(img.convert('L')) # Grayscale
    
    # 각 행의 표준편차 계산
    row_stds = np.std(img_np, axis=1)
    
    # 표준편차가 낮은 행(여백) 찾기 (임계값 5 미만)
    is_blank = row_stds < 5
    
    cuts = []
    start_y = 0
    in_panel = False
    
    h, w = img_np.shape
    
    # 단순한 split 알고리즘 (개선 가능)
    # 픽셀 단위 루프는 느릴 수 있으므로 최적화 필요하지만 일단 유지
    for y in range(h):
        if not is_blank[y] and not in_panel:
            # 패널 시작 (여백 종료)
            start_y = max(0, y - 10) # 좀 더 여유
            in_panel = True
        elif is_blank[y] and in_panel:
            # 패널 종료 (여백 시작)
            if y - start_y > 150: # 최소 높이 상향
                end_y = min(h, y + 10)
                
                # 이미지 잘라내기
                cut = img.crop((0, start_y, w, end_y))
                
                # 순차적 파일명 생성 (start_idx 반영)
                current_idx = start_idx + len(cuts)
                cut_filename = f"scene_{current_idx:03d}.jpg"
                cut_path = os.path.join(output_dir, cut_filename)
                
                cut.save(cut_path, "JPEG", quality=95)
                cuts.append(cut_path)
                
                in_panel = False
    
    # 마지막 조각 처리
    if in_panel:
        if h - start_y > 150:
            cut = img.crop((0, start_y, w, h))
            current_idx = start_idx + len(cuts)
            cut_filename = f"scene_{current_idx:03d}.jpg"
            cut_path = os.path.join(output_dir, cut_filename)
            cut.save(cut_path, "JPEG", quality=95)
            cuts.append(cut_path)
            
    return cuts

class WebtoonScene(BaseModel):
    scene_number: int
    character: str
    dialogue: str
    visual_desc: str
    image_path: str
    voice_id: Optional[str] = None
    atmosphere: Optional[str] = None
    sound_effects: Optional[str] = None

class ScanRequest(BaseModel):
    path: str

class AnalyzeDirRequest(BaseModel):
    project_id: int
    files: List[str]

class WebtoonAutomateRequest(BaseModel):
    project_id: int
    scenes: List[WebtoonScene]
    use_lipsync: bool = True
    use_subtitles: bool = True

@router.post("/automate")
async def automate_webtoon(req: WebtoonAutomateRequest):
    """분석된 데이터를 프로젝트 설정에 저장하고 대기열로 전송"""
    try:
        project_id = req.project_id
        
        # 1. 스크립트 결합 (멀티보이스 형식 준수)
        full_script = ""
        for s in req.scenes:
            speaker = s.character if s.character and s.character != "None" else "나레이션"
            full_script += f"{speaker}: {s.dialogue}\n\n"
            
        # 2. 이미지 에셋 일괄 이동 및 매칭 설정
        asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image")
        os.makedirs(asset_dir, exist_ok=True)
        # SFX dir
        sfx_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound")
        os.makedirs(sfx_dir, exist_ok=True)
        
        image_prompts = []
        for i, s in enumerate(req.scenes):
            filename = f"scene_{i+1:03d}.jpg"
            dest_path = os.path.join(asset_dir, filename)
            shutil.copy2(s.image_path, dest_path)
            
            # 매칭 정보 저장 (Project Settings - Legacy)
            db.update_project_setting(project_id, f"scene_{i+1}_image", filename)
            db.update_project_setting(project_id, f"scene_{i+1}_motion", "zoom_in")
            db.update_project_setting(project_id, f"scene_{i+1}_motion_speed", "3.3")
            
            # [NEW] Save Scene Voice
            if s.voice_id and s.voice_id != "None":
                db.update_project_setting(project_id, f"scene_{i+1}_voice", s.voice_id)


            # --- Auto SFX Generation (ElevenLabs) ---
            if s.sound_effects and s.sound_effects not in ['None', 'Unknown'] and len(s.sound_effects) > 2:
                try:
                    # Clean up text for better prompt
                    sfx_prompt = re.sub(r'[^\w\s,]', '', s.sound_effects)
                    # Generate SFX using ElevenLabs
                    print(f"Generating SFX for scene {i+1}: {sfx_prompt}")
                    sfx_data = await tts_service.generate_sound_effect(sfx_prompt[:100], duration_seconds=None)
                    
                    if sfx_data:
                        sfx_filename = f"sfx_scene_{i+1:03d}.mp3"
                        sfx_path = os.path.join(sfx_dir, sfx_filename)
                        with open(sfx_path, "wb") as f:
                            f.write(sfx_data)
                        
                        db.update_project_setting(project_id, f"scene_{i+1}_sfx", sfx_filename)
                        print(f"✅ SFX Saved: {sfx_filename}")
                except Exception as e:
                    print(f"❌ SFX Generation failed for scene {i+1}: {e}")

            # [핵심] 이미지 프롬프트 테이블 저장 (AutoPilot 필수 데이터)
            image_prompts.append({
                "scene_number": i + 1,
                "scene_text": s.dialogue,
                "prompt_en": f"{s.visual_desc}", 
                "image_url": f"/output/{str(project_id)}/assets/image/{filename}",
                "narrative": s.dialogue
            })
            
        # 3. 이미지 프롬프트 테이블 일괄 저장
        db.save_image_prompts(project_id, image_prompts)

        # 4. 프로젝트 설정 및 오토파일럿 플래그 업데이트
        db.update_project(project_id, script=full_script, status="queued") # 바로 대기열로!
        db.update_project_setting(project_id, "script", full_script)
        db.update_project_setting(project_id, "auto_plan", False)
        db.update_project_setting(project_id, "app_mode", "shorts") 
        db.update_project_setting(project_id, "auto_tts", 1)      # TTS 자동 생성 활성화
        db.update_project_setting(project_id, "auto_render", 1)   # 렌더링 자동 시작 활성화
        
        # [NEW] 립싱크(Akool) 엔진 설정
        if req.use_lipsync:
            db.update_project_setting(project_id, "video_engine", "akool")
            db.update_project_setting(project_id, "all_video", 1) # 모든 장면을 비디오(립싱크)화
            print(f"🎭 [Webtoon] Lip-sync enabled for project {project_id}")
        else:
            db.update_project_setting(project_id, "video_engine", "wan") # 기본 모션 엔진
            db.update_project_setting(project_id, "all_video", 0)
        
        # 4. 설정 저장 (립싱크 및 자막 여부)
        db.update_project_setting(project_id, "use_lipsync", req.use_lipsync)
        db.update_project_setting(project_id, "use_lipsync", req.use_lipsync)
        db.update_project_setting(project_id, "use_subtitles", req.use_subtitles)

        # [NEW] Save Voice Mapping for future consistency
        final_voice_map = {}
        for s in req.scenes:
            if s.character and s.voice_id and s.character != "None" and s.voice_id != "None":
                 final_voice_map[s.character] = s.voice_id
        
        if final_voice_map:
             db.update_project_setting(project_id, "voice_mapping_json", json.dumps(final_voice_map, ensure_ascii=False))

        # 5. 백그라운드 워커가 감지할 수 있도록 보장
        autopilot_service.add_to_queue(project_id)
        
        return {"status": "ok", "message": "Project added to queue for automation"}
        
    except Exception as e:
        print(f"Automate error: {e}")
        raise HTTPException(500, str(e))

@router.post("/scan")
async def scan_directory(req: ScanRequest):
    """로컬 디렉토리의 웹툰 파일 스캔"""
    if not os.path.exists(req.path):
        return JSONResponse({"status": "error", "error": "Path does not exist"}, status_code=404)
    
    files = []
    try:
        # 파일명 기준 정렬 (1화_001, 1화_002 순서 보장)
        file_list = sorted(os.listdir(req.path))
        
        for f in file_list:
            full_path = os.path.join(req.path, f)
            if os.path.isfile(full_path):
                ext = os.path.splitext(f)[1].lower()
                if ext in ['.psd', '.png', '.jpg', '.jpeg', '.webp']:
                    files.append({
                        "filename": f,
                        "path": full_path,
                        "size": os.path.getsize(full_path)
                    })
    except Exception as e:
         return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
    
    return {"status": "ok", "files": files}

@router.post("/analyze-dir")
async def analyze_directory(req: AnalyzeDirRequest):
    """로컬 파일 리스트를 입력받아 일괄 분석 (Direct Access)"""
    try:
        project_dir = os.path.join(config.OUTPUT_DIR, str(req.project_id))
        sliced_base_dir = os.path.join(project_dir, "webtoon_sliced")
        os.makedirs(sliced_base_dir, exist_ok=True)
        
        # Temp dir for PSD conversion
        temp_dir = os.path.join(project_dir, "temp_psd_conversion")
        os.makedirs(temp_dir, exist_ok=True)
        
        all_scenes = []
        global_scene_counter = 1
        
        # [NEW] Load Previous Context for Continuity
        prev_context = None
        current_project = db.get_project(req.project_id)
        if current_project and current_project.get("topic"):
            topic = current_project["topic"]
            conn = db.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE topic = ? AND id != ? ORDER BY id DESC LIMIT 1", (topic, req.project_id))
            row = cursor.fetchone()
            if row:
                prev_id = row["id"]
                cursor.execute("SELECT full_script FROM scripts WHERE project_id = ?", (prev_id,))
                script_row = cursor.fetchone()
                if script_row and script_row["full_script"]:
                     prev_context = script_row["full_script"][-500:] # Last 500 chars
            conn.close()
            if prev_context:
                print(f"📖 [Webtoon] Loaded context from previous episode: {len(prev_context)} chars")
        
        for file_path in req.files:
            if not os.path.exists(file_path):
                continue
                
            ext = os.path.splitext(file_path)[1].lower()
            target_image_path = file_path
            
            # --- 1. PSD Handling (In-place or Temp) ---
            if ext == '.psd':
                try:
                    from psd_tools import PSDImage
                    import uuid
                    # PSD -> PNG Temp
                    temp_png_name = f"{uuid.uuid4().hex}.png"
                    temp_png_path = os.path.join(temp_dir, temp_png_name)
                    
                    psd = PSDImage.open(file_path)
                    composite = psd.composite()
                    if not composite: 
                        composite = Image.fromarray(psd.numpy())
                    
                    composite.save(temp_png_path)
                    target_image_path = temp_png_path
                except Exception as e:
                    print(f"Failed to process PSD {file_path}: {e}")
                    continue
            
            # --- 2. Slicing with continuous numbering ---
            # start_idx를 넘겨주어 Scene 번호가 이어지게 함
            cuts = slice_webtoon(target_image_path, sliced_base_dir, start_idx=global_scene_counter)
            
            # --- 3. Analysis ---
            for cut_path in cuts:
                try:
                    # Pass context to Gemini
                    analysis = await gemini_service.analyze_webtoon_panel(cut_path, context=prev_context)
                except Exception as e:
                    print(f"Gemini failed for {cut_path}: {e}")
                    analysis = {"dialogue": "", "character": "Unknown", "visual_desc": "Analysis failed", "atmosphere": "Error"}

                all_scenes.append({
                    "scene_number": global_scene_counter,
                    "image_path": cut_path,
                    "image_url": f"/api/media/view?path={urllib.parse.quote(cut_path)}",
                    "analysis": analysis
                })
                global_scene_counter += 1
            
            # Clean up temp PNG
            if ext == '.psd' and target_image_path.startswith(temp_dir):
                try:
                    os.remove(target_image_path)
                except: pass

        # --- 4. Auto Voice Assignment (ElevenLabs API Integrated) ---
        from services.tts_service import tts_service
        
        # 1. Fetch ElevenLabs Voices
        try:
            eleven_voices = await tts_service.get_elevenlabs_voices()
        except:
            eleven_voices = []
        
        # 2. Categorize Voices
        male_pool = []
        female_pool = []
        default_pool = [] # Mixed
        
        for v in eleven_voices:
            vid = v.get("voice_id")
            labels = v.get("labels", {})
            gender = labels.get("gender", "").lower()
            
            # Add to pools
            default_pool.append(vid)
            if gender == "male": 
                male_pool.append(vid)
            elif gender == "female":
                female_pool.append(vid)
        
        # Fallbacks (Antoni, Rachel, Josh, etc.) if API fails or empty
        # These are standard ElevenLabs pre-made voices
        if not male_pool: male_pool = ["ErXwobaYiN019PkySvjV", "TxGEqnHWrfWFTfGW9XjX"] 
        if not female_pool: female_pool = ["21m00Tcm4TlvDq8ikWAM", "EXAVITQu4vr4xnSDxMaL"]
        if not default_pool: default_pool = male_pool + female_pool

        if not default_pool: default_pool = male_pool + female_pool

        char_voice_map = {}
        
        # [NEW] Load previous character voices for consistency
        current_project = db.get_project(req.project_id)
        if current_project and current_project.get("topic"):
            topic = current_project["topic"]
            # Find recent project with same topic
            conn = db.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE topic = ? AND id != ? ORDER BY id DESC LIMIT 1", (topic, req.project_id))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                prev_id = row["id"]
                prev_settings = db.get_project_settings(prev_id) or {}
                if prev_settings.get("voice_mapping_json"):
                    try:
                        loaded_map = json.loads(prev_settings["voice_mapping_json"])
                        char_voice_map.update(loaded_map)
                        print(f"📖 [Webtoon] Loaded {len(loaded_map)} character voices from Project {prev_id}")
                    except: pass

        male_idx = 0
        female_idx = 0
        misc_idx = 0
        
        char_normalization = {
            "Narrator": "내레이션", "narrator": "내레이션", "Unknown": "Unknown", "None": "Unknown"
        }

        all_scenes_result = [] # Rebuild list to ensure order
        
        # Pre-scan for characters to build map first (for consistency across scenes)
        # But here we iterate scenes and assign on fly, maintaining map. Same effect.
        
        for sc in all_scenes:
            raw_char = sc['analysis'].get('character', 'Unknown')
            # Normalize
            if raw_char in char_normalization:
                norm_char = char_normalization[raw_char]
            else:
                norm_char = raw_char.strip().replace("'", "").replace('"', "")
            
            # Update analysis result with normalized name
            sc['analysis']['character'] = norm_char
            
            # Assign Voice ID if new character
            if norm_char not in char_voice_map:
                lower_char = norm_char.lower()
                
                # Narrator / Unknown -> Reliable Neutral Voice (Usually Male 0)
                if norm_char in ['내레이션', 'Unknown', 'None']:
                     char_voice_map[norm_char] = male_pool[0] 
                
                # Female Characters
                elif any(x in lower_char for x in ['girl', 'woman', 'female', '엄마', '그녀', '소녀', '여자', '누나', '언니', 'lady', 'miss', 'wife']):
                     voice = female_pool[female_idx % len(female_pool)]
                     char_voice_map[norm_char] = voice
                     female_idx += 1
                
                # Male Characters
                elif any(x in lower_char for x in ['boy', 'man', 'male', '아빠', '그', '소년', '남자', '형', '오빠', 'gentleman', 'mr', 'husband']):
                     voice = male_pool[male_idx % len(male_pool)]
                     char_voice_map[norm_char] = voice
                     male_idx += 1
                
                # Others -> Round Robin from Default Pool
                else:
                     voice = default_pool[misc_idx % len(default_pool)]
                     char_voice_map[norm_char] = voice
                     misc_idx += 1
            
            # Assign the determined voice_id to the scene
            sc['voice_id'] = char_voice_map[norm_char]
            all_scenes_result.append(sc)

        # Clean up temp dir
        try:
            shutil.rmtree(temp_dir)
        except: pass
            
        return {
            "status": "ok",
            "scenes": all_scenes_result,
            "total_scenes": len(all_scenes_result),
            "filename": "batch_process",
            "character_map": char_voice_map # Frontend can display this mapping
        }
    except Exception as e:
        print(f"Analyze Directory Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))
