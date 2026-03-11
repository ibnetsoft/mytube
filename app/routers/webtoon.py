from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import os
import shutil
import json
import re
import io
import time
import httpx
import urllib.parse
from PIL import Image
import numpy as np
from typing import List, Dict, Optional

from config import config
import database as db
from services.gemini_service import gemini_service
from services.autopilot_service import autopilot_service
from services.tts_service import tts_service
from services.auth_service import auth_service
from services.replicate_service import replicate_service
from services.webtoon_service import (
    analyze_directory_service, automate_webtoon_service, fetch_webtoon_url_service,
    generate_single_scene_video_service, finalize_scene_analysis
)
from app.models.webtoon import (
    WebtoonScene, ScanRequest, AnalyzeDirRequest, 
    WebtoonAutomateRequest, WebtoonPlanRequest, LocalImageRequest,
    WebtoonSingleSceneRequest
)
from services.video_builder_service import (
    analyze_scenes_for_director, get_png_files_from_folder
)


router = APIRouter(prefix="/webtoon", tags=["Webtoon Studio"])
templates = Jinja2Templates(directory="templates")


# ✅ 공유 app_state에서 translator 가져오기 (main.py와 동일한 인스턴스)
from services import app_state as _app_state

templates.env.globals['membership'] = auth_service.get_membership()
templates.env.globals['is_independent'] = auth_service.is_independent()

@router.get("", response_class=HTMLResponse)
async def webtoon_studio_page(request: Request):
    """웹툰 스튜디오 메인 페이지"""
    # 매 요청마다 최신 translator를 컨텍스트에 직접 주입
    # Jinja2에서 컨텍스트 변수 > env.globals 이므로 항상 올바른 언어 반영
    tr = _app_state.get_translator()
    t_func = tr.t if tr else (lambda k: k)
    lang = tr.lang if tr else 'ko'
    return templates.TemplateResponse("pages/webtoon_studio.html", {
        "request": request,
        "title": "Webtoon Studio",
        "page": "webtoon-studio",
        "t": t_func,
        "current_lang": lang,
    })

@router.post("/fetch-url")
async def fetch_webtoon_url(
    project_id: int = Form(...),
    url: str = Form(...)
):
    """네이버 웹툰 URL에서 이미지를 크롤링하여 저장"""
    try:
        return await fetch_webtoon_url_service(project_id, url)
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Fetch URL error: {e}")
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
                "url": f"/api/media/v?path={urllib.parse.quote(png_path)}"
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
                "url": f"/api/media/v?path={urllib.parse.quote(file_path)}"
            }
            
    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

