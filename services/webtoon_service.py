import os
import shutil
import json
import re
import io
import time
import unicodedata
import urllib.parse
import httpx
from PIL import Image
import numpy as np
from typing import List, Dict, Optional, Any
from config import config
import database as db
from services.gemini_service import gemini_service
from services.tts_service import tts_service
from services.replicate_service import replicate_service
from services.video_service import video_service

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
    
    narrator_keywords = ['narrator', 'narration', '내레이션', '해설', 'unknown', 'unknown voice', 'none', '', 'undefined']
    if any(char_lower == kw for kw in narrator_keywords):
        if dialogue:
            norm_char = "내레이션"
        else:
            norm_char = "Unknown"
    else:
        norm_char = raw_char.replace("'", "").replace('"', "")

    # Sync to analysis
    analysis['character'] = norm_char
    
    # 2. Voice ID/Name 배정 (Manual Override Priority 1)
    # [NEW] 우선 scene 루트 필드(사용자 직접 수정 반영)부터 확인
    final_voice_id = str(scene.get('voice_id', '')).strip()
    final_voice_name = str(scene.get('voice_name', '')).strip()
    
    # 만약 루트 필드가 비어있다면, analysis 추천값 가져오기
    if final_voice_id.lower() in ["none", "null", "", "unknown"]:
        suggested_voice = analysis.get('voice_recommendation') or {}
        final_voice_id = str(suggested_voice.get('id', '')).strip()
        final_voice_name = str(suggested_voice.get('name', '')).strip()

    # "None" 문자열 필터링 (다시 한번 정규화)
    if final_voice_id.lower() in ["none", "null", "", "unknown"]: final_voice_id = None
    if final_voice_name.lower() in ["none", "null", "", "unknown voice"]: final_voice_name = None

    # [FIX] 일관성 맵 확인 - 사용자 수동 지정이 없을 때만(None일 때만) 적용
    if not final_voice_id:
        if norm_char != "Unknown" and norm_char in voice_consistency_map:
            existing = voice_consistency_map[norm_char]
            if isinstance(existing, dict):
                final_voice_id = existing.get("id")
                final_voice_name = existing.get("name")
            else:
                final_voice_id = existing # legacy string
    
    # [MODIFIED] 내레이션(Narrator) 일관성 강제: 사용자 지정이 없을 때만 적용
    if norm_char == "내레이션" and not final_voice_id:
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
    
    # [FIX] Flattening with ROBUSTNESS - DO NOT overwrite if root fields already have manual edits/data
    # 사용자가 의도적으로 비운 경우("")를 구분하기 위해 None 체크만 수행하거나, Unknown인 경우만 덮어씀
    if scene.get('visual_desc') is None: scene['visual_desc'] = analysis.get('visual_desc', '')
    if scene.get('character') is None or scene.get('character') == 'Unknown': 
        scene['character'] = analysis.get('character', 'Unknown')
    
    # dialogue/atmosphere/sfx 등은 수동 편집 빈도가 높으므로 더 보수적으로 덮어씀 (None일 때만)
    if scene.get('dialogue') is None: scene['dialogue'] = analysis.get('dialogue', '')
    if scene.get('atmosphere') is None: scene['atmosphere'] = analysis.get('atmosphere', '')
    if scene.get('sound_effects') is None: scene['sound_effects'] = analysis.get('sound_effects', '')
    
    # [NEW] Sync back to analysis for complete internal consistency
    analysis['visual_desc'] = scene['visual_desc']
    analysis['character'] = scene['character']
    analysis['dialogue'] = scene['dialogue']
    analysis['atmosphere'] = scene['atmosphere']
    analysis['sound_effects'] = scene['sound_effects']

    analysis['voice_settings'] = vs
    scene['analysis'] = analysis # Ensure synced
    
    # [NEW] Final "Nuclear" anti-None check for UI
    if str(scene.get('voice_name')).lower() in ["none", "null", "unknown", ""]:
        scene['voice_name'] = "Default Character Voice"
        if "voice_recommendation" not in analysis: analysis["voice_recommendation"] = {}
        analysis['voice_recommendation']['name'] = "Default Character Voice"

    return scene

