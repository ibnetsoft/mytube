
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Body
from typing import List, Dict
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import os
import shutil
import json
import base64
import re
import io
import time
import httpx
import urllib.parse
from PIL import Image
import numpy as np
from config import config
import database as db
from services.gemini_service import gemini_service
from services.autopilot_service import autopilot_service
from services.tts_service import tts_service
from pydantic import BaseModel
from typing import List, List as PyList, Optional

import unicodedata
from services.i18n import Translator
from services.auth_service import auth_service

def finalize_scene_analysis(scene: Dict, voice_consistency_map: Dict, eleven_voices: List = None) -> Dict:
    """
    AI 분석 결과에 일관성을 부여하고, 유실된 데이터(성우, 효과음 등)를 보정하는 최종 단계.
    """
    analysis = scene.get('analysis', {})
    
    # 1. 캐릭터 이름 정규화 및 성우 배정
    raw_char = str(analysis.get('character', 'Unknown')).strip()
    if raw_char.lower() in ["none", "null", "undefined", "", "none "]: raw_char = "Unknown"
    
    # Narrator variants + Defaulting Unknown speech to Narration
    char_lower = raw_char.lower()
    dialogue = str(analysis.get('dialogue', '')).strip()
    
    narrator_keywords = ['narrator', 'narration', '내레이션', '해설', 'unknown', 'none', '', 'undefined']
    if any(char_lower == kw for kw in narrator_keywords):
        if dialogue:
            norm_char = "내레이션"
        else:
            norm_char = "Unknown"
    else:
        norm_char = raw_char.replace("'", "").replace('"', "")

    # Sync to analysis
    analysis['character'] = norm_char
    
    # 2. Voice ID/Name 배정 (일관성 유지가 1순위)
    suggested_voice = analysis.get('voice_recommendation') or {}
    final_voice_id = str(suggested_voice.get('id', '')).strip()
    final_voice_name = str(suggested_voice.get('name', '')).strip()
    
    # "None" 문자열 필터링
    if final_voice_id.lower() in ["none", "null", "", "unknown"]: final_voice_id = None
    if final_voice_name.lower() in ["none", "null", "", "unknown voice"]: final_voice_name = None

    # 일관성 맵 확인
    if norm_char != "Unknown" and norm_char in voice_consistency_map:
        existing = voice_consistency_map[norm_char]
        if isinstance(existing, dict):
            final_voice_id = existing.get("id")
            final_voice_name = existing.get("name")
        else:
            final_voice_id = existing # legacy string
    
    # [MODIFIED] 내레이션(Narrator) 일관성 강제: 무조건 Brian 성우 사용
    if norm_char == "내레이션":
        final_voice_id = "nPczCjzI2devNBz1zQrb"
        final_voice_name = "Brian"

    # [NEW] 신규 캐릭터 자동 성우 할당 (맵에 없고 내레이션도 아닌 경우)
    if not final_voice_id and norm_char != "Unknown":
        # 성별 및 나이 감지 (간단한 키워드 기반)
        lower_char = norm_char.lower()
        is_female = any(x in lower_char for x in ['girl', 'woman', 'female', '엄마', '그녀', '소녀', '여자', '누나', '언니', 'lady', 'miss', 'wife', 'rachel', 'bella', 'nicole'])
        
        # 기본 풀 (백엔드 하드코딩된 안정적인 성우들)
        female_pool = ["21m00Tcm4TlvDq8ikWAM", "EXAVITQu4vr4xnSDxMaL", "AZnzlk1XhkbcUvJdpS9D", "z9fAnlkUCjS8Inj9L65X"] # Rachel, Bella, Nicole, Dorothy
        male_pool = ["ErXwobaYiN019PkySvjV", "TxGEqnHWrfWFTfGW9XjX", "bIHbv24qawwzYvFyYv6f", "N2lVS1wzCLPce5hNBy94"] # Antoni, Josh, Adam, Josh (alt)

        # 실제 ElevenLabs 데이터가 있으면 활용
        if eleven_voices:
            f_list = [v['voice_id'] for v in eleven_voices if v.get('labels', {}).get('gender') == 'female']
            m_list = [v['voice_id'] for v in eleven_voices if v.get('labels', {}).get('gender') == 'male']
            if f_list: female_pool = f_list
            if m_list: male_pool = m_list

        # 결정적 할당 (캐릭터 이름 해시값 사용)
        import hashlib
        h = int(hashlib.md5(norm_char.encode()).hexdigest(), 16)
        if is_female:
            final_voice_id = female_pool[h % len(female_pool)]
        else:
            final_voice_id = male_pool[h % len(male_pool)]

    # 2.5 voice_consistency_map 업데이트 (다음 씬에서 동일 캐릭터가 나오면 같은 성우 사용)
    if norm_char != "Unknown" and final_voice_id:
        voice_consistency_map[norm_char] = {"id": final_voice_id, "name": final_voice_name or "Assigning..."}

    # 3. 보이스 이름 유실 복구 (ElevenLabs 기반)
    # final_voice_name이 비어있거나 "None"인 경우 강제 복구
    if not final_voice_name or str(final_voice_name).lower() in ["none", "null", "unknown voice", "unknown", "generic description"]:
        if eleven_voices and final_voice_id and final_voice_id not in ["unknown", "None"]:
            for v in eleven_voices:
                if v.get("voice_id") == final_voice_id:
                    final_voice_name = v.get("name")
                    break
        
        if not final_voice_name or str(final_voice_name).lower() in ["none", "null"]:
            fallback_names = {
                "ErXwobaYiN019PkySvjV": "Antoni (Male)",
                "TxGEqnHWrfWFTfGW9XjX": "Josh (Male)",
                "21m00Tcm4TlvDq8ikWAM": "Rachel (Female)",
                "EXAVITQu4vr4xnSDxMaL": "Bella (Female)",
                "nPczCjzI2devNBz1zQrb": "Brian (Narrator)"
            }
            final_voice_name = fallback_names.get(final_voice_id, "Default Character Voice")

    # Update Scene Root and Analysis
    scene['voice_id'] = final_voice_id or "unknown"
    scene['voice_name'] = str(final_voice_name or "Default Character Voice")
    
    if 'voice_recommendation' not in analysis: analysis['voice_recommendation'] = {}
    analysis['voice_recommendation']['id'] = final_voice_id or "unknown"
    analysis['voice_recommendation']['name'] = str(final_voice_name or "Default Character Voice")

    # [NEW] Final "Nuclear" anti-None check for UI strings
    if str(scene.get('voice_name','')).lower() in ["none", "null", "unknown", "", "undefined"]:
        scene['voice_name'] = "Default Character Voice"
        analysis['voice_recommendation']['name'] = "Default Character Voice"
    
    # Final cleanup for voice_id to avoid "null" in JSON
    if not scene['voice_id'] or str(scene['voice_id']).lower() in ["none", "null"]:
        scene['voice_id'] = "unknown"

    # 4. 오디오 디렉션 (효과음/배경음) 스마트 보정
    aud = scene.get('audio_direction') or analysis.get('audio_direction') or {}
    sfx_val = str(aud.get('sfx_prompt', '')).strip()
    bgm_val = str(aud.get('bgm_mood', '')).strip()
    atmosphere = str(analysis.get('atmosphere', '')).lower()
    dialogue = str(analysis.get('dialogue', '')).lower()
    visual = str(analysis.get('visual_desc', '')).lower()
    
    # [NEW] 영어 묘사(Visual Desc)도 키워드 검사에 활용 (더 넓은 범위의 감지)
    combined_desc = f"{dialogue} {visual}"

    # SFX 보정: 'None' 문자열이거나 비어있을 때만 검사
    if not sfx_val or sfx_val.lower() in ['none', 'null', '', 'no sound', 'silence']:
        sfx = ""
        # 명확한 소리 유발 키워드가 있을 때만 보충
        if any(x in combined_desc for x in ["쾅", "폭발", "bang", "boom", "explosion", "clash", "sword", "impact", "검술", "부딪히는"]): sfx = "Cinematic impact and clashing"
        elif any(x in combined_desc for x in ["슈", "woosh", "wind", "피융", "fly", "motion blur"]): sfx = "Fast whoosh motion"
        elif any(x in combined_desc for x in ["터벅", "step", "발자국", "walk", "running"]): sfx = "Footsteps"
        elif any(x in combined_desc for x in ["웃음", "laugh", "chuckle", "smile"]): sfx = "Subtle background laughter"
        
        if sfx:
            aud['sfx_prompt'] = sfx
            aud['has_sfx'] = True
        else:
            # 실효성 없는 Silence는 빈칸으로 유지하여 "의도된 침묵" 허용
            aud['sfx_prompt'] = ""
            aud['has_sfx'] = False
    else:
        # 이미 값이 있으면 (AI가 직접 적은 경우) 유지
        aud['has_sfx'] = True

    # BGM 보정: 분위기가 정말 있을 때만 추천
    if not bgm_val or bgm_val.lower() in ['none', 'null', 'silence', '']:
        # 무조건 Cinematic을 넣지 않고, 의미 있는 분위기일 때만 반영
        meaningful_atm = atmosphere and atmosphere not in ["none", "unknown", "static", "blank", "neutral"]
        if meaningful_atm:
            aud['bgm_mood'] = atmosphere.capitalize()
        # 시각적 묘사에 강한 키워드가 있으면 추가 추천
        elif any(x in visual for x in ["clash", "fight", "war", "battle", "sword"]):
             aud['bgm_mood'] = "Epic Battle"
        else:
            aud['bgm_mood'] = "" # 평범한 장면은 비워둠 (침묵 허용)

    scene['audio_direction'] = aud
    analysis['audio_direction'] = aud

    # 5. 성우 설정 (톤/이유) 스마트 보정
    vs = scene.get('voice_settings') or analysis.get('voice_settings') or {}
    if not vs or not vs.get('reason') or str(vs.get('reason')).lower() in ["none", "null", "why this tone?", ""]:
        # [NEW] 더 구체적인 이유 생성
        atm_reason = atmosphere.capitalize() if atmosphere not in ["none", "unknown"] else "natural"
        vs_reason = f"Matching {norm_char}'s {atm_reason} tone in this scene."
        if not vs or not isinstance(vs, dict): vs = {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0}
        vs['reason'] = vs_reason
    
    scene['voice_settings'] = vs
    analysis['voice_settings'] = vs
    scene['analysis'] = analysis # Ensure synced
    
    # [NEW] Final "Nuclear" anti-None check for UI
    if str(scene.get('voice_name')).lower() in ["none", "null", "unknown", ""]:
        scene['voice_name'] = "Default Character Voice"
        analysis['voice_recommendation']['name'] = "Default Character Voice"

    return scene

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
    filename: str = Form(...),
    psd_exclude_layer: Optional[str] = Form(None)
):
    """웹툰 이미지 슬라이싱 및 AI 분석 (OCR + Scene Description)"""
    try:
        project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
        webtoon_path = os.path.join(project_dir, "webtoon_originals", filename)
        sliced_dir = os.path.join(project_dir, "webtoon_sliced")
        
        # [CRITICAL] 이전 분석 결과 물리적으로 삭제하여 캐시 및 찌꺼기 방지
        if os.path.exists(sliced_dir):
            shutil.rmtree(sliced_dir)
        os.makedirs(sliced_dir, exist_ok=True)
        
        if not os.path.exists(webtoon_path):
            raise HTTPException(404, "Webtoon file not found")
            
        def normalize_name(s):
            if not s: return ""
            # NFC/NFKC 통합
            s = unicodedata.normalize('NFKC', str(s))
            # 공백 및 제어문자 제거, 소문자화 (한글/영문/숫자/일부특수문자 유지)
            s = "".join(c for c in s if not c.isspace() and ord(c) > 31).lower()
            return s

        layer_trace = []
        debug_all_layers = {}

        # 1. Image Slicing (PSD handling for clean images)
        analysis_image_path = webtoon_path
        clean_image_path = None
        ext = os.path.splitext(filename)[1].lower()
        temp_dir = os.path.join(config.MEDIA_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        if ext == '.psd':
            from psd_tools import PSDImage
            import uuid
            
            try:
                # 1. 분석용 (전체 레이어)
                psd_ana = PSDImage.open(webtoon_path)
                ana_png = os.path.join(temp_dir, f"ana_{uuid.uuid4().hex}.png")
                comp_ana = psd_ana.composite()
                if not comp_ana: comp_ana = Image.fromarray(psd_ana.numpy())
                comp_ana.save(ana_png)
                analysis_image_path = ana_png
                
                # 2. 영상용 (지정 레이어 제외)
                clean_image_path = ana_png # Default
                matched_layers = []
                
                # PSD인 경우 모든 레이어 구조를 항상 디버그 정보에 포함
                all_layers_list = [l.name for l in psd_ana.descendants() if l.name][:100]
                debug_all_layers = {
                    "layers": all_layers_list,
                    "matched": [],
                    "keywords": [],
                    "method": "analysis_only"
                }

                if psd_exclude_layer:
                    psd_cln = PSDImage.open(webtoon_path)
                    raw_keywords = [k.strip() for k in re.split(r'[,，\s\n]+', psd_exclude_layer) if k.strip()]
                    keywords = [normalize_name(k) for k in raw_keywords]
                    print(f"🔍 [PSD Match] Keywords: {keywords}")
                    
                    found_any = False
                    for layer in psd_cln.descendants():
                        if not layer.name: continue
                        name_norm = normalize_name(layer.name)
                        
                        if any(k in name_norm for k in keywords):
                            if layer.visible: # 이미 꺼진 건 무시
                                print(f"👉 [PSD Filter] Hiding: '{layer.name}' (norm: {name_norm})")
                                layer.visible = False
                                layer_trace.append(layer.name)
                                matched_layers.append(layer.name)
                                # 하위 레이어까지 재귀적으로 강제 은닉
                                if hasattr(layer, 'descendants'):
                                    for child in layer.descendants():
                                        child.visible = False
                                found_any = True
                    
                    if found_any:
                        cln_png = os.path.join(temp_dir, f"cln_{uuid.uuid4().hex}.png")
                        try:
                            comp_cln = psd_cln.composite()
                        except:
                            comp_cln = None

                        method = "composite"
                        if not comp_cln:
                            method = "manual_merge"
                            print("   [PSD] Main composite failed. Starting Manual Merge Fallback...")
                            # 바탕을 흰색(solid)으로 시작
                            canvas = Image.new("RGBA", psd_cln.size, (255, 255, 255, 255))
                            for l in psd_cln:
                                if l.visible:
                                    try:
                                        l_img = l.composite()
                                        if l_img:
                                            canvas.alpha_composite(l_img.convert("RGBA"))
                                    except:
                                        pass
                            comp_cln = canvas.convert("RGB")
                        
                        if comp_cln.mode != 'RGB':
                            comp_cln = comp_cln.convert('RGB')
                        comp_cln.save(cln_png)
                        clean_image_path = cln_png
                        debug_all_layers = {
                            "layers": [l.name for l in psd_cln.descendants() if l.name][:100],
                            "matched": matched_layers,
                            "keywords": keywords,
                            "method": method
                        }
                    else:
                        print(f"   [PSD] No layer matched from {keywords}")
                        all_names = [l.name for l in psd_cln.descendants() if l.name][:50]
                        debug_all_layers = {
                            "layers": all_names,
                            "matched": [],
                            "keywords": keywords,
                            "method": "none_matched"
                        }
                
            except Exception as e:
                print(f"PSD PROCESS ERROR: {e}")
                import traceback
                traceback.print_exc()
                clean_image_path = webtoon_path
        else:
            clean_image_path = webtoon_path

        cuts = slice_webtoon(analysis_image_path, sliced_dir, clean_image_path=clean_image_path)
        
        # Temp PNG cleanup
        if ext == '.psd':
            for p in [analysis_image_path, clean_image_path]:
                if p and p.startswith(temp_dir) and os.path.exists(p):
                    try: os.remove(p)
                    except: pass
        
        # [NEW] Prepare Voice Options for AI Recommendation
        voice_options_str = None
        try:
            voices = await tts_service.get_elevenlabs_voices()
            if voices:
                v_list = []
                # Limit to top 40 to avoid token overflow
                for v in voices[:40]:
                    labels = v.get('labels', {})
                    # Simplify labels
                    traits = []
                    if 'gender' in labels: traits.append(labels['gender'])
                    if 'age' in labels: traits.append(labels['age'])
                    if 'accent' in labels: traits.append(labels['accent'])
                    if 'description' in labels: traits.append(labels['description']) # Some use description
                    
                    trait_str = ", ".join(traits) if traits else "General"
                    v_list.append(f"- Name: {v['name']} (ID: {v['voice_id']}) - {trait_str}")
                
                voice_options_str = "\n".join(v_list)
        except Exception as e:
            print(f"⚠️ Failed to load voices for recommendation: {str(e)}")

        # [NEW] Pre-fetch context and voices
        eleven_voices = []
        try: eleven_voices = await tts_service.get_elevenlabs_voices()
        except: pass

        voice_consistency_map = {}
        try:
            p_set = db.get_project_settings(project_id) if project_id else {}
            if p_set and p_set.get('voice_mapping_json'):
                raw_map = json.loads(p_set.get('voice_mapping_json'))
                # Normalize format to dict
                for k, v in raw_map.items():
                    if isinstance(v, dict): voice_consistency_map[k] = v
                    else: voice_consistency_map[k] = {"id": v, "name": "Unknown Voice"}
        except: pass

        # 2. AI Analysis for each cut with context passing
        scenes = []
        context = ""
        for i, cut_info in enumerate(cuts):
            video_path = cut_info["video"]
            analysis_path = cut_info["analysis"]
            
            try:
                analysis = await gemini_service.analyze_webtoon_panel(analysis_path, context=context, voice_options=voice_options_str)
                
                # Skip meaningless panels (copyright, blank, etc.)
                is_meaningless = analysis.get('is_meaningless') is True
                dialogue = analysis.get('dialogue', '').strip()
                visual = analysis.get('visual_desc', '').lower()
                
                # Extra safety: check for copyright keywords if dialogue is provided
                copyright_keywords = [
                    "저작권", "무단 전재", "illegal copy", "all rights reserved", "무단 복제", "RK STUDIO",
                    "studio", "webtoon", "episode", "next time", "to be continued", "copyright", "scan", "watermark"
                ]
                
                if "completely dark" in visual or "completely black" in visual or "blank panel" in visual:
                    if not dialogue:
                        is_meaningless = True

                if any(k in dialogue for k in copyright_keywords) and len(dialogue) < 150:
                    is_meaningless = True

                if is_meaningless:
                    print(f"Skipping meaningless panel {i} (Visual: {visual})")
                    continue

                import time
                ts = int(time.time())
                scene = {
                    "scene_number": len(scenes) + 1,
                    "image_path": video_path,
                    "image_url": f"/api/media/view?path={urllib.parse.quote(video_path)}&t={ts}",
                    "analysis": analysis,
                    "focal_point_y": analysis.get("focal_point_y", 0.5)
                }

                # [REF ACTOR] Use centralized helper for consistency & fallbacks
                finalize_scene_analysis(scene, voice_consistency_map, eleven_voices)
                
                # Update map and save to DB for future consistency
                norm_char = scene['analysis']['character']
                if norm_char != "Unknown":
                    voice_consistency_map[norm_char] = {"id": scene['voice_id'], "name": scene['voice_name']}
                    try:
                        db.update_project_setting(project_id, "voice_mapping_json", json.dumps(voice_consistency_map, ensure_ascii=False))
                    except: pass

                # Update context for next panel
                if dialogue:
                    context = f"Last seen: {norm_char} said \"{dialogue[:100]}\"."
                
                scenes.append(scene)

            except Exception as e:
                print(f"Gemini evaluation failed for cut {i}: {e}")
                import time
                ts = int(time.time())
                scenes.append({
                    "scene_number": len(scenes) + 1,
                    "image_path": video_path,
                    "image_url": f"/api/media/view?path={urllib.parse.quote(video_path)}&t={ts}",
                    "analysis": {"dialogue": "", "character": "Unknown", "visual_desc": "Error during analysis", "atmosphere": "Error"}
                })
            
        response_data = {
            "status": "ok",
            "scenes": scenes,
            "layer_debug": {
                "trace": layer_trace,
                "all": debug_all_layers # Removed slice [:100] as it can be a dict
            }
        }
        return response_data
    except Exception as e:
        print(f"Analyze error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

def slice_webtoon(image_path: str, output_dir: str, min_padding=30, start_idx=1, clean_image_path: str = None):
    """
    웹툰 긴 이미지를 칸별로 분할.
    clean_image_path가 제공되면, image_path(원본)로 절단점을 찾고 두 이미지 모두를 잘라냅니다.
    """
    try:
        img = Image.open(image_path)
        clean_img = Image.open(clean_image_path) if clean_image_path else None
    except Exception as e:
        print(f"Error opening images: {e}")
        return []

    if img.mode != 'RGB':
        img = img.convert('RGB')
    if clean_img and clean_img.mode != 'RGB':
        clean_img = clean_img.convert('RGB')
        
    img_np = np.array(img.convert('L')) # Grayscale
    h, w = img_np.shape
    
    # [IMPROVED] 여백 감지 로직 개선
    # 단순 std만 보는 게 아니라, 평균 밝기가 매우 높거나(흰색) 매우 낮은(검은색) 경우도 고려
    row_stds = np.std(img_np, axis=1)
    row_means = np.mean(img_np, axis=1)
    
    # 여백 조건: (표준편차가 매우 낮음) AND (밝기가 아주 밝거나 아주 어두움)
    # std < 5 (좀 더 여유있게)
    # mean > 240 (흰색) or mean < 15 (검은색)
    is_blank = (row_stds < 5) & ((row_means > 240) | (row_means < 15))
    
    # 여백 구간 탐지
    blank_threshold = 30 # 최소 30픽셀 이상이어야 여백으로 인정
    blank_runs = []
    run_start = -1
    
    for y in range(h):
        if is_blank[y]:
            if run_start == -1: run_start = y
        else:
            if run_start != -1:
                if y - run_start >= blank_threshold:
                    blank_runs.append((run_start, y))
                run_start = -1
    if run_start != -1 and h - run_start >= blank_threshold:
        blank_runs.append((run_start, h))

    # 절단점을 기준으로 조각 범위 결정
    panel_ranges = []
    if not blank_runs:
        # 여백이 아예 없으면 통으로 1장
        panel_ranges = [(0, h)]
    else:
        last_y = 0
        for start, end in blank_runs:
            # 여백 시작점(start)까지가 하나의 컷
            # 단, 컷의 높이가 최소 50px은 되어야 함
            if start - last_y > 50:
                panel_ranges.append((last_y, start))
            last_y = end # 여백 끝점(end)부터 다음 컷 시작
            
        # 마지막 남은 부분 처리
        if h - last_y > 50:
            panel_ranges.append((last_y, h))

    cuts = []
    for i, (p_start, p_end) in enumerate(panel_ranges):
        # 약간의 여백 포함 (위아래 5px) - 단 이미지 범위 내에서
        p_start = max(0, p_start - 5)
        p_end = min(h, p_end + 5)
        
        # 원본 이미지 잘라내기 (분석용)
        cut_full = img.crop((0, p_start, w, p_end))
        
        # [REFINED] 정밀 필터링 강화 (짜투리 제거)
        cut_gray = np.array(cut_full.convert('L'))
        std_val = np.std(cut_gray)
        mean_val = np.mean(cut_gray)
        h_cut, w_cut = float(cut_gray.shape[0]), float(cut_gray.shape[1])
        
        # 1. 너무 작은 조각 제거 (높이 100px 미만)
        if h_cut < 100:
            print(f"      - Skipping too small panel (h={h_cut})")
            continue

        # 2. 단색(검은색/흰색) 배경 제거
        # std가 적당히 낮으면서(10 미만), 평균 밝기가 양극단(어둡거나 밝음)인 경우
        is_dark_junk = (mean_val < 30) and (std_val < 10)  # 검은색 띠
        is_light_junk = (mean_val > 225) and (std_val < 10) # 흰색 여백
        
        # 3. 거의 완벽한 단색 (노이즈 포함)
        is_flat = std_val < 3.0
        
        if is_dark_junk or is_light_junk or is_flat:
            print(f"      - Skipping junk panel (std={std_val:.2f}, mean={mean_val:.2f})")
            continue
            
        current_idx = start_idx + len(cuts)
        
        # 파일 저장
        analysis_filename = f"scene_{current_idx:03d}_ana.jpg"
        analysis_path = os.path.join(output_dir, analysis_filename)
        cut_full.save(analysis_path, "JPEG", quality=95)
        
        video_path = analysis_path # 기본값
        
        if clean_img:
            # 클린 이미지 잘라내기 (영상용)
            # 좌표는 원본과 동일하게 사용
            cut_clean = clean_img.crop((0, p_start, w, p_end))
            video_filename = f"scene_{current_idx:03d}.jpg"
            video_path = os.path.join(output_dir, video_filename)
            cut_clean.save(video_path, "JPEG", quality=95)
        
        cuts.append({
            "video": video_path,
            "analysis": analysis_path
        })
                
    if not cuts:
         print("⚠️ No cuts found after slicing. Fallback to using the whole image.")
         # 전체 이미지를 하나로 저장해서라도 반환
         full_ana_path = os.path.join(output_dir, "scene_001_ana.jpg")
         img.save(full_ana_path, "JPEG")
         cuts.append({"video": full_ana_path, "analysis": full_ana_path})
         
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
    focal_point_y: Optional[float] = 0.5
    engine_override: Optional[str] = None
    effect_override: Optional[str] = None
    motion_desc: Optional[str] = None
    voice_settings: Optional[dict] = None
    audio_direction: Optional[dict] = None

class ScanRequest(BaseModel):
    path: str

class AnalyzeDirRequest(BaseModel):
    project_id: int
    files: List[str]
    psd_exclude_layer: Optional[str] = None

class WebtoonAutomateRequest(BaseModel):
    project_id: int
    scenes: List[WebtoonScene]
    use_lipsync: bool = True
    use_subtitles: bool = True
    character_map: Optional[dict] = None

class WebtoonPlanRequest(BaseModel):
    project_id: int
    scenes: List[dict]

@router.post("/generate-plan")
async def generate_webtoon_plan(req: WebtoonPlanRequest):
    """장면별 대사/묘사를 바탕으로 비디오 제작 기획서(기술 사양) 생성"""
    try:
        plan = await gemini_service.generate_webtoon_plan(req.scenes)
        return {"status": "ok", "plan": plan}
    except Exception as e:
        print(f"Plan Gen Error: {e}")
        raise HTTPException(500, str(e))

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
            
            # Use overrides if present, else default to zoom_in
            motion = s.effect_override or "zoom_in"
            db.update_project_setting(project_id, f"scene_{i+1}_motion", motion)
            db.update_project_setting(project_id, f"scene_{i+1}_motion_speed", "3.3")
            
            # Engine override per scene (if supported by autopilot_service later)
            if s.engine_override:
                db.update_project_setting(project_id, f"scene_{i+1}_engine", s.engine_override)
            
            # [NEW] Save special motion description for Wan engine
            if s.motion_desc:
                db.update_project_setting(project_id, f"scene_{i+1}_motion_desc", s.motion_desc)
            
            # [NEW] Save Scene Voice
            if s.voice_id and s.voice_id != "None":
                db.update_project_setting(project_id, f"scene_{i+1}_voice", s.voice_id)

            # [NEW] Save Voice Settings (Tone/Speed)
            if s.voice_settings:
                # Ensure it's JSON string for DB storage
                try:
                    vs_json = json.dumps(s.voice_settings)
                    db.update_project_setting(project_id, f"scene_{i+1}_voice_settings", vs_json)
                except:
                    pass


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
            # [핵심] 이미지 프롬프트 테이블 저장 (AutoPilot 필수 데이터)
            image_prompts.append({
                "scene_number": i + 1,
                "scene_text": s.dialogue,
                "prompt_en": f"{s.visual_desc}", 
                "image_url": f"/output/{str(project_id)}/assets/image/{filename}",
                "narrative": s.dialogue,
                "focal_point_y": s.focal_point_y,
                "motion_desc": s.motion_desc # [NEW] Store motion description
            })

            # [NEW] Save motion desc to settings for direct access by Autopilot
            if s.motion_desc:
                db.update_project_setting(project_id, f"scene_{i+1}_motion_desc", s.motion_desc)
            
        # 3. 이미지 프롬프트 테이블 일괄 저장
        db.save_image_prompts(project_id, image_prompts)

        # 4. 프로젝트 설정 및 오토파일럿 플래그 업데이트
        db.update_project(project_id, status="queued") # 바로 대기열로!
        db.update_project_setting(project_id, "script", full_script)
        db.update_project_setting(project_id, "auto_plan", False)
        db.update_project_setting(project_id, "app_mode", "shorts") 
        db.update_project_setting(project_id, "auto_tts", 1)      # TTS 자동 생성 활성화
        db.update_project_setting(project_id, "auto_render", 1)   # 렌더링 자동 시작 활성화
        
        # [NEW] 립싱크(Akool) 및 동영상(Wan) 엔진 설정
        if req.use_lipsync:
            db.update_project_setting(project_id, "video_engine", "akool")
            db.update_project_setting(project_id, "all_video", 1) # 모든 장면을 비디오(립싱크)화
        else:
            db.update_project_setting(project_id, "video_engine", "wan") # 기본 모션 엔진
            db.update_project_setting(project_id, "all_video", 1) # [FIX] 웹툰 모드에서는 모든 장면을 비디오(Wan/Motion)화 하도록 강제
        
        # 4. 설정 저장 (립싱크 및 자막 여부)
        db.update_project_setting(project_id, "use_lipsync", req.use_lipsync)
        db.update_project_setting(project_id, "use_subtitles", req.use_subtitles)

        # [NEW] Save Voice Mapping for future consistency
        if req.character_map:
            db.update_project_setting(project_id, "voice_mapping_json", json.dumps(req.character_map, ensure_ascii=False))
        
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
        
        # [CRITICAL] 일괄 분석 시에도 기존 자른 이미지 폴더를 비워서 캐시 꼬임 방지
        if os.path.exists(sliced_base_dir):
            shutil.rmtree(sliced_base_dir)
        os.makedirs(sliced_base_dir, exist_ok=True)
        
        # Temp dir for PSD conversion
        temp_dir = os.path.join(project_dir, "temp_psd_conversion")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        print(f"🚀 [Webtoon Dir] Start analysis for {len(req.files)} files. Project: {req.project_id}")

        layer_trace = [] # Initialize layer_trace for the entire batch
        debug_all_layers = {} # 파일별 레이어 목록
        
        def normalize_name(s):
            if not s: return ""
            # NFC/NFKC 통합
            s = unicodedata.normalize('NFKC', str(s))
            # 공백 및 제어문자 제거, 소문자화 (한글/영문/숫자/일부특수문자 유지)
            s = "".join(c for c in s if not c.isspace() and ord(c) > 31).lower()
            return s
        
        all_scenes = []
        global_scene_counter = 1
        current_context = "" # Initialize context for Gemini
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
                     current_context = script_row["full_script"][-500:] # Last 500 chars (Previous episode context)
            conn.close()
            if current_context:
                print(f"📖 [Webtoon] Loaded context from previous episode: {len(current_context)} chars")
        
        # [NEW] Prepare Voice Options for AI Recommendation
        voice_options_str = None
        try:
            voices = await tts_service.get_elevenlabs_voices()
            if voices:
                v_list = []
                # Limit to top 40 to avoid token overflow
                for v in voices[:40]:
                    labels = v.get('labels', {})
                    # Simplify labels
                    traits = []
                    if 'gender' in labels: traits.append(labels['gender'])
                    if 'age' in labels: traits.append(labels['age'])
                    if 'accent' in labels: traits.append(labels['accent'])
                    if 'description' in labels: traits.append(labels['description']) # Some use description
                    
                    trait_str = ", ".join(traits) if traits else "General"
                    v_list.append(f"- Name: {v['name']} (ID: {v['voice_id']}) - {trait_str}")
                
                voice_options_str = "\n".join(v_list)
                print(f"🎤 [Webtoon] Loaded {len(v_list)} voices for recommendation.")
        except Exception as e:
            print(f"⚠️ Failed to load voices for recommendation: {e}")

        # [NEW] Load Voice Consistency Map ONCE for the batch
        voice_consistency_map = {}
        try:
            p_set = db.get_project_settings(req.project_id) if req.project_id else {}
            if p_set and p_set.get('voice_mapping_json'):
                start_map = json.loads(p_set.get('voice_mapping_json'))
                # Validate format (id vs dict)
                for k, v in start_map.items():
                    if isinstance(v, dict) and "id" in v:
                        voice_consistency_map[k] = v
                    elif isinstance(v, str):
                        # Convert legacy format (id string) to dict
                        voice_consistency_map[k] = {"id": v, "name": "Unknown Voice"}
        except Exception as e:
            print(f"⚠️ Failed to load voice map: {e}")

        for file_path in req.files:
            print(f"  - Processing file: {file_path}")
            if not os.path.exists(file_path):
                print(f"    ⚠️ File NOT found: {file_path}")
                continue
                
            ext = os.path.splitext(file_path)[1].lower()
            analysis_image_path = file_path
            clean_image_path = None
            
            print(f"    Ext: {ext}")
            if ext == '.psd':
                try:
                    from psd_tools import PSDImage
                    import uuid
                    
                    # 1. Full Image (Analysis)
                    psd_ana = PSDImage.open(file_path)
                    full_png_path = os.path.join(temp_dir, f"ana_{uuid.uuid4().hex}.png")
                    comp_ana = psd_ana.composite()
                    if not comp_ana: comp_ana = Image.fromarray(psd_ana.numpy())
                    comp_ana.save(full_png_path)
                    analysis_image_path = full_png_path
                    
                    # PSD인 경우 모든 레이어 구조를 항상 디버그 정보에 포함
                    all_layers_batch = [l.name for l in psd_ana.descendants() if l.name][:50]
                    debug_all_layers[os.path.basename(file_path)] = {
                        "layers": all_layers_batch,
                        "matched": [],
                        "keywords": [],
                        "method": "analysis_only"
                    }

                    # 2. Clean Image (Filtered)
                    clean_image_path = full_png_path # Default
                    if req.psd_exclude_layer:
                        psd_cln = PSDImage.open(file_path) # Fresh open for clean image
                        raw_keywords = [k.strip() for k in re.split(r'[,，\s\n]+', req.psd_exclude_layer) if k.strip()]
                        keywords = [normalize_name(k) for k in raw_keywords]
                        
                        found_any = False
                        keywords_debug = keywords
                        matched_trace = []
                        
                        for layer in psd_cln.descendants():
                            if not layer.name: continue
                            name_norm = normalize_name(layer.name)
                            if any(k in name_norm for k in keywords):
                                if layer.visible:
                                    print(f"👉 [PSD Dir Filter] Hiding: '{layer.name}' (norm: {name_norm})")
                                    layer.visible = False
                                    layer_trace.append(f"{os.path.basename(file_path)}: {layer.name}") 
                                    matched_trace.append(layer.name)
                                    # 하위 레이어까지 재귀적으로 강제 은닉
                                    if hasattr(layer, 'descendants'):
                                        for child in layer.descendants():
                                            child.visible = False
                                    found_any = True
                        
                        if found_any:
                            clean_png_path = os.path.join(temp_dir, f"cln_{uuid.uuid4().hex}.png")
                            try:
                                comp_cln = psd_cln.composite()
                            except:
                                comp_cln = None

                            method = "composite"
                            if not comp_cln:
                                method = "manual_merge"
                                print(f"   [PSD Dir] Main composite failed for {file_path}. Manual Merge started...")
                                # 흰색 배경으로 시작 (255 alpha)
                                canvas = Image.new("RGBA", psd_cln.size, (255, 255, 255, 255))
                                for l in psd_cln:
                                    if l.visible:
                                        try:
                                            l_img = l.composite()
                                            if l_img:
                                                canvas.alpha_composite(l_img.convert("RGBA"))
                                        except:
                                            pass
                                comp_cln = canvas.convert("RGB")
                                
                            if comp_cln.mode != 'RGB': comp_cln = comp_cln.convert('RGB')
                            comp_cln.save(clean_png_path)
                            clean_image_path = clean_png_path
                            debug_all_layers[os.path.basename(file_path)] = {
                                "layers": [l.name for l in psd_cln.descendants() if l.name][:50],
                                "matched": matched_trace,
                                "keywords": keywords_debug,
                                "method": method
                            }
                        else:
                            print(f"   [PSD Dir] No layer matched from {keywords} in {file_path}")
                            all_names = [l.name for l in psd_cln.descendants() if l.name][:20]
                            debug_all_layers[os.path.basename(file_path)] = {
                                "layers": all_names,
                                "matched": [],
                                "keywords": keywords,
                                "method": "none_matched"
                            }
                            clean_image_path = full_png_path
                    else:
                         clean_image_path = full_png_path
                        
                except Exception as e:
                    print(f"Failed to process PSD {file_path}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            else: # For non-PSD files, analysis and clean image are the same
                clean_image_path = file_path
                debug_all_layers[os.path.basename(file_path)] = {
                    "layers": ["(Not a PSD file - flattened image)"],
                    "matched": [],
                    "keywords": [],
                    "method": "flattened_image"
                }
            
            # --- 2. Slicing ---
            print(f"    ✂️ Slicing: {analysis_image_path}")
            cuts = slice_webtoon(analysis_image_path, sliced_base_dir, start_idx=global_scene_counter, clean_image_path=clean_image_path)
            print(f"    ✅ Found {len(cuts)} scenes in this file.")
            
            # [CRITICAL FIX] 글로벌 카운터 업데이트 - 이 작업이 없으면 다음 파일이 이전 파일을 덮어씀
            global_scene_counter += len(cuts)
            
            # --- 3. Analysis with dynamic context tracking ---
            for cut_info in cuts:
                v_path = cut_info["video"]
                a_path = cut_info["analysis"]
                
                print(f"    🔍 Analyzing scene {len(all_scenes) + 1}...")
                print(f"      - Context length: {len(current_context) if current_context else 0}")
                print(f"      - Voice options available: {'Yes' if voice_options_str else 'NO'}")
                try:
                    # [NEW] Prepare Known Characters context
                    known_chars_str = ""
                    if voice_consistency_map:
                        known_chars_list = []
                        for name, data in voice_consistency_map.items():
                            voice_name = data.get("name", "Unknown Voice")
                            known_chars_list.append(f"- {name} (Voice: {voice_name})")
                        if known_chars_list:
                            known_chars_str = "\n[KNOWN CHARACTERS IN THIS EPISODE]\n" + "\n".join(known_chars_list) + "\nTry to reuse these character names if they appear.\n"
                    
                    final_context = (current_context or "") + known_chars_str

                    # Pass running context to Gemini (Analyze the one WITH text)
                    analysis = await gemini_service.analyze_webtoon_panel(a_path, context=final_context, voice_options=voice_options_str)
                    print(f"DEBUG: Analyzed scene. Keys present: {list(analysis.keys())}")
                    print(f"DEBUG: audio_direction: {analysis.get('audio_direction')}")
                    print(f"DEBUG: voice_recommendation: {analysis.get('voice_recommendation')}")

                    
                    # Skip meaningless panels (copyright, blank, logos, etc.)
                    is_meaningless = analysis.get('is_meaningless') is True
                    dialogue = analysis.get('dialogue', '').strip()
                    visual = analysis.get('visual_desc', '').lower()
                    
                    # Safer keyword filtering
                    copyright_keywords = [
                        "저작권", "무단 전재", "illegal copy", "all rights reserved", "무단 복제", "RK STUDIO", 
                        "studio", "webtoon", "episode", "next time", "to be continued", "copyright", "scan", "watermark"
                    ]
                    
                    # 추가적인 시각적 판별 (완전 어두운 배경 등)
                    if "completely dark" in visual or "completely black" in visual or "blank panel" in visual:
                        if not dialogue: # 대사가 없으면 진짜 짜투리
                            is_meaningless = True

                    if any(k in dialogue for k in copyright_keywords) and len(dialogue) < 150:
                        is_meaningless = True
                    
                    if is_meaningless:
                        print(f"Skipping meaningless panel (Visual: {visual})")
                        continue

                    import time
                    ts = int(time.time())
                    all_scenes.append({
                        "scene_number": len(all_scenes) + 1,
                        "image_path": v_path,
                        "image_url": f"/api/media/view?path={urllib.parse.quote(v_path)}&t={ts}",
                        "analysis": analysis,
                        "focal_point_y": analysis.get("focal_point_y", 0.5)
                    })
                    
                    print(f"    ✅ Scene {len(all_scenes)} analysis complete.")

                except Exception as e:
                    print(f"Gemini failed for {a_path}: {e}")
                    import time
                    ts = int(time.time())
                    all_scenes.append({
                        "scene_number": len(all_scenes) + 1,
                        "image_path": v_path,
                        "image_url": f"/api/media/view?path={urllib.parse.quote(v_path)}&t={ts}",
                        "analysis": {"dialogue": "", "character": "Unknown", "visual_desc": "Analysis failed", "atmosphere": "Error"}
                    })
            
            # Clean up temp PNGs
            for p in [analysis_image_path, clean_image_path]:
                if p and p.startswith(temp_dir) and os.path.exists(p):
                    try: os.remove(p)
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
        
        # 2. Finalize all scenes using the enriched map
        for sc in all_scenes:
            # [REF ACTOR] Centralized finalization (Character Normalization, Consistency, Fallbacks)
            finalize_scene_analysis(sc, char_voice_map, eleven_voices)
            
            # [NEW] Persist map updates back to DB (important for consistency across project)
            norm_char = sc['analysis'].get('character')
            if norm_char and norm_char != "Unknown":
                char_voice_map[norm_char] = {"id": sc['voice_id'], "name": sc['voice_name']}
                try:
                    db.update_project_setting(req.project_id, "voice_mapping_json", json.dumps(char_voice_map, ensure_ascii=False))
                except: pass

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
            "character_map": char_voice_map,
            "layer_debug": {
                "trace": layer_trace,
                "all_files": debug_all_layers
            }
        }
    except Exception as e:
        print(f"Analyze Directory Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

@router.post("/save-analysis")
async def save_webtoon_analysis(
    project_id: int = Body(...),
    scenes: List[Dict] = Body(...)
):
    """분석 결과(장면) 저장"""
    try:
        scenes_json = json.dumps(scenes, ensure_ascii=False)
        db.update_project_setting(project_id, "webtoon_scenes_json", scenes_json)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/get-analysis/{project_id}")
async def get_webtoon_analysis(project_id: int):
    """저장된 분석 결과(장면) 조회 (유실 데이터 보정 포함)"""
    try:
        settings = db.get_project_settings(project_id)
        if settings and settings.get("webtoon_scenes_json"):
            scenes = json.loads(settings["webtoon_scenes_json"])
            
            # [HEAL] 보이스 일관성 맵 로드
            char_voice_map = {}
            if settings.get("voice_mapping_json"):
                try: char_voice_map = json.loads(settings["voice_mapping_json"])
                except: pass
            
            # ElevenLabs 데이터 (보정용)
            try: eleven_voices = await tts_service.get_elevenlabs_voices()
            except: eleven_voices = []
            
            # 로드된 모든 장면에 대해 일관성 및 유실 데이터 보정 실행
            for sc in scenes:
                # [REF ACTOR] Centralized finalization (Character Normalization, Consistency, Fallbacks)
                finalize_scene_analysis(sc, char_voice_map, eleven_voices)
                
                # 맵 업데이트 (새로운 캐릭터 발견 시 대비)
                norm_char = sc['analysis'].get('character')
                if norm_char and norm_char != "Unknown":
                    char_voice_map[norm_char] = {"id": sc['voice_id'], "name": sc['voice_name']}

            return {"status": "ok", "scenes": scenes}
        return {"status": "ok", "scenes": []}
    except Exception as e:
        print(f"Get Analysis Error: {e}")
        return {"status": "error", "message": str(e)}