@router.post("/replace-scene-image")
async def replace_scene_image(
    project_id: int = Form(...),
    scene_index: int = Form(...),
    file: UploadFile = File(...)
):
    """특정 씬의 이미지를 사용자가 업로드한 파일로 교체"""
    try:
        project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
        replaced_dir = os.path.join(project_dir, "webtoon_replaced")
        os.makedirs(replaced_dir, exist_ok=True)
        
        import time
        filename = f"replaced_{scene_index}_{int(time.time())}_{file.filename}"
        file_path = os.path.join(replaced_dir, filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        ts = int(time.time())
        image_url = f"/api/media/v?path={urllib.parse.quote(file_path)}&t={ts}"

        # [NEW] Persist replacement in DB immediately
        settings = db.get_project_settings(project_id)
        if settings and settings.get("webtoon_scenes_json"):
            scenes = json.loads(settings["webtoon_scenes_json"])
            if 0 <= scene_index < len(scenes):
                scenes[scene_index]["image_path"] = file_path
                scenes[scene_index]["image_url"] = image_url
                # Also reset specific overrides if needed (optional)
                db.update_project_setting(project_id, "webtoon_scenes_json", json.dumps(scenes, ensure_ascii=False))
                print(f"✅ [Persistence] Scene {scene_index} image updated in DB.")

        return {
            "status": "ok",
            "image_path": file_path,
            "image_url": image_url
        }
    except Exception as e:
        print(f"Replace image error: {e}")
        raise HTTPException(500, str(e))

@router.post("/classify-scenes")
async def classify_webtoon_scenes(
    scenes: List[Dict] = Body(...),
    project_id: int = Body(...)
):
    """장면별 이미지 유형(Type 1-6) 자동 분류"""
    try:
        classified_scenes = []
        for i, scene in enumerate(scenes):
            analysis = scene.get('analysis', {})
            visual_desc = str(analysis.get('visual_desc', '')).lower()
            img_path = scene.get('image_path')
            
            # Default Type
            scene_type = "3" # Small/Regular
            type_label = "Type 3: 일반/작은 컷"
            
            # 1. 이미지 비율 기반 물리적 분류
            if img_path and os.path.exists(img_path):
                try:
                    with Image.open(img_path) as img:
                        w, h = img.size
                        ratio = w / h
                        
                        if ratio < 0.8: # 세로로 김 (기준 완화)
                            scene_type = "1"
                            type_label = "Type 1: 세로형 컷 (패닝)"
                        elif ratio > 1.0: # 가로로 조금이라도 넓으면 Type 2로 간주
                            scene_type = "2"
                            type_label = "Type 2: 가로형 컷 (팬핑 권장)"
                except: pass
            
            # 2. 내용 기반 보정 (키워드 매칭)
            if any(x in visual_desc for x in ["battle", "fight", "falling", "epic", "space", "sky", "chapel"]):
                if scene_type == "1": type_label += " (전투/공간)"
            
            if any(x in visual_desc for x in ["close-up", "portrait", "eyes", "talking", "dialogue"]):
                if scene_type != "1":
                    scene_type = "2"
                    type_label = "Type 2: 클로즈업/대화"

            # 3. 레이어 정보가 있으면 Type 5 (Depth) 고려 가능 (여기서는 기본 1-3 위주)
            
            scene['scene_type'] = scene_type
            scene['type_label'] = type_label
            classified_scenes.append(scene)
            
        return {"status": "ok", "scenes": classified_scenes}
    except Exception as e:
        print(f"Classification error: {e}")
        raise HTTPException(500, str(e))

@router.post("/analyze")
async def analyze_webtoon(
    project_id: int = Form(...),
    filename: str = Form(...),
    psd_exclude_layer: Optional[str] = Form(None),
    skip_ai: Optional[bool] = Form(False)
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
        if ext == '.psd':
            from psd_tools import PSDImage
            import uuid
            
            try:
                # 1. 분석용 (전체 레이어)
                psd_ana = PSDImage.open(webtoon_path)
                ana_png = os.path.join(sliced_dir, f"full_{uuid.uuid4().hex}.png")
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
                        cln_png = os.path.join(sliced_dir, f"cln_{uuid.uuid4().hex}.png")
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
        
        # Temp PNG cleanup removed to keep files available for UI display
        
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
            
            if skip_ai:
                # [NEW] AI 분석 생략 모드 (Review first)
                scenes.append({
                    "scene_number": i + 1,
                    "image_path": video_path,
                    "analysis_path": analysis_path, # 나중 분석을 위해 저장
                    "original_image_path": clean_image_path,
                    "original_image_url": f"/api/media/v?path={urllib.parse.quote(clean_image_path)}&t={ts}",
                    "image_url": f"/api/media/v?path={urllib.parse.quote(video_path)}&t={ts}",
                    "analysis": {
                        "dialogue": "", "character": "Unknown", "visual_desc": "Waiting for analysis...", 
                        "atmosphere": "Normal", "is_meaningless": False
                    },
                    "voice_id": "nPczCjzI2devNBz1zQrb", # Brian default
                    "voice_name": "Brian"
                })
                continue
            
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

                scene = {
                    "scene_number": len(scenes) + 1,
                    "image_path": video_path,
                    "original_image_path": clean_image_path,  # [NEW] Full original
                    "original_image_url": f"/api/media/v?path={urllib.parse.quote(clean_image_path)}&t={ts}",
                    "image_url": f"/api/media/v?path={urllib.parse.quote(video_path)}&t={ts}",
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
                    "original_image_path": clean_image_path,
                    "original_image_url": f"/api/media/v?path={urllib.parse.quote(clean_image_path)}&t={ts}",
                    "image_url": f"/api/media/v?path={urllib.parse.quote(video_path)}&t={ts}",
                    "analysis": {"dialogue": "", "character": "Unknown", "visual_desc": "Error during analysis", "atmosphere": "Error"}
                })
        
        # [NEW] Critical Persistence: Save scenes to DB
        try:
            db.update_project_setting(project_id, "webtoon_scenes_json", json.dumps(scenes, ensure_ascii=False))
            print(f"✅ [Persistence] Saved {len(scenes)} scenes to project {project_id}")
        except Exception as se:
            print(f"⚠️ [Persistence] Failed to auto-save scenes: {se}")

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




@router.post("/generate-plan")
async def generate_webtoon_plan(req: WebtoonPlanRequest):
    """장면별 대사/묘사를 바탕으로 비디오 제작 기획서(기술 사양) 생성"""
    try:
        # [NEW] 만약 분석 데이터가 비어있다면, 기획서 생성 전 즉시 분석 수행
        needs_analysis = any(
            not s.get('analysis', {}).get('visual_desc') or 
            s.get('analysis', {}).get('visual_desc') == "Waiting for analysis..."
            for s in req.scenes
        )
        
        updated_scenes = req.scenes
        if needs_analysis:
            print("🚀 [On-Demand Analysis] Starting scene analysis before planning...")
            # 보이스 일관성 맵 로드 (필수)
            char_voice_map = {}
            eleven_voices = []
            try:
                settings = db.get_project_settings(req.project_id) if req.project_id else {}
                if settings and settings.get('voice_mapping_json'):
                    char_voice_map = json.loads(settings['voice_mapping_json'])
                eleven_voices = await tts_service.get_elevenlabs_voices()
            except: pass

            context = ""
            for i, s in enumerate(updated_scenes):
                # 분석이 필요한 경우만 수행
                if not s.get('analysis', {}).get('visual_desc') or s.get('analysis', {}).get('visual_desc') == "Waiting for analysis...":
                    # analysis_path가 없으면 image_path 사용 (보수적)
                    target_path = s.get('analysis_path') or s.get('image_path')
                    if target_path and os.path.exists(target_path):
                        try:
                            ana = await gemini_service.analyze_webtoon_panel(target_path, context=context)
                            s['analysis'] = ana
                            
                            # 일관성 부여
                            finalize_scene_analysis(s, char_voice_map, eleven_voices)
                            
                            if ana.get('dialogue'):
                                context = f"Last seen: {ana.get('character')} said \"{ana.get('dialogue')[:50]}\"."
                                
                            print(f"   - Scene {i+1} analyzed.")
                        except Exception as e:
                            print(f"   - Scene {i+1} analysis failed: {e}")
            
            # 분석 완료된 데이터를 DB에 저장 (유실 방지)
            try:
                db.update_project_setting(req.project_id, "webtoon_scenes_json", json.dumps(updated_scenes, ensure_ascii=False))
                db.update_project_setting(req.project_id, "voice_mapping_json", json.dumps(char_voice_map, ensure_ascii=False))
            except: pass

        # 이제 기획서 생성
        plan = await gemini_service.generate_webtoon_plan(updated_scenes)
        
        # [FORCE OVERRIDE] 물리적 비율에 따른 강제 보정 (AI 기획이 줌인이어도 팬핑으로 교체)
        if plan and "scene_specifications" in plan:
            for spec in plan["scene_specifications"]:
                try:
                    # scene_number 타입 안전하게 매칭 (int vs None 방지)
                    s_num_raw = spec.get('scene_number')
                    if s_num_raw is None: continue
                    s_num = int(s_num_raw)
                    
                    # original_s 매칭 시에도 None 체크 추가
                    original_s = next((s for s in updated_scenes if int(s.get('scene_number') or -1) == s_num), None)
                    
                    if original_s:
                        img_path = original_s.get('image_path')
                        physically_wide = False
                        if img_path and os.path.exists(img_path):
                            with Image.open(img_path) as img:
                                w, h = img.size
                                # 가로 비율이 1.1만 넘어도 강제로 Pan Right 전략 사용
                                if w / h > 1.1: physically_wide = True

                        # [핵심] 가로가 길면 AI 대답 상관없이 'pan_right'로 덮어쓰기
                        if physically_wide or str(original_s.get('scene_type')) == "2":
                            print(f"   - [STRICT OVERRIDE] Scene {s_num} (Wide ratio) forced to pan_right from {spec.get('effect')}")
                            spec['effect'] = "pan_right"
                            spec['engine'] = "akool"
                            # 프롬프트에도 가로 이동 키워드 강제 주입
                            if "zoom" in str(spec.get('motion', '')).lower():
                                spec['motion'] = str(spec.get('motion', '')).lower().replace("zoom", "horizontal pan").capitalize()
                            if "pan" not in str(spec.get('motion', '')).lower():
                                spec['motion'] += ". Camera pans right horizontally."
                except Exception as e:
                    print(f"   - [Override Error] Scene spec processing failed: {e}")
                
                # 엔진 무조건 akool 우선
                if not spec.get('engine') or spec.get('engine') == 'wan':
                    spec['engine'] = 'akool'

        # [NEW] Save Plan to Project Settings
        try:
            plan_json = json.dumps(plan, ensure_ascii=False)
            db.update_project_setting(req.project_id, "webtoon_plan_json", plan_json)
        except Exception as se:
            print(f"Failed to save plan: {se}")

        return {"status": "ok", "plan": plan, "scenes": updated_scenes if needs_analysis else None}
    except Exception as e:
        print(f"Plan Gen Error: {e}")
        raise HTTPException(500, str(e))

        raise HTTPException(500, str(e))

@router.post("/generate-scene-video")
async def generate_scene_video(req: WebtoonSingleSceneRequest):
    """특정 장면 하나만 영상을 생성"""
    try:
        return await generate_single_scene_video_service(req.project_id, req.scene_index, req.scene)
    except Exception as e:
        print(f"Generate scene video error: {e}")
        raise HTTPException(500, str(e))

@router.post("/scan")
async def scan_directory(req: ScanRequest):
    """로컬 디렉토리의 웹툰 파일 스캔"""
    print(f"📂 [Scan] Received request to scan: {req.path}")
    if not os.path.exists(req.path):
        print(f"❌ [Scan] Path does not exist: {req.path}")
        return JSONResponse({"status": "error", "error": f"Path does not exist: {req.path}"}, status_code=404)
    
    files = []
    try:
        # 파일명 기준 정렬 (1화_001, 1화_002 순서 보장)
        file_list = sorted(os.listdir(req.path))
        print(f"🔍 [Scan] Found {len(file_list)} items in directory.")
        
        valid_exts = ['.psd', '.png', '.jpg', '.jpeg', '.webp']
        for f in file_list:
            full_path = os.path.join(req.path, f)
            if os.path.isfile(full_path):
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    files.append({
                        "filename": f,
                        "path": full_path,
                        "size": os.path.getsize(full_path)
                    })
        print(f"✅ [Scan] Returning {len(files)} valid image/PSD files.")
    except Exception as e:
         print(f"❌ [Scan] Error during scan: {str(e)}")
         return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
    
    return {"status": "ok", "files": files}

@router.post("/analyze-dir")
async def analyze_directory(req: AnalyzeDirRequest):
    """로컬 파일 리스트를 입력받아 일괄 분석 (Direct Access)"""
    try:
        return await analyze_directory_service(req.project_id, req.files, req.psd_exclude_layer)
    except Exception as e:
        print(f"Analyze Directory Error: {e}")
        raise HTTPException(500, str(e))

@router.post("/save-analysis")
async def save_webtoon_analysis(
    project_id: int = Body(...),
    scenes: List[Dict] = Body(...),
    webtoon_source_dir: Optional[str] = Body(None),
    psd_exclude_layer: Optional[str] = Body(None)
):
    """분석 결과(장면) 저장"""
    try:
        scenes_json = json.dumps(scenes, ensure_ascii=False)
        db.update_project_setting(project_id, "webtoon_scenes_json", scenes_json)
        
        if webtoon_source_dir is not None:
            db.update_project_setting(project_id, "webtoon_source_dir", webtoon_source_dir)
        if psd_exclude_layer is not None:
            db.update_project_setting(project_id, "psd_exclude_layer", psd_exclude_layer)
        
        # [NEW] Extract and persist voice mapping for consistency
        try:
            voice_map = {}
            for s in scenes:
                char = s.get('analysis', {}).get('character')
                if char and char != "Unknown" and s.get('voice_id'):
                    voice_map[char] = {"id": s.get('voice_id'), "name": s.get('voice_name')}
            if voice_map:
                db.update_project_setting(project_id, "voice_mapping_json", json.dumps(voice_map, ensure_ascii=False))
        except: pass
            
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

            # [NEW] Load Saved Plan & Characters
            plan = None
            if settings.get("webtoon_plan_json"):
                try: plan = json.loads(settings["webtoon_plan_json"])
                except: pass

            characters = []
            try: characters = db.get_project_characters(project_id)
            except: pass

            return {"status": "ok", "scenes": scenes, "plan": plan, "characters": characters, "settings": settings}
        return {"status": "ok", "scenes": []}
    except Exception as e:
        print(f"Get Analysis Error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/optimize-image")
async def optimize_webtoon_image(file: UploadFile = File(...), prompt_type: str = Form(None)):
    """
    Step 1: Webtoon Image Optimization (9:16) - Upload Version
    """
    try:
        contents = await file.read()
        return await process_webtoon_image(io.BytesIO(contents), prompt_type)
    except Exception as e:
        print(f"Error optimizing image (upload): {e}")
        raise HTTPException(500, f"Image optimization failed: {str(e)}")



@router.post("/optimize-local-image")
async def optimize_local_image(request: LocalImageRequest):
    """
    Step 1: Webtoon Image Optimization (9:16) - Local File Version
    """
    try:
        if not os.path.exists(request.file_path):
            raise HTTPException(404, "File not found")
            
        with open(request.file_path, "rb") as f:
            contents = f.read()
            
        return await process_webtoon_image(io.BytesIO(contents))
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error optimizing image (local): {e}")
        raise HTTPException(500, f"Image optimization failed: {str(e)}")


# ─────────────────────────────────────────────────────────────
# PNG 컷 추출 API  (PSD Cutter)
# ─────────────────────────────────────────────────────────────

from pydantic import BaseModel as PydanticBaseModel

class ExtractCutsRequest(PydanticBaseModel):
    input_dir: str
    project_id: Optional[int] = None
    output_dir: Optional[str] = None        # 없으면 input_dir/cuts/ 에 저장
    psd_exclude_layer: Optional[str] = None # PSD 레이어 제외 키워드 (쉼표/공백 구분)

@router.post("/extract-cuts")
async def extract_cuts_endpoint(req: ExtractCutsRequest):
    """
    폴더 내 PSD/PNG/JPG 파일을 자동 분석하여 컷 단위 PNG로 추출.
    psd_exclude_layer: '식자, 대사' 처럼 입력하면 해당 레이어를 제외한 클린본으로 컷 분할.
    이미지를 직접 보여주지 않고 저장 폴더 경로와 파일 목록만 반환.
    """
    try:
        from services.psd_cutter_service import extract_cuts_from_folder

        input_dir = req.input_dir.strip().replace('"', '')
        if not os.path.isdir(input_dir):
            raise HTTPException(400, f"입력 폴더를 찾을 수 없습니다: {input_dir}")

        # output_dir 결정
        if req.output_dir:
            output_dir = req.output_dir.strip().replace('"', '')
        elif req.project_id:
            output_dir = os.path.join(config.OUTPUT_DIR, str(req.project_id), "webtoon_cuts")
        else:
            output_dir = os.path.join(input_dir, "cuts")

        result = extract_cuts_from_folder(
            input_dir, output_dir,
            psd_exclude_layer=req.psd_exclude_layer or None,
        )
        return {"status": "ok", **result}

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@router.post("/extract-cuts-single")
async def extract_cuts_single(
    file_path: str = Body(..., embed=True),
    project_id: Optional[int] = Body(None, embed=True),
    output_dir: Optional[str] = Body(None, embed=True),
):
    """단일 파일에서 컷을 추출합니다."""
    try:
        from services.psd_cutter_service import extract_cuts

        fp = file_path.strip().replace('"', '')
        if not os.path.isfile(fp):
            raise HTTPException(404, f"파일을 찾을 수 없습니다: {fp}")

        if not output_dir:
            if project_id:
                output_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "webtoon_cuts")
            else:
                output_dir = os.path.join(os.path.dirname(fp), "cuts")

        stem = os.path.splitext(os.path.basename(fp))[0]
        cuts = extract_cuts(fp, output_dir, file_prefix=stem, start_idx=1)
        return {"status": "ok", "output_dir": output_dir, "cuts": cuts, "total_cuts": len(cuts)}

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════
# Video Builder — 감독 연출 기획서 생성 API
# ══════════════════════════════════════════════════════════════════════════