def slice_webtoon(image_path: str, output_dir: str, min_padding=30, start_idx=1, clean_image_path: str = None, original_full_path: str = None):
    # 중복 체크용 해시 버퍼 초기화
    slice_webtoon._seen_hashes = set()
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
    
    # 중앙 70%만 검사 (좌우 테두리가 검은색 선이거나 노이즈가 넓게 있을 수 있으므로 무시)
    margin = int(w * 0.15)
    if margin < 1: margin = 0
    center_img_np = img_np[:, margin:w-margin] if margin > 0 else img_np
    
    # [RELAXED] 여백 감지 로직 대폭 완화 (노이즈나 옅은 그림자도 여백으로 인정)
    row_stds = np.std(center_img_np, axis=1)
    row_means = np.mean(center_img_np, axis=1)
    
    # 여백 조건: (표준편차가 어느정도 낮음) AND (밝기가 밝거나 어두움)
    # std < 30 (그라데이션이나 노이즈가 있어도 단색 배경이면 인정)
    # mean > 200 (밝은 회색까지 흰색으로 인정) or mean < 60 (짙은 회색까지 검은색으로 인정)
    is_blank = (row_stds < 30) & ((row_means > 200) | (row_means < 60))
    
    # 여백 구간 탐지
    blank_threshold = 5 # 5픽셀 이상의 얇은 선도 여백으로 인정 (칸 사이 좁은 간격 지원)
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
    
    # [DEDUPE] 노이즈로 인해 아주 가깝게 붙어있는 여백들을 하나로 합침
    if len(blank_runs) > 1:
        merged_blanks = []
        curr_s, curr_e = blank_runs[0]
        for next_s, next_e in blank_runs[1:]:
            # 여백 사이의 거리가 30px 미만이면 그냥 하나의 여백 구간으로 취급
            if next_s - curr_e < 30:
                curr_e = next_e
            else:
                merged_blanks.append((curr_s, curr_e))
                curr_s, curr_e = next_s, next_e
        merged_blanks.append((curr_s, curr_e))
        blank_runs = merged_blanks

    # 절단점을 기준으로 조각 범위 결정
    panel_ranges = []
    if not blank_runs:
        panel_ranges = [(0, h)]
    else:
        last_y = 0
        for start, end in blank_runs:
            if start - last_y > 50: # 최소 컷 높이 환원
                panel_ranges.append((last_y, start))
            last_y = end 
            
        if h - last_y > 50:
            panel_ranges.append((last_y, h))

    cuts = []
    for i, (p_start, p_end) in enumerate(panel_ranges):
        cut_full = img.crop((0, p_start, w, p_end))
        
        # [AGGRESSIVE: TIGHT CROP] 컷 내부 상하좌우 모든 종류의 여백을 완전히 제거 (임계값 상향)
        cut_np = np.array(cut_full.convert('L'))
        
        row_stds = np.std(cut_np, axis=1)
        row_means = np.mean(cut_np, axis=1)
        col_stds = np.std(cut_np, axis=0)
        col_means = np.mean(cut_np, axis=0)
        
        # [REFINED] 더욱 공격적으로 크롭: 
        # std < 50 (노이즈 더 많이 허용) 
        # mean >= 180 or <= 90 (더 넓은 밝기 범위를 여백으로 간주 - 특히 검은색 테두리 감지 강화)
        is_bg_row = (row_stds < 50) & ((row_means >= 180) | (row_means <= 90))
        is_bg_col = (col_stds < 65) & ((col_means >= 170) | (col_means <= 100))
        
        valid_rows = ~is_bg_row
        valid_cols = ~is_bg_col
        
        if not np.any(valid_rows) or not np.any(valid_cols):
            continue
            
        rmin, rmax = np.where(valid_rows)[0][[0, -1]]
        cmin, cmax = np.where(valid_cols)[0][[0, -1]]
        
        # 상하좌우 여백 없이 완벽하게 타이트하게 2차 크롭
        cmin = max(0, cmin)
        cmax = min(w, cmax)
        rmin = max(0, rmin)
        rmax = min(p_end - p_start, rmax)
        
        cut_full = cut_full.crop((cmin, rmin, cmax, rmax))
        
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
        # [DEDUPE: CONTENT-BASED] 잘라낸 결과물이 이전과 정확히 똑같다면 중복으로 간주하고 건너뜀
        # (이미지 데이터 일부를 해싱하여 비교)
        import hashlib
        # 속도를 위해 중앙 부분 일부만 샘플링해서 해시 생성
        sample_data = np.array(cut_full.resize((64, 64), Image.NEAREST)).tobytes()
        content_hash = hashlib.md5(sample_data).hexdigest()
        
        if not hasattr(slice_webtoon, "_seen_hashes"):
            slice_webtoon._seen_hashes = set()
            
        if content_hash in slice_webtoon._seen_hashes:
            print(f"      - Skipping duplicate content panel (hash={content_hash})")
            continue
        slice_webtoon._seen_hashes.add(content_hash)

        # [OPTIMIZED] Resize for Vision AI (Gemini doesn't need 8MB images)
        max_dim = 1280
        w_cut, h_cut = cut_full.size
        cut_full_resised = cut_full # Default
        if w_cut > max_dim or h_cut > max_dim:
            if w_cut > h_cut:
                new_w = max_dim
                new_h = int(h_cut * (max_dim / w_cut))
            else:
                new_h = max_dim
                new_w = int(w_cut * (max_dim / h_cut))
            cut_full_resised = cut_full.resize((new_w, new_h), Image.LANCZOS)
        
        # Reset hash buffer for new function calls if this is the start
        if len(cuts) == 0:
            pass # We should actually reset hash buffer outside or check if loop just started
            # But since it's a function property, let's reset it at the top of the function.

            
        current_idx = start_idx + len(cuts)
        
        # 파일 저장 (분석용 - 용량 축소)
        analysis_filename = f"scene_{current_idx:03d}_ana.jpg"
        analysis_path = os.path.join(output_dir, analysis_filename)
        cut_full_resised.save(analysis_path, "JPEG", quality=85) # Quality 85 is enough
        
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
            "analysis": analysis_path,
            "original": original_full_path or clean_image_path or image_path 
        })
                
    if not cuts:
         print("⚠️ No cuts found after slicing. Fallback to using the whole image.")
         # 전체 이미지를 하나로 저장해서라도 반환
         full_ana_path = os.path.join(output_dir, "scene_001_ana.jpg")
         img.save(full_ana_path, "JPEG")
         cuts.append({"video": full_ana_path, "analysis": full_ana_path})
         
    # [NEW] AI 기반 파이프라인 1단계: Auto-crop (검은색 테두리 등 여백 제거)
    video_paths = []
    for c in cuts:
        if "video" in c and os.path.exists(c["video"]):
            # 원본 보존 없이 바로 덮어쓰기 (용량 절약 및 일관성)
            video_service.auto_crop_image(c["video"])
            video_paths.append(c["video"])
            
    # [DISABLED] AI 기반 파이프라인 2단계: 연속 씬 합성 (사용자 요청으로 개별 컷 유지)
    # if video_paths:
    #     merged_video_paths = set(video_service.auto_merge_continuous_images(video_paths))
    #     final_cuts = []
    #     for c in cuts:
    #         if "video" in c and c["video"] in merged_video_paths:
    #             c["analysis"] = c["video"]
    #             final_cuts.append(c)
    #     cuts = final_cuts
        
    # [NEW] AI 기반 파이프라인 3단계: 9:16 최적화 (가로면 1080px 크롭, 세로면 1080px 피팅 및 스크롤용 유지)
    for c in cuts:
        if "video" in c and os.path.exists(c["video"]):
            video_service.fit_image_to_916(c["video"])
         
    return cuts

async def process_webtoon_image(img_io, prompt_type=None):
    """Core Logic for Webtoon Image Optimization"""
    try:
        img = Image.open(img_io).convert("RGB")
    except Exception:
        raise Exception("Invalid image file")
        
    width, height = img.size
    aspect_ratio = width / height
    
    # 2. Target Dimensions (9:16)
    TARGET_W, TARGET_H = 1080, 1920
    target_ar = TARGET_W / TARGET_H
    
    # 3. Create Canvas (Black background)
    canvas = Image.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
    mask = Image.new("L", (TARGET_W, TARGET_H), 255) # Default: All White (Inpaint Everything)
    
    # 4. Resize & Paste Logic
    if aspect_ratio > target_ar:
        # Case 1: Wider (Horizontal or Standard Vertical) -> Fit Width
        new_w = TARGET_W
        new_h = int(height * (TARGET_W / width))
        resized_img = img.resize((new_w, new_h), Image.LANCZOS)
        
        # Center Vertically
        y_offset = (TARGET_H - new_h) // 2
        canvas.paste(resized_img, (0, y_offset))
        
        # Mask
        mask_draw = Image.new("L", (new_w, new_h), 0) # Black (Keep)
        mask.paste(mask_draw, (0, y_offset))
        
        # Classification
        cut_type = "horizontal" if aspect_ratio > 0.8 else "vertical_wide"

    else:
        # Case 2: Taller (Ultra Vertical) -> Fit Height
        new_h = TARGET_H
        new_w = int(width * (TARGET_H / height))
        resized_img = img.resize((new_w, new_h), Image.LANCZOS)
        
        # Center Horizontally
        x_offset = (TARGET_W - new_w) // 2
        canvas.paste(resized_img, (x_offset, 0))
        
        # Mask
        mask_draw = Image.new("L", (new_w, new_h), 0)
        mask.paste(mask_draw, (x_offset, 0))
        
        cut_type = "vertical"

    # 5. Prepare Prompt based on Type
    if cut_type == "horizontal" or cut_type == "vertical_wide":
        # Horizontal (Wide) Logic
        default_horiz = (
            "Expand background vertically to fit 9:16, keep characters unchanged, "
            "match original lighting and color tone, natural environment continuation, "
            "high detail, static image, no motion, webtoon style, high resolution, " 
            "seamless extension"
        )
        prompt = db.get_global_setting("webtoon_horizontal_prompt", default_horiz)
    else:
        # Vertical Logic
        default_vert = (
            "Preserve full original composition, fit into 9:16 vertical canvas, "
            "no distortion, extend background naturally if needed, "
            "maintain original webtoon art style, high resolution, clean edges, "
            "no motion, no animation, static illustration"
        )
        prompt = db.get_global_setting("webtoon_vertical_prompt", default_vert)
        
    # 6. Save Canvas & Mask to Buffer for Upload
    canvas_buffer = io.BytesIO()
    canvas.save(canvas_buffer, format="PNG")
    canvas_buffer.seek(0)
    
    mask_buffer = io.BytesIO()
    mask.save(mask_buffer, format="PNG")
    mask_buffer.seek(0)
    
    # 7. Call Replicate (Outpainting)
    print(f"🎨 [Webtoon] Optimizing Image ({cut_type}): {width}x{height} -> 1080x1920")
    
    result_url = await replicate_service.outpaint_image(
        canvas_buffer, 
        mask_buffer, 
        prompt
    )
    
    if not result_url:
        raise Exception("Image generation failed (No URL returned)")
        
    return {
        "status": "success",
        "original_url": None, 
        "optimized_url": result_url,
        "type": cut_type,
        "prompt_used": prompt
    }