@router.post("/video-builder/scan-folder")
async def vb_scan_folder(body: dict = Body(...)):
    """PNG 폴더 스캔 → 이미지 파일 목록 반환"""
    folder = body.get("folder_path", "").strip()
    if not folder or not os.path.isdir(folder):
        raise HTTPException(400, f"폴더를 찾을 수 없습니다: {folder}")
    files = get_png_files_from_folder(folder)
    if not files:
        raise HTTPException(404, "지원 이미지 파일(PNG/JPG)이 없습니다.")
    return {
        "status": "ok",
        "total": len(files),
        "files": [{"filename": os.path.basename(f), "path": f} for f in files]
    }


@router.post("/video-builder/analyze")
async def vb_analyze(body: dict = Body(...)):
    """
    PNG 이미지 목록 + 대본 맥락 → Gemini Vision 분석
    → 감독 연출 기획서(씬별 연출 방향 + AI 영상 프롬프트) 반환
    """
    folder_path = body.get("folder_path", "").strip()
    png_paths = body.get("png_paths", [])   # 직접 경로 지정 시
    script_context = body.get("script_context", "")
    project_id = body.get("project_id")

    # 폴더 지정이면 자동 탐색
    if folder_path and not png_paths:
        png_paths = get_png_files_from_folder(folder_path)

    if not png_paths:
        raise HTTPException(400, "분석할 이미지 파일이 없습니다.")

    # 프로젝트 대본/기획서 자동 참조
    if project_id and not script_context:
        try:
            plan_raw = db.get_project_setting(project_id, "webtoon_plan")
            if plan_raw:
                plan_data = json.loads(plan_raw) if isinstance(plan_raw, str) else plan_raw
                overview = plan_data.get("overall_strategy", "")
                scenes_preview = ""
                for s in plan_data.get("scene_specifications", [])[:5]:
                    scenes_preview += f"씬{s.get('scene_number','?')}: {s.get('rationale','')[:80]}\n"
                script_context = f"{overview}\n{scenes_preview}"
        except Exception as e:
            print(f"[VB] Plan load error: {e}")

    print(f"[VideoBuilder] Analyzing {len(png_paths)} scenes...")
    
    try:
        result = await analyze_scenes_for_director(
            png_paths=png_paths,
            script_context=script_context,
        )
        return {"status": "ok", "plan": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


@router.post("/video-builder/generate")
async def vb_generate(body: dict = Body(...)):
    """
    Scene Builder 체인 영상 생성 (SSE 스트리밍 진행률).
    body: { scenes: [...], output_dir: str, project_id: int }
    → SSE 이벤트로 씬별 진행 상황 스트리밍
    """
    scenes = body.get("scenes", [])
    project_id = body.get("project_id")
    output_dir = body.get("output_dir", "").strip()

    if not scenes:
        raise HTTPException(400, "scenes 목록이 비어있습니다.")

    # 출력 폴더 결정
    if not output_dir:
        import time
        output_dir = os.path.join(config.OUTPUT_DIR, f"vbuilder_{int(time.time())}")
    os.makedirs(output_dir, exist_ok=True)

    from services.video_builder_service import run_scene_builder_chain, concat_scene_videos

    async def event_stream():
        results_store = []
        errors = []

        async def on_progress(scene_id, status, message):
            import json as _json
            data = _json.dumps({"scene_id": scene_id, "status": status, "message": message})
            yield f"data: {data}\n\n"

        # 각 씬 순차 처리 (Scene Builder 체인)
        try:
            # SSE 초기 메시지
            yield f"data: {json.dumps({'status': 'start', 'total': len(scenes), 'message': '영상 생성 시작...'})}\n\n"

            # 실제 생성 — on_progress는 generator라 직접 yield 불가
            # → 결과만 순차 반환 후 최종 전송
            from services.video_builder_service import (
                SceneVideoResult, generate_scene_video_wan,
                generate_scene_video_akool, _blend_frames,
                _extract_last_frame, concat_scene_videos
            )

            last_frame_path = None
            results = []

            for i, scene in enumerate(scenes):
                sid = scene.get("scene_id", i + 1)
                image_path = scene.get("image_path", "")
                prompt = scene.get("motion_prompt", "")

                # 진행 이벤트
                yield f"data: {json.dumps({'status': 'generating', 'scene_id': sid, 'current': i+1, 'total': len(scenes), 'message': f'씬 {sid} 영상 생성 중...'})}\n\n"

                result = SceneVideoResult(scene_id=sid)

                # 시작 이미지 결정
                if last_frame_path and os.path.exists(last_frame_path) and image_path and os.path.exists(image_path):
                    start_image = _blend_frames(last_frame_path, image_path, output_dir, sid)
                elif image_path and os.path.exists(image_path):
                    start_image = image_path
                else:
                    result.status = "skipped"
                    result.error = f"이미지 없음: {image_path}"
                    results.append(result)
                    yield f"data: {json.dumps({'status': 'skipped', 'scene_id': sid, 'current': i+1, 'message': f'씬 {sid} 이미지 없음 — 건너뜀'})}\n\n"
                    continue

                # Wan 시도
                video_path = await generate_scene_video_wan(start_image, prompt, output_dir, sid)
                result.engine = "wan"

                if not video_path:
                    # AKOOL 폴백
                    yield f"data: {json.dumps({'status': 'fallback', 'scene_id': sid, 'current': i+1, 'message': f'씬 {sid} — AKOOL로 전환 중...'})}\n\n"
                    video_path = await generate_scene_video_akool(start_image, prompt, output_dir, sid)
                    result.engine = "akool"

                if video_path and os.path.exists(video_path):
                    result.video_path = video_path
                    result.status = "success"
                    frame = _extract_last_frame(video_path, output_dir, sid)
                    if frame:
                        result.last_frame_path = frame
                        last_frame_path = frame
                    else:
                        last_frame_path = None
                    yield f"data: {json.dumps({'status': 'done', 'scene_id': sid, 'current': i+1, 'engine': result.engine, 'video_path': video_path, 'message': f'씬 {sid} 완료 ({result.engine})'})}\n\n"
                else:
                    result.status = "error"
                    result.error = "Wan + AKOOL 모두 실패"
                    last_frame_path = None
                    errors.append(sid)
                    yield f"data: {json.dumps({'status': 'error', 'scene_id': sid, 'current': i+1, 'message': f'씬 {sid} 생성 실패'})}\n\n"

                results.append(result)

            # 최종 합본
            yield f"data: {json.dumps({'status': 'concat', 'message': '영상 합치는 중...'})}\n\n"
            final_path = await concat_scene_videos(results, output_dir)

            summary = {
                "status": "complete",
                "total": len(scenes),
                "success": sum(1 for r in results if r.status == "success"),
                "errors": errors,
                "final_video": final_path or "",
                "output_dir": output_dir,
                "message": "영상 생성 완료!",
            }
            yield f"data: {json.dumps(summary)}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/video-builder/output/{filename}")
async def vb_serve_video(filename: str):
    """생성된 영상 파일 서빙"""
    safe_name = os.path.basename(filename)  # path traversal 방지
    file_path = os.path.join(config.OUTPUT_DIR, safe_name)
    if not os.path.exists(file_path):
        # output 하위 폴더도 탐색
        for root, dirs, files in os.walk(config.OUTPUT_DIR):
            if safe_name in files:
                file_path = os.path.join(root, safe_name)
                break
    if not os.path.exists(file_path):
        raise HTTPException(404, "파일 없음")
    from fastapi.responses import FileResponse
    return FileResponse(file_path, media_type="video/mp4")