async def analyze_directory_service(project_id: int, files: List[str], psd_exclude_layer: Optional[str] = None):
    """로컬 파일 리스트를 일괄 분석하는 비즈니스 로직"""
    project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
    sliced_base_dir = os.path.join(project_dir, "webtoon_sliced")
    
    if os.path.exists(sliced_base_dir):
        shutil.rmtree(sliced_base_dir)
    os.makedirs(sliced_base_dir, exist_ok=True)
    
    temp_dir = os.path.join(project_dir, "temp_psd_conversion")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    db.update_project(project_id, status="processing")
    print(f"🚀 [Webtoon Service] Start analysis for {len(files)} files. Project: {project_id}")

    layer_trace = []
    debug_all_layers = {}
    
    def normalize_name(s):
        if not s: return ""
        s = unicodedata.normalize('NFKC', str(s))
        s = "".join(c for c in s if not c.isspace() and ord(c) > 31).lower()
        return s
    
    all_scenes = []
    global_scene_counter = 1
    current_context = ""
    current_project = db.get_project(project_id)
    if current_project and current_project.get("topic"):
        topic = current_project["topic"]
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE topic = ? AND id != ? ORDER BY id DESC LIMIT 1", (topic, project_id))
        row = cursor.fetchone()
        if row:
            prev_id = row["id"]
            cursor.execute("SELECT full_script FROM scripts WHERE project_id = ?", (prev_id,))
            script_row = cursor.fetchone()
            if script_row and script_row["full_script"]:
                 current_context = script_row["full_script"][-500:] 
        conn.close()
    
    voice_options_str = None
    try:
        voices = await tts_service.get_elevenlabs_voices()
        if voices:
            v_list = []
            for v in voices[:40]:
                labels = v.get('labels', {})
                traits = []
                if 'gender' in labels: traits.append(labels['gender'])
                if 'age' in labels: traits.append(labels['age'])
                if 'accent' in labels: traits.append(labels['accent'])
                if 'description' in labels: traits.append(labels['description'])
                trait_str = ", ".join(traits) if traits else "General"
                v_list.append(f"- Name: {v['name']} (ID: {v['voice_id']}) - {trait_str}")
            voice_options_str = "\n".join(v_list)
    except: pass

    voice_consistency_map = {}
    try:
        p_set = db.get_project_settings(project_id) if project_id else {}
        if p_set and p_set.get('voice_mapping_json'):
            start_map = json.loads(p_set.get('voice_mapping_json'))
            for k, v in start_map.items():
                if isinstance(v, dict) and "id" in v:
                    voice_consistency_map[k] = v
                elif isinstance(v, str):
                    voice_consistency_map[k] = {"id": v, "name": "Unknown Voice"}
    except: pass

    for i, file_path in enumerate(files):
        if not os.path.exists(file_path): continue
            
        ext = os.path.splitext(file_path)[1].lower()
        analysis_image_path = file_path
        clean_image_path = None
        
        if ext == '.psd':
            try:
                from psd_tools import PSDImage
                import uuid
                psd_ana = PSDImage.open(file_path)
                full_png_path = os.path.join(sliced_base_dir, f"full_{uuid.uuid4().hex}.png")
                comp_ana = psd_ana.composite()
                if not comp_ana: comp_ana = Image.fromarray(psd_ana.numpy())
                comp_ana.save(full_png_path)
                analysis_image_path = full_png_path
                
                debug_all_layers[os.path.basename(file_path)] = {
                    "layers": [l.name for l in psd_ana.descendants() if l.name][:50],
                    "matched": [], "keywords": [], "method": "analysis_only"
                }

                clean_image_path = full_png_path
                if psd_exclude_layer:
                    psd_cln = PSDImage.open(file_path)
                    raw_keywords = [k.strip() for k in re.split(r'[,，\s\n]+', psd_exclude_layer) if k.strip()]
                    keywords = [normalize_name(k) for k in raw_keywords]
                    found_any = False
                    matched_trace = []
                    for layer in psd_cln.descendants():
                        if not layer.name: continue
                        name_norm = normalize_name(layer.name)
                        if any(k in name_norm for k in keywords):
                            if layer.visible:
                                layer.visible = False
                                layer_trace.append(f"{os.path.basename(file_path)}: {layer.name}") 
                                matched_trace.append(layer.name)
                                if hasattr(layer, 'descendants'):
                                    for child in layer.descendants(): child.visible = False
                                found_any = True
                    if found_any:
                        clean_png_path = os.path.join(sliced_base_dir, f"cln_{uuid.uuid4().hex}.png")
                        try: comp_cln = psd_cln.composite()
                        except: comp_cln = None

                        method = "composite"
                        if not comp_cln:
                            method = "manual_merge"
                            canvas = Image.new("RGBA", psd_cln.size, (255, 255, 255, 255))
                            for l in psd_cln:
                                if l.visible:
                                    try:
                                        l_img = l.composite()
                                        if l_img: canvas.alpha_composite(l_img.convert("RGBA"))
                                    except: pass
                            comp_cln = canvas.convert("RGB")
                        if comp_cln.mode != 'RGB': comp_cln = comp_cln.convert('RGB')
                        comp_cln.save(clean_png_path)
                        clean_image_path = clean_png_path
                        debug_all_layers[os.path.basename(file_path)] = {
                            "layers": [l.name for l in psd_cln.descendants() if l.name][:50],
                            "matched": matched_trace, "keywords": keywords, "method": method
                        }
            except Exception as e:
                print(f"PSD Error: {e}")
                continue
        else:
            clean_image_path = file_path
        
        cuts = slice_webtoon(analysis_image_path, sliced_base_dir, start_idx=global_scene_counter, clean_image_path=clean_image_path)
        global_scene_counter += len(cuts)
        
        try:
            known_chars_str = ""
            if voice_consistency_map:
                known_chars_list = [f"- {name} (Voice: {data.get('name', 'Unknown')})" for name, data in voice_consistency_map.items()]
                if known_chars_list:
                    known_chars_str = "\n[KNOWN CHARACTERS]\n" + "\n".join(known_chars_list) + "\n"
            
            ts = int(time.time())
            
            for c in cuts:
                final_context = (current_context or "") + known_chars_str
                # 분석 개별 컷마다 수행
                analysis = await gemini_service.analyze_webtoon_panel(c["analysis"] if "analysis" in c else c["video"], context=final_context, voice_options=voice_options_str)
                
                if analysis.get('is_meaningless') is not True:
                    all_scenes.append({
                        "scene_number": len(all_scenes) + 1,
                        "image_path": c["video"],
                        "original_image_path": clean_image_path,
                        "original_image_url": f"/api/media/v?path={urllib.parse.quote(clean_image_path)}&t={ts}",
                        "image_url": f"/api/media/v?path={urllib.parse.quote(c['video'])}&t={ts}",
                        "analysis": analysis,
                        "focal_point_y": analysis.get("focal_point_y", 0.5)
                    })
                    # Add dialogue to context
                    diag = analysis.get("dialogue", "").strip()
                    char = analysis.get("character", "Unknown")
                    if diag and char != "Unknown":
                        current_context = f"Last seen: {char} said \"{diag[:50]}\". "

        except Exception as e:
            print(f"Directory AI Analysis Error on {file_path}: {e}")
            ts = int(time.time())
            for c in cuts:
                all_scenes.append({
                    "scene_number": len(all_scenes) + 1,
                    "image_path": c["video"],
                    "original_image_path": clean_image_path,
                    "original_image_url": f"/api/media/v?path={urllib.parse.quote(clean_image_path)}&t={ts}",
                    "image_url": f"/api/media/v?path={urllib.parse.quote(c['video'])}&t={ts}",
                    "analysis": {"dialogue": "", "character": "Unknown", "visual_desc": "Failed", "atmosphere": "Error"}
                })
        
        # Removed temporary file cleanup to preserve images for frontend display

    try:
        eleven_voices = await tts_service.get_elevenlabs_voices()
    except:
        eleven_voices = []
    
    for sc in all_scenes:
        finalize_scene_analysis(sc, voice_consistency_map, eleven_voices)
        norm_char = sc['analysis'].get('character')
        if norm_char and norm_char != "Unknown":
            voice_consistency_map[norm_char] = {"id": sc['voice_id'], "name": sc['voice_name']}
            db.update_project_setting(project_id, "voice_mapping_json", json.dumps(voice_consistency_map, ensure_ascii=False))

    try: shutil.rmtree(temp_dir)
    except: pass
        
    db.update_project(project_id, status="completed")
    
    # [NEW] Persist analyzed scenes to DB immediately
    try:
        db.update_project_setting(project_id, "webtoon_scenes_json", json.dumps(all_scenes, ensure_ascii=False))
        print(f"✅ [Persistence-Dir] Saved {len(all_scenes)} scenes to project {project_id}")
    except Exception as e:
        print(f"⚠️ [Persistence-Dir] Error saving scenes: {e}")

    # [NEW] Generate global story summary
    story_summary = ""
    try:
        story_summary = await gemini_service.summarize_story(all_scenes)
        db.update_project_setting(project_id, "webtoon_story_summary", story_summary)
    except: pass

    return {
        "status": "ok",
        "scenes": all_scenes,
        "total_scenes": len(all_scenes),
        "story_summary": story_summary,
        "character_map": voice_consistency_map,
        "layer_debug": {"trace": layer_trace, "all_files": debug_all_layers}
    }

async def automate_webtoon_service(project_id: int, scenes: List[Any], use_lipsync: bool, use_subtitles: bool, character_map: Optional[dict]):
    """웹툰 자동화를 위한 데이터 전처리 및 대기열 전송 로직"""
    full_script = ""
    for s in scenes:
        speaker = s.character if s.character and s.character != "None" else "나레이션"
        full_script += f"{speaker}: {s.dialogue}\n\n"
        
    asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image")
    os.makedirs(asset_dir, exist_ok=True)
    sfx_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound")
    os.makedirs(sfx_dir, exist_ok=True)
    
    image_prompts = []
    for i, s in enumerate(scenes):
        filename = f"scene_{i+1:03d}.jpg"
        dest_path = os.path.join(asset_dir, filename)
        shutil.copy2(s.image_path, dest_path)
        
        db.update_project_setting(project_id, f"scene_{i+1}_image", filename)
        motion = s.effect_override or "zoom_in"
        db.update_project_setting(project_id, f"scene_{i+1}_motion", motion)
        db.update_project_setting(project_id, f"scene_{i+1}_motion_speed", "3.3")
        
        orig_img_path = s.original_image_path
        if orig_img_path and orig_img_path != s.image_path and os.path.exists(orig_img_path):
            wan_filename = f"scene_{i+1:03d}_wan.jpg"
            shutil.copy2(orig_img_path, os.path.join(asset_dir, wan_filename))
            db.update_project_setting(project_id, f"scene_{i+1}_wan_image", wan_filename)
        
        if s.engine_override:
            db.update_project_setting(project_id, f"scene_{i+1}_engine", s.engine_override)
        if s.motion_desc:
            db.update_project_setting(project_id, f"scene_{i+1}_motion_desc", s.motion_desc)
        if s.voice_id and s.voice_id != "None":
            db.update_project_setting(project_id, f"scene_{i+1}_voice", s.voice_id)
        if s.voice_settings:
            try: db.update_project_setting(project_id, f"scene_{i+1}_voice_settings", json.dumps(s.voice_settings))
            except: pass

        if s.sound_effects and s.sound_effects not in ['None', 'Unknown'] and len(s.sound_effects) > 2:
            try:
                sfx_prompt = re.sub(r'[^\w\s,]', '', s.sound_effects)
                sfx_data = await tts_service.generate_sound_effect(sfx_prompt[:100], duration_seconds=None)
                if sfx_data:
                    sfx_filename = f"sfx_scene_{i+1:03d}.mp3"
                    with open(os.path.join(sfx_dir, sfx_filename), "wb") as f: f.write(sfx_data)
                    db.update_project_setting(project_id, f"scene_{i+1}_sfx", sfx_filename)
            except: pass

        image_prompts.append({
            "scene_number": i + 1, "scene_text": s.dialogue, "prompt_en": f"{s.visual_desc}", 
            "image_url": f"/output/{str(project_id)}/assets/image/{filename}",
            "narrative": s.dialogue, "focal_point_y": s.focal_point_y, "motion_desc": s.motion_desc
        })

    db.save_image_prompts(project_id, image_prompts)
    db.update_project(project_id, status="queued")
    db.update_project_setting(project_id, "script", full_script)
    db.update_project_setting(project_id, "auto_plan", False)
    db.update_project_setting(project_id, "app_mode", "shorts") 
    db.update_project_setting(project_id, "auto_tts", 1)      
    db.update_project_setting(project_id, "auto_render", 1)   
    
    if use_lipsync:
        db.update_project_setting(project_id, "video_engine", "akool")
        db.update_project_setting(project_id, "all_video", 1)
    else:
        db.update_project_setting(project_id, "video_engine", "wan")
        db.update_project_setting(project_id, "all_video", 1)
    
    db.update_project_setting(project_id, "use_lipsync", use_lipsync)
    db.update_project_setting(project_id, "use_subtitles", use_subtitles)
    if character_map:
        db.update_project_setting(project_id, "voice_mapping_json", json.dumps(character_map, ensure_ascii=False))
    
    autopilot_service.add_to_queue(project_id)
    return {"status": "ok", "message": "Project added to queue for automation"}

async def fetch_webtoon_url_service(project_id: int, url: str):
    """네이버 웹툰 URL에서 이미지를 크롤링하여 저장하는 비즈니스 로직"""
    from fastapi import HTTPException
    
    if "comic.naver.com" not in url:
        raise HTTPException(400, "Only Naver Webtoon URLs are supported currently.")

    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            raise HTTPException(500, f"Failed to fetch page: {res.status_code}")
        
        html = res.text
        img_urls = re.findall(r'src="(https://image-comic\.pstatic\.net/webtoon/[^"]+)"', html)
        if not img_urls:
            img_urls = re.findall(r'data-src="(https://image-comic\.pstatic\.net/webtoon/[^"]+)"', html)
        
        if not img_urls:
            raise HTTPException(404, "No webtoon images found in the provided URL.")

        seen = set()
        img_urls = [x for x in img_urls if not (x in seen or seen.add(x))]

        project_dir = os.path.join(config.OUTPUT_DIR, str(project_id))
        webtoon_dir = os.path.join(project_dir, "webtoon_originals")
        os.makedirs(webtoon_dir, exist_ok=True)
        
        downloaded_images = []
        img_headers = headers.copy()
        img_headers["Referer"] = "https://comic.naver.com/"

        for i, img_url in enumerate(img_urls):
            img_res = await client.get(img_url, headers=img_headers)
            if img_res.status_code == 200:
                img_data = Image.open(io.BytesIO(img_res.content))
                downloaded_images.append(img_data)
            
        if not downloaded_images:
            raise HTTPException(500, "Failed to download any images.")

        total_width = max(img.width for img in downloaded_images)
        total_height = sum(img.height for img in downloaded_images)
        
        merged_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
        y_offset = 0
        for img in downloaded_images:
            merged_img.paste(img, (0, y_offset))
            y_offset += img.height
        
        save_path = os.path.join(webtoon_dir, f"original_{int(time.time())}.jpg")
        merged_img.save(save_path, "JPEG", quality=95)
        
        filename = os.path.basename(save_path)
        return {
            "status": "ok", 
            "filename": filename,
            "path": save_path, 
            "url": f"/api/media/v?path={urllib.parse.quote(save_path)}",
            "width": total_width, 
            "height": total_height
        }

async def generate_single_scene_video_service(project_id: int, scene_index: int, s: Any):
    """특정 장면 하나만 영상을 생성하는 서비스 로직"""
    import shutil
    import time
    from datetime import datetime
    
    scene_num = s.scene_number
    asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image")
    os.makedirs(asset_dir, exist_ok=True)
    
    # 1. Prepare image in assets/image if not there
    filename = f"scene_{scene_num:03d}.jpg"
    dest_path = os.path.join(asset_dir, filename)
    
    # Use image_path provided by frontend
    if s.image_path and os.path.exists(s.image_path):
        shutil.copy2(s.image_path, dest_path)
    else:
        # Fallback
        print(f"⚠️ [Single Gen] Image path {s.image_path} not found. Checking assets.")

    # Update individual scene settings in DB to ensure engine/motion are synced
    db.update_project_setting(project_id, f"scene_{scene_num}_image", filename)
    motion = s.effect_override or "zoom_in"
    db.update_project_setting(project_id, f"scene_{scene_num}_motion", motion)
    if s.engine_override:
        db.update_project_setting(project_id, f"scene_{scene_num}_engine", s.engine_override)
    if s.motion_desc:
        db.update_project_setting(project_id, f"scene_{scene_num}_motion_desc", s.motion_desc)

    # [NEW] 물리적 이미지 비율 체크 (기획서 오판 방지)
    try:
        with Image.open(dest_path) as img:
            w, h = img.size
            is_wide = (w / h) > 1.2
            if is_wide:
                print(f"📐 [Single Gen] Scene {scene_num} is WIDE physically. Forcing Pan Right strategy.")
                motion = "pan_right"
    except: pass

    # 2. Choice of Engine — AKOOL Seedance is PRIMARY, Wan 2.1 is FALLBACK
    engine = s.engine_override or "akool"
    video_url = None
    
    # Estimated duration based on dialogue length
    dialogue = s.dialogue or ""
    duration = max(3.0, len(dialogue) * 0.35)
    
    now_str = datetime.now().strftime('%H%M%S')

    try:
        if engine == "image":
            # 2D Motion Video (Image only)
            print(f"🖼️ [Single Gen] Scene {scene_num}: Using Image Engine (2D) with style: {motion}")
            motion_bytes = await video_service.create_image_motion_video(
                image_path=dest_path,
                duration=duration,
                motion_type=motion,
                width=1080, height=1920
            )
            if motion_bytes:
                out_filename = f"vid_img_{project_id}_{scene_num}_{now_str}.mp4"
                out_path = os.path.join(config.OUTPUT_DIR, out_filename)
                with open(out_path, 'wb') as f: f.write(motion_bytes)
                video_url = f"/output/{out_filename}"
                
        else: # "akool" (primary) or "wan" (fallback)
            import re
            print(f"🎬 [Single Gen] Scene {scene_num}: Using AI Engine ({engine})")
            
            # [SAFETY CHECK] 다이내믹 캔버스 패딩 (모션 방향에 따른 가변 해상도)
            # Wide Image의 패닝(Pan) 성능을 극대화하기 위해 모션에 따라 16:9 또는 9:16 캔버스를 선택합니다.
            try:
                from PIL import Image
                with Image.open(dest_path) as img:
                    orig_w, orig_h = img.size
                    
                    # [STRATEGY] 원본 비율 유지! 
                    # 이미지 호스팅 접근 차단 문제가 해결되었으므로, Wan 2.5 엔진의 자체적인 네이티브 패닝(Pan) 기능에 원본 전체를 전달합니다.
                    # 너무 큰 이미지만 메모리 제한(1536px)에 맞춰 축소하며 비율은 해치지 않습니다.
                    max_dim = 1536
                    if orig_w > max_dim or orig_h > max_dim:
                        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                        
                    # 4. 저장 (고호환성 RGB JPEG로 강제 변환)
                    dest_path_jpg = dest_path.replace(".png", ".jpg")
                    img.convert("RGB").save(dest_path_jpg, "JPEG", quality=95, optimize=True)
                    dest_path = dest_path_jpg
                    print(f"📏 [Native Ratio] Passed to AI for Native Panning ({img.size[0]}x{img.size[1]})")
            except Exception as resize_e:
                print(f"⚠️ [Canvas Error] {resize_e}")

            # [1] Wan 2.5 최적화 프롬프트 생성 (카메라 모션 주입 제거)
            # 사용자가 수정한 motion_desc가 있다면 최우선적으로 사용합니다.
            prompt_base = str(s.motion_desc or s.visual_desc or "high quality anime webtoon style")
            
            # 카메라 관련 키워드 강제 필터링 (AI가 화면을 억지로 비틀지 않게 함)
            # clean_p = re.sub(r'(?i)\b(pan\w*|zoom\w*|truck\w*|move\w*|motion|direction|into|in|out|up|down|horizontal|vertical|effect)\b', '', prompt_base)
            
            # 최종 프롬프트: 사용자의 연출 의도 + 고화질 품질 태그
            prompt = f"{prompt_base}, high quality, detailed anime art style, masterpiece, 4k."
            
            print(f"🎬 [AKOOL WAN 2.5 PREMIUM] {prompt}")

            video_data = None
            exception_to_raise = None
            
            try:
                if engine == "wan":
                    raise Exception("force_wan")
                
                # [PRIMARY] AKOOL Premium (WAN 2.5)
                from services.akool_service import AkoolService
                ak_svc = AkoolService()
                
                print(f"🎬 [AKOOL WAN 2.5 PREMIUM] Scene {scene_num}: Generating 720p Video...")
                video_data = await ak_svc.generate_akool_video_v4(
                    local_image_path=dest_path,
                    prompt=prompt,
                    duration=5,
                    resolution="720p"    # 1080p는 Wan2.5 특성상 호환성 에러 빈발, 720p로 고정
                )
            except Exception as e:
                err_str = str(e).lower()
                if "force_wan" in err_str:
                    print(f"⚠️ [Single Gen] Engine explicitly set to Wan.")
                    print(f"🔄 [Single Gen] Using Replicate (Wan 2.1)...")
                    try:
                        video_data = await replicate_service.generate_video_from_image(dest_path, prompt)
                    except Exception as wan_e:
                        print(f"❌ [Single Gen] Replicate failed: {wan_e}")
                        exception_to_raise = wan_e
                else:
                    # AKOOL 에러면 여기서 바로 멈추고 에러 전달
                    print(f"❌ [Single Gen] AKOOL Premium failed: {e}")
                    raise Exception(f"AKOOL 생성 실패: {str(e)}")
                    
            if exception_to_raise and not video_data:
                raise exception_to_raise
            
            if video_data:
                actual_engine = "akool" if not exception_to_raise and engine != "wan" else "wan"
                out_filename = f"vid_{actual_engine}_{project_id}_{scene_num}_{now_str}.mp4"
                out_path = os.path.join(config.OUTPUT_DIR, out_filename)
                with open(out_path, 'wb') as f: f.write(video_data)
                video_url = f"/output/{out_filename}"

        if video_url:
            db.update_image_prompt_video_url(project_id, scene_num, video_url)
            return {"status": "ok", "video_url": video_url}
        else:
            return {"status": "error", "error": f"{engine} engine failed to generate video file."}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ [Single Gen] Error: {e}")
        return {"status": "error", "error": str(e)}
