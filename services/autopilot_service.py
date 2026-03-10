
import asyncio
import json
import os
import sys
import random
from datetime import datetime, timedelta
import httpx
from typing import List, Dict, Union, Optional, Any
from config import config

# Windows cp949 이모지 출력 에러 방지
_builtin_print = print
def print(*args, **kwargs):
    try:
        _builtin_print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [str(a).encode('ascii', errors='replace').decode('ascii') for a in args]
        try:
            _builtin_print(*safe_args, **kwargs)
        except Exception:
            pass
import database as db
from services.gemini_service import gemini_service
from services.replicate_service import replicate_service
from services.akool_service import akool_service
from services.prompts import prompts
from services.tts_service import tts_service
from services.video_service import video_service
from services.youtube_upload_service import youtube_upload_service
from services.topview_service import topview_service


def split_text_to_subtitle_chunks(text: str, max_chars_per_line: int = 20, max_lines: int = 2) -> list:
    """
    긴 텍스트를 자막용 청크로 분할합니다.
    - 한 줄당 최대 max_chars_per_line 글자
    - 한 화면에 최대 max_lines 줄 (기본 2줄)
    - 문장 경계(. ! ?)를 우선으로 분할
    
    Returns: List of subtitle text chunks (each chunk is max 2 lines)
    """
    if not text or not text.strip():
        return []
    
    text = text.strip()
    
    # 먼저 문장 단위로 분리 (마침표, 느낌표, 물음표 기준)
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk_lines = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # 문장을 줄 단위로 분할 (max_chars_per_line 기준)
        words = sentence.split()
        current_line = ""
        lines_from_sentence = []
        
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            if len(test_line) <= max_chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    lines_from_sentence.append(current_line)
                current_line = word
        
        if current_line:
            lines_from_sentence.append(current_line)
        
        # 현재 청크에 이 문장의 줄들을 추가
        for line in lines_from_sentence:
            current_chunk_lines.append(line)
            
            # max_lines에 도달하면 청크 생성
            if len(current_chunk_lines) >= max_lines:
                chunks.append("\n".join(current_chunk_lines))
                current_chunk_lines = []
    
    # 남은 줄들 처리
    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))
    
    return chunks


def log_debug(msg: str):
    """Explicitly write to debug.log for external monitoring"""
    print(msg)
    try:
        from config import config
        from datetime import datetime
        with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except:
        pass

class AutoPilotService:
    def __init__(self):
        self.search_url = f"{config.YOUTUBE_BASE_URL}/search"
        self.config = {}  # Director Mode Configuration
        self.is_batch_running = False # [NEW] Batch Concurrency Lock

    async def run_workflow(self, keyword: str, project_id: int = None, config_dict: dict = None):
        """오토파일럿 전체 워크플로우 실행"""
        print(f"🚀 [Auto-Pilot] '{keyword}' 작업 시작")
        start_dt = datetime.now()
        db.update_project_setting(project_id, "stats_start_time", start_dt.strftime("%Y-%m-%d %H:%M:%S"))
        
        self.config = config_dict or {}
        if "auto_plan" not in self.config:
            self.config["auto_plan"] = True  # Always generate plan data by default
        
        # [NEW] TopView Commerce Mode Check
        creation_mode = self.config.get("creation_mode", "default")
        if creation_mode == "commerce":
            return await self._run_topview_workflow(project_id, self.config)
        
        try:
            # 1~2. 소재 발굴 및 프로젝트 생성
            log_debug(f"⚙️ [Auto-Pilot] Start run_workflow for project {project_id} (Keyword: {keyword})")
            start_dt = datetime.now()
            
            # [FIX] Load latest project settings BEFORE modifying self.config
            if project_id:
                p_settings = db.get_project_settings(project_id) or {}
                # Update self.config with DB settings
                if config_dict:
                    p_settings.update(config_dict)
                self.config = p_settings
            else:
                self.config = config_dict or {}
            
            # Force all_video if needed
            if self.config.get("all_video"):
                 log_debug(f"🔋 [Auto-Pilot] all_video flag detected in config for PID {project_id}")

            if not project_id:
                video = await self._find_best_material(keyword)
                if not video: return
                project_name = f"[Auto] {keyword} - {video['snippet']['title'][:20]}"
                project_id = db.create_project(name=project_name, topic=keyword)
                db.update_project(project_id, status="created")
                current_status = "created"
            else:
                project = db.get_project(project_id)
                current_status = project.get('status', 'created')

            # 3. AI 분석
            if current_status in ["created", "draft"]:
                db.update_project(project_id, status="analyzing") # [NEW] status for UI
                video = await self._find_best_material(keyword)
                analysis_result = await self._analyze_video(video)
                db.save_analysis(project_id, video, analysis_result)
                db.update_project(project_id, status="analyzed")
                current_status = "analyzed"

            # 4. 기획 및 대본 작성
            if current_status == "analyzed":
                db.update_project(project_id, status="planning") # [NEW] status for UI
                analysis = db.get_analysis(project_id)
                script = await self._generate_script(project_id, analysis.get("analysis_result", {}), self.config)
                db.update_project_setting(project_id, "script", script)
                
                db.update_project(project_id, status="scripting") # [NEW] status for UI
                # [NEW] AI 제목 및 설명 생성
                await self._generate_metadata(project_id, script)
                
                db.update_project(project_id, status="scripted")
                current_status = "scripted"

            # [RE-SYNC] Webtoon mode transition: if it's queued/scripted but came from webtoon studio
            if current_status in ["queued", "scripted", "scripting"]:
                # Check if we have image prompts but no videos
                prompts = db.get_image_prompts(project_id)
                if prompts:
                    current_status = "characters_ready"
                    print(f"🎞️ [Auto-Pilot] Found existing image prompts. Moving to Asset Generation.")

            # 4.5 캐릭터 추출 (일관성 유지용)
            if current_status == "scripted":
                script_data = db.get_script(project_id)
                if script_data:
                    await self._extract_characters(project_id, script_data["full_script"], self.config)
                current_status = "characters_ready"

            # 5. 에셋 생성 (이미지 & 썸네일 & 오디오)
            if current_status == "characters_ready":
                script_data = db.get_script(project_id)
                full_script = script_data["full_script"]
                
                # 5-1. 영상 소스 생성
                db.update_project(project_id, status="generating_assets")
                await self._generate_assets(project_id, full_script, self.config)
                
                # [NEW] Ensure Metadata exists (Title, Description) - Re-run if skipped earlier
                settings = db.get_project_settings(project_id) or {}
                if not settings.get('title') or not settings.get('description'):
                    print(f"📝 [Auto-Pilot] Metadata missing for pid {project_id}. Generating...")
                    await self._generate_metadata(project_id, full_script)

                # 5-2. [NEW] 썸네일 자동 생성
                if self.config.get('auto_thumbnail', True):
                    # Check if already exists to avoid duplicate gen
                    if not settings.get('thumbnail_url'):
                        db.update_project(project_id, status="generating_thumbnail")
                        await self._generate_thumbnail(project_id, full_script, self.config)

                db.update_project(project_id, status="tts_done")
                current_status = "tts_done"

            # 6. 영상 렌더링
            if current_status == "tts_done":
                await self._render_video(project_id)
                current_status = "rendered"

            # 7. 업로드
            if current_status == "rendered":
                settings = db.get_project_settings(project_id)
                video_path = settings.get("video_path")
                if video_path:
                    abs_video_path = os.path.join(config.OUTPUT_DIR, video_path.replace("/output/", ""))
                    if os.path.exists(abs_video_path):
                        await self._upload_video(project_id, abs_video_path)
                        db.update_project(project_id, status="uploaded")
            
            # [NEW] Save Stats
            end_dt = datetime.now()
            duration_str = str(end_dt - start_dt).split('.')[0]
            db.update_project_setting(project_id, "stats_end_time", end_dt.strftime("%Y-%m-%d %H:%M:%S"))
            db.update_project_setting(project_id, "stats_total_duration", duration_str)
            
            db.update_project(project_id, status="done")
            print(f"✨ [Auto-Pilot] 작업 완료! (ID: {project_id}, Time: {duration_str})")

        except Exception as e:
            import traceback
            err_details = traceback.format_exc()
            print(f"❌ [Auto-Pilot] 오류 발생: {e}")
            print(err_details)
            
            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                    df.write(f"[{datetime.now()}] ❌ [Auto-Pilot] CRITICAL ERROR in run_workflow:\n{err_details}\n")
            except: pass
            
            db.update_project(project_id, status="error")

    async def _extract_characters(self, project_id: int, script_text: str, config_dict: dict = None):
        """대본에서 캐릭터 추출 및 일관성 있는 프롬프트 생성 (이미 있으면 건너뜀)"""
        # [NEW] 이미 캐릭터가 수동으로 설정되어 있는지 확인
        existing = db.get_project_characters(project_id)
        if existing:
            print(f"👥 [Auto-Pilot] 이미 {len(existing)}명의 캐릭터가 설정되어 있습니다. 추출을 건너뜁니다.")
            return

        print(f"👥 [Auto-Pilot] 캐릭터 추출 시작...")
        
        # [NEW] 비주얼 스타일 결정
        style_prefix = "photorealistic"
        if config_dict:
            image_style_key = config_dict.get("image_style", config_dict.get("visual_style", "realistic"))
            style_presets = db.get_style_presets()
            style_data = style_presets.get(image_style_key, {})
            style_prefix = style_data.get("prompt_value", "photorealistic")
        
        try:
            characters = await gemini_service.generate_character_prompts_from_script(script_text, visual_style=style_prefix)
            if characters:
                db.save_project_characters(project_id, characters)
                print(f"✅ [Auto-Pilot] {len(characters)}명의 캐릭터를 식별하고 저장했습니다. (Style: {style_prefix})")
                
                # [NEW] 캐릭터 샘플 이미지 생성 및 적용 (최대 3명)
                processed_chars = characters[:3]
                has_applied_reference = False
                
                for idx, char in enumerate(processed_chars):
                    try:
                        print(f"👤 [Auto-Pilot] 캐릭터 '{char['name']}' ({char['role']}) 샘플 이미지 생성 중...")
                        detailed_style = style_data.get('prompt_value', style_prefix)
                        full_prompt = f"{char['prompt_en']}, {detailed_style}"
                        
                        # Portrait aspect ratio 1:1 (Replicate -> Gemini -> Akool Strategy)
                        images_bytes = None
                        
                        # 1. Replicate Flux
                        try:
                            print(f"🎨 [Auto-Pilot Char] Attempting Replicate (Primary)...")
                            images_bytes = await replicate_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
                        except Exception as e:
                            print(f"⚠️ [Auto-Pilot Char] Replicate failed: {e}")
                        
                        # 2. Gemini Fallback
                        if not images_bytes:
                            try:
                                print(f"🎨 [Auto-Pilot Char] Attempting Gemini Imagen (Fallback 1)...")
                                images_bytes = await gemini_service.generate_image(
                                    prompt=full_prompt,
                                    num_images=1,
                                    aspect_ratio="1:1"
                                )
                            except Exception as e:
                                print(f"⚠️ [Auto-Pilot Char] Gemini failed: {e}")

                        # 3. Akool Fallback
                        if not images_bytes:
                            try:
                                print(f"🎨 [Auto-Pilot Char] Attempting AKOOL (Final Fallback)...")
                                images_bytes = await akool_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
                            except Exception as e:
                                print(f"⚠️ [Auto-Pilot Char] Akool failed: {e}")
                        
                        if images_bytes:
                            now = config.get_kst_time()
                            filename = f"char_{project_id}_{idx}_{now.strftime('%H%M%S')}.png"
                            file_path = os.path.join(config.OUTPUT_DIR, filename)
                            web_url = f"/output/{filename}"
                            
                            with open(file_path, "wb") as f:
                                f.write(images_bytes[0])
                            
                            # DB 업데이트
                            db.update_character_image(project_id, char['name'], web_url)
                            
                            # [핵심] 주인공이거나 첫 번째 캐릭터인 경우 프로젝트 레퍼런스로 자동 적용 (Apply 버튼 효과)
                            is_protagonist = "주인공" in char.get("role", "")
                            if not has_applied_reference:
                                if is_protagonist or (idx == len(processed_chars) - 1) or (idx == 0 and len(processed_chars) == 1):
                                    db.update_project_setting(project_id, "character_ref_text", char['prompt_en'])
                                    db.update_project_setting(project_id, "character_ref_image_path", web_url)
                                    has_applied_reference = True
                                    print(f"✨ [Auto-Pilot] 주인공 '{char['name']}'을(를) 캐릭터 레퍼런스로 적용했습니다.")
                        
                    except Exception as char_e:
                        print(f"⚠️ [Auto-Pilot] 캐릭터 '{char['name']}' 이미지 생성 실패: {char_e}")

        except Exception as e:
            print(f"⚠️ [Auto-Pilot] 캐릭터 추출 실패: {e}")

    async def _generate_metadata(self, project_id: int, script_text: str):
        """AI를 사용하여 제목, 설명, 태그 생성"""
        print(f"📝 [Auto-Pilot] 제목 및 설명 생성 시작...")
        try:
            metadata = await gemini_service.generate_video_metadata(script_text)
            if metadata:
                db.update_project_setting(project_id, "title", metadata.get("title"))
                db.update_project_setting(project_id, "description", metadata.get("description"))
                db.update_project_setting(project_id, "hashtags", ",".join(metadata.get("tags", [])))
                print(f"✅ [Auto-Pilot] 메타데이터 생성 완료: {metadata.get('title')}")
        except Exception as e:
            print(f"⚠️ [Auto-Pilot] 메타데이터 생성 실패: {e}")

    async def _find_best_material(self, keyword: str):
        params = {
            "part": "snippet", "q": keyword, "type": "video",
            "maxResults": 3, "order": "relevance", "videoDuration": "short",
            "key": config.YOUTUBE_API_KEY
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(self.search_url, params=params)
            data = response.json()
            return data["items"][0] if "items" in data and data["items"] else None

    async def _analyze_video(self, video_data: dict):
        video_id = video_data['id']['videoId']
        title = video_data['snippet']['title']
        description = video_data['snippet']['description']
        
        prompt = f"""
        유튜브 영상 정보를 바탕으로 새로운 영상을 위한 분석을 수행합니다.
        
        [영상 정보]
        - 제목: {title}
        - ID: {video_id}
        - 설명: {description[:500]}
        
        이 영상의 핵심 타겟 오디언스, 주요 내용, 그리고 이를 벤치마킹했을 때 대중들이 좋아할만한 '공감 포인트'를 3가지만 분석해서 JSON으로 주세요.
        
        JSON 포맷:
        {{
            "sentiment": "positive/negative/neutral",
            "topics": ["주제1", "주제2"],
            "viewer_needs": "시청자들이 원하는 것 설명"
        }}
        JSON만 출력하세요.
        """
        result_text = await gemini_service.generate_text(prompt, temperature=0.7)
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            return json.loads(json_match.group()) if json_match else {"summary": result_text}
        except: return {"summary": result_text}

    async def _generate_script(self, project_id: int, analysis: dict, config_dict: dict):
        style_key = config_dict.get("script_style", "default")
        # Get script style description from DB presets if exists
        script_presets = db.get_script_style_presets()
        style_desc = script_presets.get(style_key, f"Style: {style_key}")

        # [NEW] Check for Manual Planning (Script Structure)
        manual_plan = db.get_script_structure(project_id)

        # [AUTO-PLAN] If auto_plan is requested AND no manual plan exists, generate one now
        if not (manual_plan and manual_plan.get("structure")) and config_dict.get("auto_plan"):
             print(f"🤖 [Auto-Pilot] 자동 기획 생성 시작...")
             try:
                  target_duration_min = config_dict.get("duration_seconds", 300) // 60
                  struct_prompt = f"""
Create a structured plan for a YouTube video based on this analysis.
Analysis: {json.dumps(analysis, ensure_ascii=False)}

Context:
- Video Topic: {db.get_project(project_id).get('topic')}
- Script Style: {style_desc}
- Target Duration: {target_duration_min} minutes

Required Format (JSON Only):
{{
  "hook": "Strong opening sentence to grab attention",
  "sections": [
    {{ "title": "Section Title", "key_points": ["point1", "point2"] }}
  ],
  "cta": "Conclusion and call to action",
  "style": "{style_key}",
  "duration": {target_duration_min}
}}
Language: Korean
Style Guide: Narration/Monologue only. NO dialogue between characters.
"""
                  # request_s = type('obj', (object,), {"prompt": struct_prompt, "temperature": 0.7})
                  result_text_s = await gemini_service.generate_text(struct_prompt, temperature=0.7)
                  
                  import re
                  match = re.search(r'\{[\s\S]*\}', result_text_s)
                  if match:
                      new_struct = json.loads(match.group())
                      # Ensure style and duration are set if AI missed them
                      if "style" not in new_struct: new_struct["style"] = style_key
                      if "duration" not in new_struct: new_struct["duration"] = target_duration_min
                      
                      db.save_script_structure(project_id, new_struct)
                      manual_plan = {"structure": new_struct} # Update local var to trigger next block
                      print(f"✅ [Auto-Pilot] 자동 기획 완료 및 저장. (Duration: {target_duration_min}m)")
             except Exception as e:
                 print(f"⚠️ [Auto-Pilot] 자동 기획 실패: {e}")
        
        if manual_plan and manual_plan.get("structure"):
            print(f"📄 [Auto-Pilot] 수동 기획 데이터 발견! 기획 기반 대본 작성 모드로 전환합니다.")
            plan_json = json.dumps(manual_plan.get("structure"), ensure_ascii=False)
            
            prompt = f"""You are a professional YouTube scriptwriter.
Write a full script based strictly on the following USER PLANNED STRUCTURE.

[User Plan & Title]
{plan_json}

[Reference Analysis]
{json.dumps(analysis, ensure_ascii=False)}

[Instructions]
1. You MUST follow the 'User Plan' structure (Hook, Body, Conclusion, etc).
2. The 'structure' contains specific Hooks and plot points selected by the user. Do NOT change them.
3. Use the 'Reference Analysis' only to enrich the content details.
4. Voice: Strictly SINGLE SPEAKER Narration or Monologue. 
5. NO DIALOGUE: Do not write conversations between different people (No "A: Hello, B: Hi").
6. Output the full script in Korean.

[Absolute Rules for TTS]
- NO character names or colons (e.g., "Narrator:", "Me:").
- NO parentheses or situational descriptions (e.g., "(music)", "(laughs)").
- NO special characters or emojis.
"""
            if style_key != "default":
                prompt += f"\n\n[Writing Style Directive]: {style_desc}\nApply this style strictly."
        else:
            # Original Logic
            prompt = prompts.AUTOPILOT_GENERATE_SCRIPT.format(
                analysis_json=json.dumps(analysis, ensure_ascii=False)
            )
            if style_key != "default":
                prompt += f"\n\n[Writing Style Directive]: {style_desc}\nApply this style strictly throughout the script."

        # request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
        script = await gemini_service.generate_text(prompt, temperature=0.8)
        
        # [CRITICAL] 4가지 금지 항목 정제 (괄호, 타임스탬프, 이모티콘, 화자 표시)
        import re
        if script:
            # 1. 괄호와 그 안의 내용 삭제 (예: (배경음악), (웃음))
            script = re.sub(r'\([^)]*\)', '', script)
            # 2. 타임스탬프 및 시간대 삭제 (예: [0-5초], [00:15])
            script = re.sub(r'\[[^\]]*\]', '', script)
            # 3. 별표 및 꾸밈 기호 삭제 (**)
            script = re.sub(r'\*', '', script)
            # 4. 이모티콘 및 특수 기호 삭제 (🤣, ✨, 🔥 등)
            script = re.sub(r'[^\w\s\d,.\?\!\"\'\. ]', '', script)
            # 5. 화자 표시 삭제 (예: 나:, 상사:, A:) - 문장 시작 부분의 이름과 콜론
            script = re.sub(r'^[가-힣\w\s]+[\s]*:[\s]*', '', script, flags=re.MULTILINE)
            # 6. 불필요한 공백 및 빈 줄 정리
            script = script.strip()
            script = re.sub(r'\n\s*\n', '\n', script)

        # Save script
        # Calculate approximate duration (char count / 15 chars per sec is rough, usually 5 chars/sec for speech)
        # Using a safer estimate provided by user input usually, but here auto-calc
        target_duration_sec = config_dict.get("duration_seconds", 300) 
        db.save_script(project_id, script, len(script), target_duration_sec)
        
        return script

    async def _generate_assets(self, project_id: int, script: str, config_dict: dict):
        all_video = config_dict.get("all_video", False)
        motion_method = config_dict.get("motion_method", "standard")
        video_engine = config_dict.get("video_engine", "wan")
        image_style_key = config_dict.get("image_style", config_dict.get("visual_style", "realistic"))

        
        # Determine sequence duration based on method
        video_duration = 5.0
        if motion_method in ["extend", "slowmo"]:
            video_duration = 8.0

        # Get visual style prompt from presets
        style_presets = db.get_style_presets()
        style_data = style_presets.get(image_style_key, {})

        style_prefix = style_data.get("prompt_value", "photorealistic")
        gemini_instruction = style_data.get("gemini_instruction", "")

        # 1. Image Prompts
        # [CRITICAL FIX] Use actual target duration for image count calculation
        target_duration = config_dict.get("duration_seconds", 300)

        image_prompts = db.get_image_prompts(project_id)
        if not image_prompts:
            print(f"🖼️ [Auto-Pilot] Generating image prompts for {target_duration}s video (style_key={image_style_key})...")
            # [NEW] 캐릭터 정보 조회 및 전달
            characters = db.get_project_characters(project_id)
            image_prompts = await gemini_service.generate_image_prompts_from_script(
                script, target_duration, style_prefix,
                characters=characters,
                style_key=image_style_key,
                gemini_instruction=gemini_instruction
            )
            db.save_image_prompts(project_id, image_prompts)
            image_prompts = db.get_image_prompts(project_id)
            print(f"🖼️ [Auto-Pilot] Generated {len(image_prompts)} image prompts")

        # Determine how many scenes to make as video
        log_debug(f"🔍 [DEBUG] _generate_assets START: all_video={all_video}, motion_method={motion_method}")
        
        if all_video:
            video_scene_count = len(image_prompts)
            log_debug(f"🎬 [Auto-Pilot] 'ALL VIDEO' mode enabled. Generating {video_scene_count} video scenes.")
        else:
            video_scene_count = config_dict.get("video_scene_count", 0)
            log_debug(f"🎬 [Auto-Pilot] Video scene count set to: {video_scene_count}")
        
        # [NEW] Force loud debug for all_video to see if it's really working
        if all_video or video_scene_count > 0:
             log_debug(f"🚀🚀🚀 [DYNAMO] VIDEO GENERATION IS ACTIVE! Count: {video_scene_count}, Engine: {video_engine} 🚀🚀🚀")

        # 2. Assets (Video/Image)
        from services.replicate_service import replicate_service
        async def process_scene(p, is_video: bool):
            scene_num = p.get("scene_number")
            if p.get("image_url") and not (is_video and not p.get("video_url")): 
                # Already has image, and if video requested, check if video exists
                if not (is_video and not p.get("video_url")):
                    return True
            
            prompt_en = p.get("prompt_en", "cinematic scene")
            now = config.get_kst_time()
            try:
                # Generate base image if not exists
                image_abs_path = None
                if p.get("image_url") and p.get("image_url").startswith("/output/"):
                    image_abs_path = os.path.join(config.OUTPUT_DIR, p.get("image_url").replace("/output/", ""))
                
                if not image_abs_path or not os.path.exists(image_abs_path):
                    # [CRITICAL] Determine aspect ratio based on Mode (Shorts vs Longform)
                    duration_sec = config_dict.get("duration_seconds", 300)
                    mode = config_dict.get("mode", "longform")
                    
                    if mode == "shorts":
                        aspect_ratio = "9:16"
                    elif mode == "longform":
                        aspect_ratio = "16:9"
                    else:
                        # Fallback to duration threshold
                        aspect_ratio = "16:9" if (duration_sec and duration_sec >= 60) else "9:16"
                    
                    print(f"🎨 [Auto-Pilot] Generating image for Scene {scene_num} (Mode: {mode}, Duration: {duration_sec}s, Aspect Ratio: {aspect_ratio})")
                    images = None
                    used_backend = "none"

                    # 1. Replicate Flux
                    try:
                        images = await replicate_service.generate_image(prompt=prompt_en, aspect_ratio=aspect_ratio)
                        if images:
                            used_backend = "Replicate"
                    except Exception as e:
                        print(f"⚠️ [Scene {scene_num}] Replicate failed: {e}")

                    # 2. Gemini Fallback
                    if not images:
                        try:
                            images = await gemini_service.generate_image(prompt=prompt_en, aspect_ratio=aspect_ratio)
                            if images:
                                used_backend = "Gemini"
                        except Exception as e:
                            print(f"⚠️ [Scene {scene_num}] Gemini failed: {e}")

                    # 3. Akool Fallback
                    if not images:
                        try:
                            images = await akool_service.generate_image(prompt=prompt_en, aspect_ratio=aspect_ratio)
                            if images:
                                used_backend = "Akool"
                        except Exception as e:
                            print(f"⚠️ [Scene {scene_num}] Akool failed: {e}")

                    print(f"🎨 [Scene {scene_num}] Image generated via {used_backend}")

                    if not images: return False
                    
                    filename = f"img_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.png"
                    image_abs_path = os.path.join(config.OUTPUT_DIR, filename)
                    with open(image_abs_path, 'wb') as f: f.write(images[0])
                    db.update_image_prompt_url(project_id, scene_num, f"/output/{filename}")
                
                return True # Image only path success
            except Exception as e:
                print(f"⚠️ [Auto-Pilot] Scene {scene_num} Asset Gen Error: {e}")
            return False

        # Pass 1: Image Generation (Ensure all scenes have base images)
        print("🖼️ [Auto-Pilot] Pass 1: Generating Base Images...")
        for i, p in enumerate(image_prompts):
            db.update_project(project_id, status=f"images_{i+1}/{len(image_prompts)}")
            await process_scene(p, False) # Only images in Pass 1

        # [CRITICAL] Re-fetch image_prompts from DB to get updated image_url paths
        image_prompts = db.get_image_prompts(project_id)

        # Pass 2: TTS Generation (Collected for each scene)
        print("🎙️ [Auto-Pilot] Pass 2: Generating Scene-based TTS...")
        db.update_project(project_id, status="generating_tts")
        provider = config_dict.get("voice_provider")
        voice_id = config_dict.get("voice_id")
        
        sorted_prompts = sorted(image_prompts, key=lambda x: x.get('scene_number', 0))
        
        if not provider or not voice_id:
             p_settings = db.get_project_settings(project_id) or {}
             provider = p_settings.get("voice_provider")
             voice_id = p_settings.get("voice_id") or p_settings.get("voice_name")
             
             # Fallback logic: If any scene has SFX, prioritize ElevenLabs
             has_sfx = any(p.get("sound_effects") not in [None, 'None', 'Unknown'] for p in sorted_prompts)
             if not provider and has_sfx:
                 provider = "elevenlabs"
                 if not voice_id:
                     voice_id = "4JJwo477JUAx3HV0T7n7" # Default ElevenLabs voice
             
             # Ultimate Fallback
             if not provider: provider = "google_cloud"
             if not voice_id: voice_id = "ko-KR-Neural2-A"
        
        scene_audio_map = {} # scene_number -> local_audio_path
        scene_audio_files = []
        scene_durations = []
        all_alignments = []
        cumulative_audio_time = 0.0
        temp_audios = []
        used_voices = set() # [NEW] Track voices
        import uuid

        # [NEW] Load settings for overrides
        p_settings = db.get_project_settings(project_id) or {}

        for i, p in enumerate(sorted_prompts):
            db.update_project(project_id, status=f"tts_{i+1}/{len(sorted_prompts)}")
            text = p.get('scene_text') or p.get('narrative') or p.get('script') or ""
            scene_num = p.get('scene_number')
            
            # [NEW] Voice Override
            scene_voice = p_settings.get(f"scene_{scene_num}_voice")
            current_voice_id = scene_voice if scene_voice else voice_id
            # [NEW] Voice Settings (Stability, Speed)
            voice_settings = None
            vs_json = p_settings.get(f"scene_{scene_num}_voice_settings")
            if vs_json:
                try:
                    voice_settings = json.loads(vs_json)
                except:
                    pass

            if not text:
                scene_durations.append(3.0)
                cumulative_audio_time += 3.0
                continue

            scene_filename = f"temp_tts_{project_id}_{i}_{uuid.uuid4()}.mp3"
            
            try:
                if provider == "elevenlabs":
                    result = await tts_service.generate_elevenlabs(text, current_voice_id, scene_filename, voice_settings=voice_settings)
                    if result and result.get("audio_path"):
                        audio_path = result["audio_path"]
                        duration = result.get("duration", 3.0)
                        alignment = result.get("alignment", [])
                        
                        temp_audios.append(audio_path)
                        scene_audio_files.append(audio_path)
                        scene_audio_map[scene_num] = audio_path
                        scene_durations.append(duration)
                        
                        for word_info in alignment:
                            all_alignments.append({
                                "word": word_info["word"],
                                "start": word_info["start"] + cumulative_audio_time,
                                "end": word_info["end"] + cumulative_audio_time
                            })
                        cumulative_audio_time += duration
                    else:
                        print(f"⚠️ Scene {i} ElevenLabs TTS Failed. Using default.")
                        scene_durations.append(3.0)
                        cumulative_audio_time += 3.0
                else:
                    s_out = None
                    if provider == "openai": s_out = await tts_service.generate_openai(text, current_voice_id, model="tts-1", filename=scene_filename)
                    elif provider == "gemini": s_out = await tts_service.generate_gemini(text, current_voice_id, filename=scene_filename)
                    else: s_out = await tts_service.generate_google_cloud(text, current_voice_id, filename=scene_filename)
                    
                    if s_out and os.path.exists(s_out):
                        temp_audios.append(s_out)
                        scene_audio_files.append(s_out)
                        scene_audio_map[scene_num] = s_out
                        try:
                            try:
                                from moviepy import AudioFileClip
                            except ImportError:
                                from moviepy.audio.io.AudioFileClip import AudioFileClip
                                
                            ac = AudioFileClip(s_out)
                            dur = ac.duration
                            scene_durations.append(dur)
                            cumulative_audio_time += dur
                            ac.close()
                        except Exception as ae:
                            print(f"Audio check failed: {ae}")
                            scene_durations.append(3.0)
                            cumulative_audio_time += 3.0
                    else:
                        scene_durations.append(3.0)
                        cumulative_audio_time += 3.0

                # [NEW] Auto SFX Generation (if missing) 
                # First try to find in image_prompts (if column exists) or webtoon_scenes_json
                # [NEW] sfx_mapping_json 로드 (루프 밖에서 하면 좋지만, 중단 재시작 고려하여 매번 로드/저장 안전하게)
                sfx_map_json = p_settings.get("sfx_mapping_json")
                sfx_mapping = {}
                if sfx_map_json:
                    try: sfx_mapping = json.loads(sfx_map_json)
                    except: pass
                
                # Check 1: Image Prompt Column 'sound_effects'
                s_desc = p.get('sound_effects')
                
                # Check 2: Webtoon JSON 'sound_effects' OR 'audio_direction'
                if not s_desc:
                    w_json = p_settings.get('webtoon_scenes_json')
                    if w_json:
                        try:
                            w_scenes = json.loads(w_json)
                            if i < len(w_scenes):
                                # Prioritize new audio_direction
                                ad = w_scenes[i].get('audio_direction', {})
                                if ad and ad.get('has_sfx') and ad.get('sfx_prompt'):
                                    s_desc = ad.get('sfx_prompt')
                                else:
                                    s_desc = w_scenes[i].get('sound_effects')
                        except: pass

                # Check if already generated in mapping
                # s_desc가 있고, 매핑에 없거나 파일이 없을 때 생성
                sfx_exists = str(scene_num) in sfx_mapping
                if sfx_exists:
                    # 파일 존재 확인
                    sfx_chk_path = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound", sfx_mapping[str(scene_num)])
                    if not os.path.exists(sfx_chk_path):
                        sfx_exists = False

                if not sfx_exists and s_desc and s_desc not in ['None', 'Unknown'] and len(s_desc) > 2:
                    try:
                        sfx_p_str = re.sub(r'[^\w\s,]', '', s_desc)
                        print(f"🔊 [Auto-Pilot] Generating SFX for scene {scene_num}: {sfx_p_str}")
                        sfx_d = await tts_service.generate_sound_effect(sfx_p_str[:100])
                        if sfx_d:
                            sfx_dr = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound")
                            os.makedirs(sfx_dr, exist_ok=True)
                            sfx_fn = f"sfx_scene_{scene_num:03d}_auto.mp3"
                            sfx_pth = os.path.join(sfx_dr, sfx_fn)
                            with open(sfx_pth, "wb") as f:
                                f.write(sfx_d)
                            
                            # Update Mapping and Save
                            sfx_mapping[str(scene_num)] = sfx_fn
                            db.update_project_setting(project_id, "sfx_mapping_json", json.dumps(sfx_mapping, ensure_ascii=False))
                            print(f"✅ [Auto-Pilot] SFX Saved: {sfx_fn}")
                    except Exception as se:
                        print(f"⚠️ [Auto-Pilot] SFX Gen failed: {se}")

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"⚠️ Scene {i} TTS Error: {e}")
                scene_durations.append(3.0)
                cumulative_audio_time += 3.0
        
        # All alignments 저장 (나중에 정밀 자막 생성에 사용)
        if all_alignments:
            alignment_path = os.path.join(config.OUTPUT_DIR, f"tts_alignment_{project_id}.json")
            with open(alignment_path, "w", encoding="utf-8") as f:
                json.dump(all_alignments, f, ensure_ascii=False, indent=2)
            db.update_project_setting(project_id, "tts_alignment_path", alignment_path)
            print(f"✅ [Auto-Pilot] Saved {len(all_alignments)} word alignments")
        
        # Merge Audios
        final_filename = f"auto_tts_{project_id}.mp3"
        final_audio_path = os.path.join(config.OUTPUT_DIR, final_filename)
        
        total_duration = 0.0
        if scene_audio_files:
            try:
                from moviepy.audio.AudioClip import concatenate_audioclips
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                clips = [AudioFileClip(f) for f in scene_audio_files]
                final_clip = concatenate_audioclips(clips)
                final_clip.write_audiofile(final_audio_path, logger=None)
                
                total_duration = final_clip.duration
                final_clip.close()
                for c in clips: c.close()
                
                # DB Save
                db.save_tts(project_id, provider, voice_id, final_audio_path, total_duration)
                
                # [CRITICAL] Calculate Cumulative Start Timings for Frontend
                cumulative_starts = []
                current_time = 0.0
                for dur in scene_durations:
                    cumulative_starts.append(current_time)
                    current_time += dur
                
                # 1. Save Image Start Timings (Expects START TIMES for frontend sync)
                timings_path = os.path.join(config.OUTPUT_DIR, f"image_timings_{project_id}.json")
                with open(timings_path, "w", encoding="utf-8") as f:
                     json.dump(cumulative_starts, f)
                db.update_project_setting(project_id, "image_timings_path", timings_path)
                
                # 2. Save Initial Subtitles
                # [NEW] ElevenLabs alignment 정보가 있으면 정밀 자막 생성
                auto_subtitles = []
                
                if all_alignments:
                    # 단어 타이밍을 2줄 자막으로 변환
                    auto_subtitles = self._alignment_to_subtitles(all_alignments, max_chars=25)
                    print(f"📝 [Auto-Pilot] Generated {len(auto_subtitles)} subtitles from TTS alignment (PRECISE)")
                else:
                    # 기존 로직: Scene 기반 균등 분할
                    for i, p in enumerate(sorted_prompts):
                        if i >= len(cumulative_starts): break
                        text = p.get('scene_text') or p.get('narrative') or p.get('script') or ""
                        if not text:
                            continue
                        
                        chunks = split_text_to_subtitle_chunks(text, max_chars_per_line=20, max_lines=2)
                        if not chunks:
                            continue
                        
                        scene_start = cumulative_starts[i]
                        scene_duration = scene_durations[i]
                        chunk_duration = scene_duration / len(chunks)
                        
                        for j, chunk_text in enumerate(chunks):
                            chunk_start = scene_start + (j * chunk_duration)
                            chunk_end = chunk_start + chunk_duration
                            
                            auto_subtitles.append({
                                "text": chunk_text,
                                "start": round(chunk_start, 2),
                                "end": round(chunk_end, 2)
                            })
                    
                    print(f"📝 [Auto-Pilot] Generated {len(auto_subtitles)} subtitle segments (fallback mode)")
                
                sub_path = os.path.join(config.OUTPUT_DIR, f"subtitles_{project_id}.json")
                with open(sub_path, "w", encoding="utf-8") as f:
                    json.dump(auto_subtitles, f, ensure_ascii=False, indent=2)
                db.update_project_setting(project_id, "subtitle_path", sub_path)

                print(f"✅ [Auto-Pilot] Scene-based TTS & Subtitles Complete. Total: {total_duration:.2f}s, Scenes: {len(scene_durations)}")
                
                # [NEW] Save Stats
                db.update_project_setting(project_id, "stats_audio_duration_sec", f"{total_duration:.2f}")
                db.update_project_setting(project_id, "stats_used_voices", json.dumps(list(used_voices), ensure_ascii=False))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Audio Merge Failed: {e}")
                # Fallback to single file gen logic if merge fails?
        else:
             print("❌ No audio generated.")
        
        # [NEW] Pass 3: Video Generation (Now we have both Images and Audio)
        log_debug(f"📹 [Auto-Pilot] Pass 3: Generating Video Components... Count: {video_scene_count}, Engine: {video_engine}")
        from services.akool_service import akool_service

        # Re-fetch prompts to get latest image/audio URLs
        image_prompts = db.get_image_prompts(project_id)
        p_settings = db.get_project_settings(project_id) or {} # [NEW] Load settings
        
        for i, p in enumerate(image_prompts):
            is_vid = i < video_scene_count
            log_debug(f"  > Scene {p.get('scene_number')}: is_vid={is_vid}, has_image={bool(p.get('image_url'))}")
            if not is_vid: continue
            
            scene_num = p.get("scene_number")
            db.update_project(project_id, status=f"videos_{i+1}/{video_scene_count}")
            
            image_url = p.get("image_url")
            if not image_url: continue
            image_abs_path = os.path.join(config.OUTPUT_DIR, image_url.replace("/output/", ""))
            
            # [FIX] Skip re-generation if video already exists (e.g. generated on image gen page)
            existing_video_url = p.get("video_url")
            if existing_video_url:
                existing_video_path = os.path.join(config.OUTPUT_DIR, existing_video_url.replace("/output/", ""))
                if os.path.exists(existing_video_path):
                    print(f"  ⏭️ [Auto-Pilot] Scene {scene_num}: Video already exists → SKIP re-generation. ({os.path.basename(existing_video_path)})")
                    continue  # Use existing video, don't regenerate
                else:
                    print(f"  ⚠️ [Auto-Pilot] Scene {scene_num}: video_url set but file missing → Regenerating.")

            
            now = config.get_kst_time()
            
            # [Smart Engine Switch]
            scene_text = p.get("scene_text", "").strip()
            has_dialogue = bool(scene_text and len(scene_text) > 1 and scene_text != "None")
            
            # [NEW] Check LipSync Preference
            use_lipsync_val = p_settings.get("use_lipsync")
            use_lipsync = True
            if use_lipsync_val is not None:
                if isinstance(use_lipsync_val, str): use_lipsync = (use_lipsync_val.lower() == 'true' or use_lipsync_val == '1')
                else: use_lipsync = bool(use_lipsync_val)
            try:
                # [SMART ENGINE SWITCH]
                # Priority:
                # 1. Manual Override (from planning/settings)
                # 2. Logic (Dialogue + Lipsync -> Akool, else -> Wan)
                
                manual_engine = p_settings.get(f"scene_{scene_num}_engine")
                if manual_engine in ["wan", "akool", "image"]:
                    local_engine = manual_engine
                    print(f"🎯 [Manual Override] Scene {scene_num} -> {local_engine}")
                else:
                    local_engine = "akool" if (has_dialogue and use_lipsync) else "wan"
                
                # [EXPERIMENTAL] 건너뛰기 로직 보완 -> [UPDATED] Image 엔진도 비디오 파일 생성 (2D Pan/Zoom)
                if local_engine == "image":
                    print(f"🖼️ [Image-Only] Scene {scene_num} using 2D Pan/Zoom Motion...")
                    # Motion type determined by manual override or default 'zoom_in'
                    motion_type = p_settings.get(f"scene_{scene_num}_motion", "zoom_in")
                    
                    # [NEW] Webtoon Settings from DB (Global Preference)
                    # p_settings might have project specific override, but for now we trust Global Settings
                    # Default: True
                    w_auto = db.get_global_setting("webtoon_auto_split", True, value_type="bool")
                    w_pan = db.get_global_setting("webtoon_smart_pan", True, value_type="bool")
                    w_zoom = db.get_global_setting("webtoon_convert_zoom", True, value_type="bool")

                    # Create 2D Motion Video
                    motion_bytes = await video_service.create_image_motion_video(
                        image_path=image_abs_path,
                        duration=video_duration,
                        motion_type=motion_type,
                        width=1080, height=1920, # Default vertical shorts
                        auto_split=w_auto,
                        smart_pan=w_pan,
                        convert_zoom=w_zoom
                    )
                    
                    if motion_bytes:
                        filename = f"vid_img_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                        out = os.path.join(config.OUTPUT_DIR, filename)
                        with open(out, 'wb') as f: f.write(motion_bytes)
                        db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                    continue

                # [USER MASTER SETTING APPLIED]
                # GEMINI가 분석한 motion_desc(사용자 원칙이 반영된 상세 지침)를 우선 사용
                base_visual = p.get('motion_desc') or p.get('prompt_en') or p.get('visual_desc') or "Cinematic motion"
                manual_motion_desc = p_settings.get(f"scene_{scene_num}_motion_desc")
                
                if local_engine == "wan":
                    if manual_motion_desc:
                        # 사용자가 수동으로 입력한 모션 묘사가 있으면 결합
                        final_prompt = f"{base_visual}, {manual_motion_desc}"
                        print(f"🔥 [Wan Content Motion Override] Scene {scene_num}: {manual_motion_desc}")
                    else:
                        # AI가 생성한 motion_desc를 그대로 사용 (이미 충분히 상세함)
                        final_prompt = base_visual
                        print(f"🎬 [Wan Production Prompt] Scene {scene_num}: {final_prompt[:100]}...")
                    
                    # 카메라 이동 추가
                    manual_motion = p_settings.get(f"scene_{scene_num}_motion")
                    if manual_motion:
                        # [NEW] Webtoon Motion Prompt Integration
                        # Retrieve custom prompts from Global Settings
                        w_pan_prompt = db.get_global_setting("webtoon_motion_pan", "Slow upward cinematic camera pan, subtle 2.5D parallax depth effect, soft volumetric lighting, floating dust particles, epic dramatic atmosphere, smooth motion, no distortion")
                        w_zoom_prompt = db.get_global_setting("webtoon_motion_zoom", "Slow push-in camera movement, focus on character’s eyes, subtle breathing motion, soft rim lighting, cinematic depth of field, emotional atmosphere")
                        w_action_prompt = db.get_global_setting("webtoon_motion_action", "Strong parallax effect, embers floating in the air, light flicker from fire, slight cinematic camera shake, intense dramatic lighting, high energy atmosphere")

                        # Map standard motion keys to Webtoon Styles
                        motion_map = {
                            "zoom_in": w_zoom_prompt,
                            "zoom_out": "dramatic zoom out", # Keep generic for now or map to zoom?
                            "pan_left": "cinematic pan left",
                            "pan_right": "cinematic pan right",
                            "pan_up": w_pan_prompt, # Map 'pan_up' to Vertical Pan style
                            "pan_down": w_pan_prompt, # Map 'pan_down' to Vertical Pan style
                            "tilt_up": w_pan_prompt,
                            "tilt_down": w_pan_prompt,
                            "shake": w_action_prompt, # Map 'shake' to Action style
                            "action": w_action_prompt, # Explicit 'action' key if used
                            "dynamic": w_action_prompt
                        }

                        if manual_motion in motion_map:
                            selected_prompt = motion_map[manual_motion]
                            final_prompt += f", {selected_prompt}"
                            print(f"🎬 [Wan Camera Move] Scene {scene_num}: {manual_motion} -> {selected_prompt[:50]}...")
                        else:
                            # Fallback for unmapped standard motions
                            final_prompt += f", {manual_motion.replace('_', ' ')} motion"
                else:
                    final_prompt = base_visual
                print(f"🤖 [Auto-Switch] Scene {scene_num}: Dialogue={has_dialogue} -> Engine={local_engine}")

                if local_engine == "akool":
                    audio_abs_path = scene_audio_map.get(scene_num)
                    if not audio_abs_path:
                        log_debug(f"⚠️ [Akool] No audio found for scene {scene_num}. Switching to Wan.")
                        local_engine = "wan" # Fallback if no audio
                    else:
                        try:
                            log_debug(f"🎭 [Akool] Generating Talking Avatar for Scene {scene_num}...")
                            video_bytes = await akool_service.generate_talking_avatar(image_abs_path, audio_abs_path)
                            if video_bytes:
                                filename = f"vid_akool_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                                out = os.path.join(config.OUTPUT_DIR, filename)
                                with open(out, 'wb') as f: f.write(video_bytes)
                                db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                                log_debug(f"✅ [Akool] LipSync Success for Scene {scene_num}")
                        except Exception as ak_e:
                            log_debug(f"⚠️ [Akool] Error for scene {scene_num}: {ak_e}. Falling back to Wan...")
                            local_engine = "wan" # Fallback to Wan on Akool error
                
                    # Wan / Replicate (Enhanced for Camera Moves)
                    # [NEW] Dual Engine Support: Check User Preference
                    preferred_engine = p_settings.get("video_engine", "wan") # 'wan' or 'akool'
                    
                    if preferred_engine in ["akool", "akool_premium"]:
                        try:
                            # [MODIFIED] Use Akool Premium (v4 API) instead of old v1 I2V
                            video_data = await akool_service.generate_akool_video_v4(
                                image_abs_path, 
                                prompt=final_prompt,
                                duration=int(video_duration),
                                resolution="720p"
                            )
                            
                            if video_data:
                                filename = f"vid_akool_premium_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                                out = os.path.join(config.OUTPUT_DIR, filename)
                                with open(out, 'wb') as f: f.write(video_data)
                                db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                                print(f"✅ [Akool] Premium I2V Success for Scene {scene_num}")
                            else:
                                raise Exception("Empty data returned from Akool Premium")
                                
                        except Exception as ak_i2v_e:
                            print(f"⚠️ [Akool] I2V Failed: {ak_i2v_e}. Fallback to Replicate(Wan)...")
                            # Fallback logic below (it will flow into Replicate block if we structure it right, 
                            # or we duplicate call here. Let's redirect to Replicate block)
                            preferred_engine = "wan" 

                    if preferred_engine == "wan":
                        # [FIX] Skip Wan for Vertical Pan scenes (preserve aspect ratio)
                        manual_motion = p_settings.get(f"scene_{scene_num}_motion")
                        if manual_motion in ["pan_down", "pan_up", "vertical_pan"]:
                            print(f"⏩ [Auto-Pilot] Scene {scene_num} is Vertical Pan ({manual_motion}). Skipping Wan to preserve full resolution.")
                            continue

                        try:
                            print(f"📹 [Auto-Pilot] Generating Wan Video for Scene {scene_num}")
                            
                            # [FIX] Use full original image for Wan 2.1 if available (prevents character cropping)
                            wan_asset_filename = p_settings.get(f"scene_{scene_num}_wan_image", "")
                            if wan_asset_filename:
                                wan_asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image")
                                wan_image_path = os.path.join(wan_asset_dir, wan_asset_filename)
                                if os.path.exists(wan_image_path):
                                    print(f"  🎯 [Wan] Using FULL original image: {wan_asset_filename}")
                                    wan_source_path = wan_image_path
                                else:
                                    wan_source_path = image_abs_path
                                    print(f"  ⚠️ [Wan] wan_asset not found, fallback to sliced: {os.path.basename(image_abs_path)}")
                            else:
                                wan_source_path = image_abs_path
                                print(f"  ℹ️ [Wan] No wan_asset configured. Using sliced panel: {os.path.basename(image_abs_path)}")
                            
                            video_data = await replicate_service.generate_video_from_image(
                                wan_source_path, 
                                prompt=final_prompt,
                                duration=video_duration,
                                method=motion_method
                            )
                            if video_data:
                                filename = f"vid_wan_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                                out = os.path.join(config.OUTPUT_DIR, filename)
                                with open(out, 'wb') as f: f.write(video_data)
                                db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                                    df.write(f"[{datetime.now()}] ✅ Successfully generated Wan video for Scene {scene_num}\n")
                        except Exception as wan_e:
                            print(f"⚠️ [Wan] Failed: {wan_e}. Falling back to Akool Seedance...")
                            try:
                                video_data = await akool_service.generate_akool_video_v4(
                                    image_abs_path,
                                    prompt=final_prompt,
                                    duration=int(video_duration),
                                    resolution="720p"
                                )
                                if video_data:
                                    filename = f"vid_seedance_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                                    out = os.path.join(config.OUTPUT_DIR, filename)
                                    with open(out, 'wb') as f: f.write(video_data)
                                    db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                                    print(f"✅ [Akool Seedance] Fallback Success for Scene {scene_num}")
                                else:
                                    raise Exception("Empty data from Akool Seedance")
                            except Exception as seed_e:
                                print(f"❌ [Akool Seedance] Also failed: {seed_e}")
                                # Both engines failed, continue to next scene
            except Exception as ve:
                err_msg = f"⚠️ [Auto-Pilot] Video generation failed for Scene {scene_num}: {ve}"
                print(err_msg)
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                    df.write(f"[{datetime.now()}] {err_msg}\n")

        # [NEW] Pass 4: Finalize Timeline (AFTER video generation)
        print("🎞️ [Auto-Pilot] Pass 4: Finalizing Timeline Mapping...")
        updated_prompts = db.get_image_prompts(project_id)
        sorted_updated = sorted(updated_prompts, key=lambda x: x.get('scene_number', 0))
        
        timeline_images = [p.get('video_url') or p.get('image_url') for p in sorted_updated]
        timeline_images = [img for img in timeline_images if img]
        
        tl_images_path = os.path.join(config.OUTPUT_DIR, f"timeline_images_{project_id}.json")
        with open(tl_images_path, "w", encoding="utf-8") as f:
            json.dump(timeline_images, f, ensure_ascii=False, indent=2)
        db.update_project_setting(project_id, "timeline_images_path", tl_images_path)
        print(f"✅ [Auto-Pilot] Timeline Finalized with {len(timeline_images)} assets.")

        # Cleanup temps
        for f in temp_audios:
            try: os.remove(f)
            except: pass

    async def _generate_thumbnail(self, project_id: int, script: str, config_dict: dict):
        """대본 기반 썸네일 자동 기획 및 생성"""
        print(f"🎨 [Auto-Pilot] 썸네일 자동 생성 중... Project: {project_id}")

        # 1. 썸네일 기획 (Hook & Visual Concept)
        hook_text = "Must Watch"
        hook_candidates = []
        hook_reasoning = ""
        visual_concept = "A high quality dramatic scene"
        idea_concept = ""

        try:
            project_settings = db.get_project_settings(project_id) or {}
            image_style = config_dict.get("image_style") or project_settings.get("image_style", "realistic")
            thumb_style = config_dict.get("thumbnail_style") or project_settings.get("thumbnail_style", "face")

            characters = db.get_project_characters(project_id)
            char_context = ""
            if characters:
                char_names = [c.get("name") for c in characters if c.get("name")]
                char_context = f"\n[Featured Characters]: {', '.join(char_names)}"

            hook_prompt = prompts.GEMINI_THUMBNAIL_HOOK_TEXT.format(
                script=f"{script[:2000]}{char_context}",
                thumbnail_style=thumb_style,
                image_style=image_style,
                target_language="ko"
            )

            hook_result = await gemini_service.generate_text(hook_prompt, temperature=0.7)
            import re
            json_match = re.search(r'\{[\s\S]*\}', hook_result)
            if json_match:
                hook_data = json.loads(json_match.group())
                hook_candidates = hook_data.get("texts", [])
                hook_reasoning = hook_data.get("reasoning", "")
                if hook_candidates:
                    hook_text = hook_candidates[0]

            idea_prompt = prompts.THUMBNAIL_IDEA_PROMPT.format(
                topic=project_settings.get("topic", "AI Video"),
                script_summary=script[:1000]
            )
            idea_result = await gemini_service.generate_text(idea_prompt, temperature=0.7)
            json_match_idea = re.search(r'\{[\s\S]*\}', idea_result)
            if json_match_idea:
                idea_data = json.loads(json_match_idea.group())
                visual_concept = idea_data.get("image_prompt", visual_concept)
                idea_concept = idea_data.get("hook_text", "")

        except Exception as e:
            print(f"⚠️ [Auto-Pilot] Thumbnail Planning Error: {e}")
            hook_text = project_settings.get("title", "Must Watch") if project_id else "Must Watch"

        # [SAVE] 중간 결과 저장 — 썸네일 페이지에서 작업 흔적 표시용
        try:
            # 후킹 문구 후보 저장
            if hook_candidates:
                db.update_project_setting(project_id, "thumbnail_hook_texts", json.dumps(hook_candidates, ensure_ascii=False))
            if hook_reasoning:
                db.update_project_setting(project_id, "thumbnail_hook_reasoning", hook_reasoning)
            # 시각 컨셉 저장 (아이디어)
            db.update_project_setting(project_id, "thumbnail_idea_prompt", visual_concept)
            if idea_concept:
                db.update_project_setting(project_id, "thumbnail_idea_concept", idea_concept)
            print(f"💾 [Auto-Pilot] 썸네일 중간 결과 저장 완료 (후보 {len(hook_candidates)}개)")
        except Exception as e:
            print(f"⚠️ [Auto-Pilot] 썸네일 중간 결과 저장 실패: {e}")

        # 2. 배경 이미지 생성
        try:
            # [NEW] Art Style & Layout Inheritance
            image_style_key = config_dict.get("image_style", config_dict.get("visual_style", "realistic"))
            style_presets = db.get_style_presets()
            style_data = style_presets.get(image_style_key, {})
            style_prefix_raw = style_data.get("prompt_value", "photorealistic")

            # [CRITICAL] 썸네일 배경용 스타일 분리
            # 캐릭터 중심 스타일(wimpy/k_manhwa 등)은 캐릭터 설명이 길어서 배경 프롬프트에 부적합
            # → 간결한 스타일 키워드만 사용
            _thumb_style_overrides = {
                "k_manhwa": "Clean minimalist cartoon illustration style, bold outlines, flat colors, white background",
                "wimpy": "Diary of a Wimpy Kid illustration style, simple black and white sketch, clean lines",
                "jollaman": "Simple stick figure cartoon style, bold outlines, flat 2D, clean white background",
            }
            if image_style_key in _thumb_style_overrides:
                thumb_style_prompt = _thumb_style_overrides[image_style_key]
            elif len(style_prefix_raw) > 200:
                # 긴 프롬프트는 첫 200자만 사용 (캐릭터 세부 묘사 제거)
                thumb_style_prompt = style_prefix_raw[:200].rsplit(',', 1)[0]
            else:
                thumb_style_prompt = style_prefix_raw

            # [NEW] Layout Style
            thumbnail_style_key = config_dict.get("thumbnail_style", "face")
            thumb_presets = db.get_thumbnail_style_presets()
            thumb_preset = thumb_presets.get(thumbnail_style_key, {})
            layout_desc = thumb_preset.get("prompt", "")

            # Combine for thumbnail background (캐릭터 설명 제거 - 배경만 생성)
            final_thumb_prompt = f"ABSOLUTELY NO TEXT, NO WORDS, NO LETTERS. Style: {thumb_style_prompt}. Composition: {layout_desc}. Subject: {visual_concept}. High quality, vibrant colors."

            # [CRITICAL] Determine aspect ratio based on duration (Long-form vs Shorts)
            duration_sec = config_dict.get("duration_seconds", 300)
            aspect_ratio = "16:9" if duration_sec > 60 else "9:16"
            
            print(f"🎨 [Auto-Pilot] Generating thumbnail background. Style: {image_style_key}, Aspect: {aspect_ratio}")
            print(f"📝 Prompt: {final_thumb_prompt[:120]}...")
            
            images = None
            
            # 1. Replicate (Primary)
            try:
                print(f"🎨 [Auto-Pilot Thumb] Attempting Replicate (Primary)...")
                images = await replicate_service.generate_image(prompt=final_thumb_prompt, aspect_ratio=aspect_ratio)
            except Exception as e:
                print(f"⚠️ [Auto-Pilot Thumb] Replicate failed: {e}")
            
            # 2. Gemini Fallback (with safe generic retry)
            if not images:
                try:
                    print(f"🎨 [Auto-Pilot Thumb] Attempting Gemini Imagen (Fallback 1)...")
                    images = await gemini_service.generate_image(final_thumb_prompt, aspect_ratio=aspect_ratio)
                except Exception as e:
                    print(f"⚠️ [Auto-Pilot Thumb] Gemini failed: {e}")
                    # [FALLBACK] Retry with generic prompt
                    print("🔄 [Auto-Pilot Thumb] Retrying Gemini with generic prompt due to safety/filter...")
                    generic_prompt = f"Minimal aesthetic abstract background, Style: {style_prefix}, 8k, high quality"
                    try:
                        images = await gemini_service.generate_image(generic_prompt, aspect_ratio=aspect_ratio)
                    except: pass

            # 3. Akool Fallback
            if not images:
                try:
                    print(f"🎨 [Auto-Pilot Thumb] Attempting AKOOL (Final Fallback)...")
                    images = await akool_service.generate_image(prompt=final_thumb_prompt, aspect_ratio=aspect_ratio)
                except Exception as e:
                    print(f"⚠️ [Auto-Pilot Thumb] Akool failed: {e}")
            
            if not images: 
                print("⚠️ [Auto-Pilot] No images generated for thumbnail. Skipping synthesis.")
                return

            now = config.get_kst_time()
            bg_filename = f"thumb_bg_{project_id}_{now.strftime('%H%M%S')}.png"
            bg_path = os.path.join(config.OUTPUT_DIR, bg_filename)
            with open(bg_path, 'wb') as f: f.write(images[0])
            
            # 3. 텍스트 합성 (저장된 설정 반영)
            from services.thumbnail_service import thumbnail_service
            final_filename = f"thumbnail_{project_id}_{now.strftime('%H%M%S')}.jpg"
            final_path = os.path.join(config.OUTPUT_DIR, final_filename)
            
            # [PRIORITY 1] Check Autopilot Config / Project Settings for Explicit Style
            project_settings = db.get_project_settings(project_id) or {}
            requested_style = config_dict.get("thumbnail_style") or project_settings.get("thumbnail_style")
            
            # 스타일 레시피 기반 텍스트 레이어 생성 (항상 스타일별 레시피 사용)
            style_for_recipe = requested_style or "face"
            text_layers = thumbnail_service.get_style_recipe(style_for_recipe, hook_text)

            # [SAVE] 배경 이미지 URL 저장 (삭제하지 않고 유지)
            bg_web_path = f"/output/{bg_filename}"
            db.update_project_setting(project_id, "thumbnail_bg_url", bg_web_path)

            # [SAVE] 텍스트 레이어 정보 저장
            db.update_project_setting(project_id, "thumbnail_text_layers", json.dumps(text_layers, ensure_ascii=False))

            success = thumbnail_service.create_thumbnail(bg_path, text_layers, final_path)

            if success:
                web_path = f"/output/{final_filename}"
                db.update_project_setting(project_id, "thumbnail_url", web_path)
                msg = f"✅ [Auto-Pilot] 썸네일 생성 완료: {web_path}"
                print(msg)
            else:
                msg = "❌ [Auto-Pilot] 썸네일 텍스트 합성 실패 (create_thumbnail returned False)"
                print(msg)
            
        except Exception as e:
            msg = f"❌ [Auto-Pilot] 썸네일 생성 예외: {e}"
            print(msg)
            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                    df.write(f"[{datetime.now()}] {msg}\n")
            except: pass

    async def _render_video(self, project_id: int):
        db.update_project(project_id, status="rendering")
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        settings = db.get_project_settings(project_id) or {}
        
        # 1. Load Subtitles (Prefer Saved)
        # 1. Load Subtitles (Prefer Saved)
        subs = []
        
        # [NEW] Check user preference for subtitles
        use_sub_val = settings.get("use_subtitles")
        use_subtitles = True # Default
        if use_sub_val is not None:
            if isinstance(use_sub_val, str): use_subtitles = (use_sub_val.lower() == 'true' or use_sub_val == '1')
            else: use_subtitles = bool(use_sub_val)

        if use_subtitles and tts_data:
            subtitle_path = settings.get("subtitle_path")
            if subtitle_path and os.path.exists(subtitle_path):
                try:
                    with open(subtitle_path, "r", encoding="utf-8") as f:
                        subs = json.load(f)
                except: pass
                
            if not subs:
                print("🔍 [Auto-Pilot] No saved subtitles found. Generating via Whisper...")
                try:
                    audio_path = tts_data["audio_path"]
                    subs = video_service.generate_aligned_subtitles(audio_path, script_data["full_script"])
                except Exception as sub_e: 
                    print(f"⚠️ Subtitle Gen Error: {sub_e}")
            
            if not subs: 
                subs = video_service.generate_smart_subtitles(script_data["full_script"], tts_data["duration"])
        elif not use_subtitles:
            print("🚫 [Auto-Pilot] Subtitles disabled manually.")
        else:
            print("⚠️ [Auto-Pilot] Cannot generate subtitles: TTS data missing.")

        # 2. Load Timeline Images
        # [FIX] Always use fresh DB data from image_prompts (includes video_url from Pass 3)
        # The timeline_images_path JSON file is created during Pass 2 (before video generation)
        # so it may not contain the latest video_url values.
        images = []
        sorted_prompts = sorted(images_data, key=lambda x: x.get('scene_number', 0))
        for img in sorted_prompts:
            # Priority: video_url (motion video) > wan_image (Original Tall) > image_url (Sliced Image)
            video_url = img.get("video_url")
            image_url = img.get("image_url")
            scene_num = img.get('scene_number')
            
            # [FIX] Check for forced original image (for Vertical Pan)
            wan_asset_filename = settings.get(f"scene_{scene_num}_wan_image")
            wan_path = None
            if wan_asset_filename:
                 wan_path_check = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "image", wan_asset_filename)
                 if os.path.exists(wan_path_check):
                     wan_path = wan_path_check

            best_path = None

            # Priority Logic Refined:
            # 1. Existing Video (video_url) -> Use generated video
            # 2. Vertical Pan (Type 1) -> Force Original Tall Image (wan_path) to allow scrolling if no video
            # 3. Sliced Panel (image_url) -> Use standard panel

            check_path = None
            manual_motion = settings.get(f"scene_{scene_num}_motion")
            is_vertical_pan = manual_motion in ["pan_down", "pan_up", "vertical_pan"]
            
            if not video_url:
                # [FIX] If DB fails to save video_url, directly check file system
                import glob
                manual_files = glob.glob(os.path.join(config.OUTPUT_DIR, f"vid_*_{project_id}_{scene_num}_*.mp4"))
                if manual_files:
                    manual_files.sort(key=os.path.getmtime, reverse=True)
                    video_url = manual_files[0]
                    print(f"📸 [Auto-Pilot] Scene {scene_num}: Found unlinked manual video: {os.path.basename(video_url)}")

            if video_url:
                if video_url.startswith("/output/"):
                    fpath = os.path.join(config.OUTPUT_DIR, video_url.replace("/output/", ""))
                else:
                    fpath = os.path.join(config.OUTPUT_DIR, video_url.split("/")[-1])
                
                if os.path.exists(fpath):
                    best_path = fpath
                    print(f"📸 [Auto-Pilot] Scene {scene_num}: Using VIDEO - {os.path.basename(fpath)}")
                    
            elif is_vertical_pan and wan_path:
                 best_path = wan_path
                 print(f"📸 [Auto-Pilot] Scene {scene_num}: Vertical Pan detected. FORCING Original Tall Image - {wan_asset_filename}")
            
            # Note: wan_path is usually the FULL original strip. 
            # If not panning, we should use the sliced panel (image_url) to focus on the specific cut.
            # So we do NOT fallback to wan_path unless it's a pan.

            if not best_path and image_url:
                 if image_url.startswith("/output/"):
                    fpath = os.path.join(config.OUTPUT_DIR, image_url.replace("/output/", ""))
                 else:
                    fpath = os.path.join(config.OUTPUT_DIR, image_url.split("/")[-1])
                 
                 if os.path.exists(fpath):
                     best_path = fpath
                     print(f"📸 [Auto-Pilot] Scene {scene_num}: Using Sliced Image (Fallback) - {os.path.basename(fpath)}")

            if best_path: 
                images.append(best_path)
                
        audio_path = tts_data["audio_path"] if tts_data else None
        output_filename = f"autopilot_{project_id}_{config.get_kst_time().strftime('%H%M%S')}.mp4"

        # [IMPROVED] Calculate Durations from Start Timings
        image_durations = 5.0 # Default fallback
        timings_path = settings.get("image_timings_path")
        
        smart_sync_enabled = False
        if tts_data and timings_path and os.path.exists(timings_path):
            try:
                with open(timings_path, "r", encoding="utf-8") as f:
                    loaded_starts = json.load(f)
                
                if loaded_starts:
                    # If the file contains DURATIONS (old format), we need to detect it.
                    # Usually start times begin with 0.0. 
                    # If there are many values and sum is > total_duration, then if it's start times, the last value would be < total_duration.
                    # Best check: Is it monotonically increasing?
                    is_pacing_format = all(x < y for x, y in zip(loaded_starts, loaded_starts[1:])) if len(loaded_starts) > 1 else True
                    
                    if is_pacing_format:
                        # Convert Start Times to Durations
                        total_dur = tts_data["duration"]
                        durations = []
                        for i in range(len(loaded_starts)):
                            if i < len(loaded_starts) - 1:
                                durations.append(loaded_starts[i+1] - loaded_starts[i])
                            else:
                                durations.append(max(2.0, total_dur - loaded_starts[i]))
                        image_durations = durations
                    else:
                        # Old format: Durations
                        image_durations = loaded_starts
                    
                    # Align with images count
                    if len(image_durations) >= len(images):
                        image_durations = image_durations[:len(images)]
                    else:
                        rem_dur = tts_data["duration"] - sum(image_durations) if isinstance(image_durations, list) else 0
                        rem_cnt = len(images) - len(image_durations)
                        if rem_cnt > 0:
                            avg = max(3.0, rem_dur / rem_cnt)
                            image_durations = image_durations + [avg] * rem_cnt

                    print(f"✅ [Auto-Pilot] Start-Time Sync Applied: {len(image_durations)} scenes")
                    smart_sync_enabled = True
            except Exception as e:
                print(f"⚠️ Failed to load smart timings: {e}")

        # 2. Fallback to Simple N-Division
        if not smart_sync_enabled:
            total_dur = tts_data["duration"] if tts_data else (len(images) * 5.0)
            image_durations = total_dur / len(images) if images else 5.0
            print(f"⚠️ [Auto-Pilot] Fallback to N-Division Sync ({image_durations if not isinstance(image_durations, list) else 'list'}s per image)")
        
        # [NEW] Determine Resolution based on App Mode
        app_mode = settings.get("app_mode", "longform")
        resolution = (1920, 1080) if app_mode == "longform" else (1080, 1920)
        print(f"🎬 [Auto-Pilot] Rendering video with resolution: {resolution} (Mode: {app_mode})")

        # [NEW] Collect SFX Mapping
        # [NEW] Collect SFX Mapping from JSON
        sfx_map = {}
        sfx_map_json = settings.get("sfx_mapping_json")
        if sfx_map_json:
            try:
                raw_sfx_map = json.loads(sfx_map_json)
                for s_num_str, sfx_filename in raw_sfx_map.items():
                    sfx_abs_path = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound", sfx_filename)
                    if os.path.exists(sfx_abs_path):
                         sfx_map[str(s_num_str)] = sfx_abs_path
            except Exception as e:
                print(f"⚠️ Failed to parse SFX mapping: {e}")

        # [NEW] Handle BGM (Download if URL exists)
        bgm_url = settings.get("bgm_url")
        bgm_path = None
        if bgm_url:
            try:
                import requests
                bgm_filename = f"bgm_{project_id}.mp3"
                local_bgm_path = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "sound", bgm_filename)
                os.makedirs(os.path.dirname(local_bgm_path), exist_ok=True)
                
                if not os.path.exists(local_bgm_path):
                    print(f"🎵 [Auto-Pilot] Downloading BGM: {bgm_url}")
                    r = requests.get(bgm_url, timeout=30)
                    if r.status_code == 200:
                        with open(local_bgm_path, "wb") as f:
                            f.write(r.content)
                
                if os.path.exists(local_bgm_path):
                    bgm_path = local_bgm_path
                    # Inject into settings so video_service can find it
                    settings["bgm_path"] = bgm_path
            except Exception as bgme:
                print(f"⚠️ BGM Download failed: {bgme}")

        # [NEW] Collect Focal Points and Motions
        f_points = []
        effects = []
        for i, img in enumerate(sorted_prompts):
            s_num = img.get('scene_number')
            f_points.append(img.get("focal_point_y", 0.5))
            
            # Fetch motion from settings (saved from webtoon producer or manual)
            eff = settings.get(f"scene_{s_num}_motion")
            if not eff or eff == 'random':
                # [NEW] Level 2: Gemini Vision 자동 분류로 최적 효과 선택
                # video_service.create_slideshow에서 'auto_classify' 감지 시
                # classify_asset_type()을 호출하여 자동 결정
                eff = 'auto_classify'
            effects.append(eff)
            log_debug(f"🎞️ [Render] Scene {s_num}: Effect={eff}")

        final_path = video_service.create_slideshow(
            images=images, audio_path=audio_path, output_filename=output_filename,
            duration_per_image=image_durations, subtitles=subs, project_id=project_id,
            resolution=resolution, subtitle_settings=settings, sfx_map=sfx_map,
            focal_point_ys=f_points, image_effects=effects
        )

        db.update_project_setting(project_id, "video_path", f"/output/{output_filename}")
        db.update_project(project_id, status="rendered")

    async def _run_topview_workflow(self, project_id: int, config_dict: dict):
        """TopView API를 이용한 커머스 비디오 생성 워크플로우"""
        product_url = config_dict.get("product_url")
        if not product_url:
            print("⚠️ [TopView] Product URL is missing")
            db.update_project(project_id, status="error")
            return

        print(f"🛍️ [TopView] Starting Commerce Workflow for {product_url}")
        db.update_project(project_id, status="topview_requested")

        # 1. 태스크 시작
        from services.topview_service import topview_service
        result = await topview_service.create_video_by_url(product_url)
        
        if not result or (isinstance(result, dict) and "id" not in result):
            print(f"❌ [TopView] Failed to start task: {result}")
            db.update_project(project_id, status="error")
            return

        task_id = result["id"]
        db.update_project_setting(project_id, "topview_task_id", task_id)
        db.update_project(project_id, status="topview_processing")

        # 2. 폴링 (상태 확인)
        max_retries = 60 # 약 10분 (10초 간격)
        retry_count = 0
        video_url = None

        while retry_count < max_retries:
            await asyncio.sleep(10)
            status_data = await topview_service.get_task_status(task_id)
            
            if not status_data:
                retry_count += 1
                continue

            status = status_data.get("status")
            print(f"⏳ [TopView] Processing... ({status})")

            if status == "completed":
                video_url = status_data.get("video_url")
                break
            elif status == "failed":
                print(f"❌ [TopView] Task failed: {status_data}")
                db.update_project(project_id, status="error")
                return
            
            retry_count += 1

        if not video_url:
            print("❌ [TopView] Task timed out or no video URL received")
            db.update_project(project_id, status="error")
            return

        # 3. 비디오 다운로드 및 저장
        db.update_project(project_id, status="topview_downloading")
        target_path = os.path.join(config.OUTPUT_DIR, f"topview_{project_id}.mp4")
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(video_url, timeout=300)
                with open(target_path, "wb") as f:
                    f.write(resp.content)
            
            # DB 업데이트
            web_path = f"/output/topview_{project_id}.mp4"
            db.update_project_setting(project_id, "video_path", web_path)
            db.update_project(project_id, status="rendered")
            
            print(f"✅ [TopView] Video generated and saved: {target_path}")

            # 4. YouTube 업로드 (기본 로직 활용)
            await self._upload_video(project_id, target_path)
            
        except Exception as e:
            print(f"❌ [TopView] Download/Save Error: {e}")
            db.update_project(project_id, status="error")

    async def _upload_video(self, project_id: int, video_path: str):
        now = config.get_kst_time()
        
        # Load settings
        p_settings = db.get_project_settings(project_id) or {}
        
        # Determine Privacy & Schedule
        privacy = p_settings.get("upload_privacy", "private")
        schedule_at = p_settings.get("upload_schedule_at")
        
        publish_time = None
        if privacy == "scheduled" or schedule_at:
            if schedule_at:
                try:
                    # Validate format or parse
                    # Format expected: 2026-02-12T08:00:00 or ISO
                    if "T" not in schedule_at:
                        # Simple format YYYY-MM-DD HH:MM
                        dt = datetime.strptime(schedule_at, "%Y-%m-%d %H:%M")
                        publish_time = dt.isoformat()
                    else:
                        publish_time = schedule_at
                except:
                    print(f"⚠️ [Upload] Invalid schedule format: {schedule_at}. Falling back to default.")
            
            if not publish_time:
                # Default: Next day 8 AM
                publish_time = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0).isoformat()
            
            # YouTube API requires privacyStatus to be 'private' for scheduled uploads
            privacy = "private" 

        ai_title = p_settings.get("title") or f"AI Auto Video {now.date()}"
        ai_desc = p_settings.get("description") or "#Shorts #AI"
        ai_tags_str = p_settings.get("hashtags") or "ai,shorts"
        ai_tags = [t.strip() for t in ai_tags_str.split(",") if t.strip()]

        # [NEW] Multi-Channel Support: Resolve Token Path
        token_path = None
        channel_id = p_settings.get("youtube_channel_id")
        if channel_id:
            try:
                # get_channel must be implemented in database.py
                channel = db.get_channel(channel_id)
                if channel and channel.get("credentials_path"):
                    cand_path = channel["credentials_path"]
                    if os.path.exists(cand_path):
                        token_path = cand_path
                        print(f"🔑 [Upload] Using channel token: {channel.get('name')} ({token_path})")
            except Exception as ce:
                print(f"⚠️ [Upload] Failed to resolve channel {channel_id}: {ce}")

        try:
            # 1. Video Upload
            print(f"🚀 [Upload] Starting YouTube upload (Privacy: {privacy}, Schedule: {publish_time}, Channel: {channel_id or 'Default'})")
            response = youtube_upload_service.upload_video(
                file_path=video_path, 
                title=ai_title,
                description=ai_desc, 
                tags=ai_tags,
                privacy_status=privacy, 
                publish_at=publish_time,
                token_path=token_path # Pass token path
            )
            
            # 2. Thumbnail Upload (Wait a bit for video to be indexed)
            video_id = response.get("id")
            if video_id:
                print(f"✅ [Auto-Pilot] Video uploaded: https://youtu.be/{video_id}. Waiting 10s for thumbnail upload...")
                await asyncio.sleep(10)
                
                settings = db.get_project_settings(project_id)
                thumb_url = settings.get("thumbnail_url")
                
                if thumb_url:
                    # /output/filename.jpg -> LOCAL_PATH/filename.jpg
                    fname = thumb_url.split("/")[-1]
                    thumb_path = os.path.join(config.OUTPUT_DIR, fname)
                    
                    if os.path.exists(thumb_path):
                        print(f"🖼️ [Auto-Pilot] Uploading thumbnail: {thumb_path}")
                        try:
                            youtube_upload_service.set_thumbnail(video_id, thumb_path, token_path=token_path)
                            print(f"✅ [Auto-Pilot] Thumbnail set successfully for {video_id}")
                        except Exception as te:
                            print(f"⚠️ Thumbnail upload failed: {te}")
                    else:
                        print(f"⚠️ Thumbnail file not found at {thumb_path}")
                else:
                    print(f"⚠️ No thumbnail_url found for project {project_id}")
            
            db.update_project_setting(project_id, "is_uploaded", 1)
        except Exception as e:
            print(f"❌ Upload failed: {e}")

    async def run_batch_workflow(self):
        """queued 상태의 프로젝트를 순차적으로 모두 처리"""
        if self.is_batch_running:
            print("⚠️ [Batch] 이미 진행 중인 일괄 처리 작업이 있습니다.")
            return
            
        self.is_batch_running = True
        print("🚦 [Batch] 일괄 제작 프로세스 시작...")
        import asyncio
        
        try:
            while True:
                projects = db.get_all_projects()
                # FIFO: ID가 작은 순서대로 처리
                queue = sorted([p for p in projects if p.get("status") == "queued"], key=lambda x: x['id'])
                
                if not queue:
                    print("🏁 [Batch] 대기열 작업을 모두 완료했습니다.")
                    break
                    
                project = queue[0]
                pid = project['id']
                print(f"▶️ [Batch] 프로젝트 시작: {project.get('topic')} (ID: {pid})")
                
                try:
                    # 설정 로드
                    p_settings = db.get_project_settings(pid) or {}
                    
                    # [Logic Fix] 순서대로 진행하기 위해 적절한 시작 상태 결정
                    # 1. 이미 대본이 있는 경우 -> 자산 생성부터
                    if p_settings.get("script") and len(p_settings.get("script").strip()) > 50:
                        print(f"📄 [Batch] 기존 대본 발견 (ID: {pid}). 'scripted' 단계부터 시작합니다.")
                        db.update_project(pid, status="scripted")
                    # 2. 분석 데이터는 있는 경우 -> 기획/대본 단계부터
                    elif db.get_analysis(pid):
                        print(f"📊 [Batch] 분석 데이터 발견 (ID: {pid}). 'analyzed' 단계부터 시작합니다.")
                        db.update_project(pid, status="analyzed")
                    # 3. 아무것도 없는 새 프로젝트인 경우 -> 처음(분석)부터
                    else:
                        print(f"🆕 [Batch] 신규 프로젝트 (ID: {pid}). 'created' 단계부터 시작합니다.")
                        db.update_project(pid, status="created")
                    
                    config_dict = {
                        "script_style": p_settings.get("script_style", "default"),
                        "duration_seconds": p_settings.get("duration_seconds", 300),
                        "voice_provider": p_settings.get("voice_provider"),
                        "voice_id": p_settings.get("voice_id"),
                        "image_style": p_settings.get("image_style", "realistic"), 
                        "thumbnail_style": p_settings.get("thumbnail_style", "face"), 
                        "all_video": bool(p_settings.get("all_video", 0)),
                        "motion_method": p_settings.get("motion_method", "standard"),
                        "video_scene_count": p_settings.get("video_scene_count", 0),
                        "auto_thumbnail": True,
                        "auto_plan": p_settings.get("auto_plan", True),
                        "video_engine": p_settings.get("video_engine", "wan"),
                        "upload_privacy": p_settings.get("upload_privacy", "private"),
                        "upload_schedule_at": p_settings.get("upload_schedule_at")
                    }
                    
                    # 워크플로우 실행 (Wait for completion)
                    await self.run_workflow(project.get('topic'), pid, config_dict)
                    print(f"✅ [Batch] 프로젝트 완료: {pid}")
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"❌ [Batch] 프로젝트 실패 (ID: {pid}): {e}")
                    db.update_project(pid, status="error")
                    
                await asyncio.sleep(2)
        finally:
            self.is_batch_running = False
            print("🛑 [Batch] 일괄 제작 프로세스 종료")
    
    def _alignment_to_subtitles(self, alignments: list, max_chars: int = 25) -> list:
        """
        단어 타이밍 정보를 2줄 자막으로 변환 (정밀 싱크)
        
        Args:
            alignments: [{"word": "안녕", "start": 0.0, "end": 0.3}, ...]
            max_chars: 자막당 최대 글자 수 (2줄 기준)
        
        Returns:
            [{"text": "자막 텍스트", "start": 0.0, "end": 1.5}, ...]
        """
        if not alignments:
            return []
        
        subtitles = []
        current_words = []
        current_text = ""
        block_start = None
        block_end = None
        
        for i, word_info in enumerate(alignments):
            word = word_info.get("word", "").strip()
            if not word:
                continue
            
            start = word_info.get("start", 0)
            end = word_info.get("end", start + 0.1)
            
            # 새 블록 시작
            if block_start is None:
                block_start = start
            
            # 텍스트 누적
            test_text = f"{current_text} {word}".strip() if current_text else word
            
            # 최대 글자 수 체크 또는 문장 부호로 끊기
            is_sentence_end = word.endswith(('.', '?', '!', ','))
            should_break = len(test_text) > max_chars or is_sentence_end
            
            if should_break and current_text:
                # 현재 블록 저장
                subtitles.append({
                    "text": current_text,
                    "start": round(block_start, 2),
                    "end": round(block_end, 2)
                })
                
                # 새 블록 시작
                current_text = word
                block_start = start
                block_end = end
            else:
                current_text = test_text
                block_end = end
        
        # 마지막 블록
        if current_text:
            subtitles.append({
                "text": current_text,
                "start": round(block_start, 2),
                "end": round(block_end, 2)
            })
        
        return subtitles

    def get_queue_status(self):
        """현재 대기열 상태 반환"""
        projects = db.get_all_projects()
        queued_projects = [p for p in projects if p.get("status") == "queued"]
        processing_projects = [p for p in projects if p.get("status") not in ["done", "error", "queued", "draft", "created"]]
        
        return {
            "is_running": self.is_batch_running,
            "queued_count": len(queued_projects),
            "processing_count": len(processing_projects),
            "queued_items": queued_projects[:10],  # 상위 10개만
            "current_items": processing_projects
        }

    def add_to_queue(self, project_id: int):
        """프로젝트를 대기열에 추가"""
        db.update_project(project_id, status="queued")

    def clear_queue(self):
        """대기열 비우기"""
        projects = db.get_all_projects()
        for p in projects:
            if p.get("status") == "queued":
                db.update_project(p['id'], status="draft")

    async def generate_production_plan(self, scenes: List[Dict]) -> Dict:
        """
        Gemini를 사용하여 웹툰 장면 목록을 기반으로 비디오 제작 기획서를 생성합니다.
        """
        print(f"📋 [Auto-Pilot] Generating Production Plan for {len(scenes)} scenes...")
        
        # 1. Prepare Context & Analyze Image Types (Simple Logic)
        scene_context = []
        for s in scenes:
            scene_context.append({
                "scene_number": s.get('scene_number'),
                "visual_desc": s.get('analysis', {}).get('visual_desc', ''),
                "atmosphere": s.get('analysis', {}).get('atmosphere', ''),
                "dialogue": s.get('analysis', {}).get('dialogue', ''),
                "type": s.get('scene_type', '3'), # 1: Vertical, 2: Horizontal, 3: Regular
            })
            
        prompt_template = """
        # ROLE: Hollywood Trailer Editor & VFX Supervisor
        You are creating a high-end cinematic video production plan for a webtoon.
        Follow the [USER CINEMATIC MASTER GUIDE] strictly when generating specifications for each scene.

        [INPUT DATA (JSON SCENES)]
        [[SCENES_JSON]]

        [USER CINEMATIC MASTER GUIDE (STRICT ADHERENCE)]
        0. Base Master Setting (Common for ALL cuts):
           "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, smooth camera movement, subtle parallax depth effect, soft volumetric lighting, atmospheric particles, high quality anime webtoon style, dramatic color grading, film grain subtle, slow cinematic motion, emotional pacing."

        1. Production Types (scene_type):
           - TYPE 1 (Vertical Long): "Show Space" -> slow upward/downward camera pan (pan_down, pan_up), 2.5D depth parallax, focus on full body or background reveal.
           - TYPE 2 (Horizontal Wide): "Panoramic Vista" -> SIDE PANNING (pan_left, pan_right) to show the full width of the image while fitting the height. DO NOT JUST ZOOM IN.
           - TYPE 3 (Small/Empty): "Fill Space" -> Place center, extend matching background, slow cinematic zoom (zoom_in), focal point on face.
           - TYPE 4 (Transition): "Consistency" -> Fade with particles, slow cross-dissolve, motion blur.
           - TYPE 5 (PSD Depth): "3D Illusion" -> Separate foreground/mid/background, strong parallax, 3D camera move.
           - TYPE 6 (Unified Tone): High-end animated trailer look, soft contrast, warm highlights.

        [CORE INSTRUCTIONS]
        1. **overall_strategy**: Summarize the production direction in Korean.
        2. **bgm_style**: Recommend BGM style in Korean.
        3. **scene_specifications**: For each scene, generate:
           - **scene_number**: The number from input.
           - **engine**: "wan" (motion), "akool" (lipsync), or "image" (2D). 
             * Note: If scene has dialogue, strongly consider 'akool'.
           - **effect**: "pan_down", "pan_up", "pan_left", "pan_right", "zoom_in", "zoom_out", "static".
             * Use 'pan_left' or 'pan_right' for TYPE 2 (Wide) images to show the whole image.
           - **motion**: FULL CINEMATIC PROMPT in English. Combine Master Setting (0) + Type Specific Guide (1-6) + Scene Context. Mention specific camera movement directions.
           - **rationale**: Why this choice (e.g., "Wide image detected, using Type 2 Pan Left to reveal background").
           - **cropping_advice**: How to frame to 9:16 (Fitting height and panning width) (Korean).

        [OUTPUT FORMAT (JSON ONLY)]
        {
            "overall_strategy": "Overall direction (Korean)",
            "bgm_style": "BGM (Korean)",
            "scene_specifications": [
                {
                    "scene_number": 1,
                    "engine": "wan | akool | image",
                    "effect": "zoom_in | pan_down | pan_left | ...",
                    "motion": "Detailed cinematic prompt in English focusing on camera motion",
                    "rationale": "Reason (Korean)",
                    "cropping_advice": "Advice (Korean)"
                }
            ]
        """
        
        prompt = prompt_template.replace("[[SCENES_JSON]]", json.dumps(scene_context, ensure_ascii=False))
        
        try:
            # Call Gemini
            resp = await gemini_service.generate_text(prompt)
            
            # Parse JSON
            # Clean up potential markdown blocks
            clean_json = resp.replace("```json", "").replace("```", "").strip()
            
            # Handle potential extra text
            start_idx = clean_json.find('{')
            end_idx = clean_json.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_json = clean_json[start_idx:end_idx+1]
                
            plan = json.loads(clean_json)
            return plan
        except Exception as e:
            print(f"❌ [Auto-Pilot] Plan Generation Failed: {e}")
            import traceback
            traceback.print_exc()
            # Return dummy plan
            return {
                "overall_strategy": "Plan generation failed. Please try again or proceed manually.",
                "bgm_style": "Casual",
                "scene_specifications": []
            }

    async def start_batch_worker(self):
        """[NEW] 프로젝트 대기열을 감시하고 순차적으로 처리하는 워커"""
        if self.is_batch_running:
            print("[Auto-Pilot] Batch worker already running.")
            return

        self.is_batch_running = True
        print("[Auto-Pilot] Batch worker started.")

        while True:
            try:
                # 1. 'queued' 상태인 프로젝트 찾기
                projects = db.get_all_projects()
                queued = [p for p in projects if p.get("status") == "queued"]

                if queued:
                    target = queued[0]
                    target_pid = target['id']
                    target_topic = target.get('topic', 'Auto-Webtoon')

                    log_debug(f"📦 [Auto-Pilot] Worker found queued project {target_pid} ({target_topic})...")
                    
                    # 2. 실행 상태로 전이 (run_workflow가 인식할 수 있게)
                    p_settings = db.get_project_settings(target_pid) or {}
                    
                    # 대본이 있으면 바로 에셋 생성 단계로, 없으면 처음부터
                    if p_settings.get("script") and len(p_settings.get("script").strip()) > 10:
                        log_debug(f"📜 [Auto-Pilot] Setting PID {target_pid} to 'scripted' because script exists.")
                        db.update_project(target_pid, status="scripted")
                    else:
                        log_debug(f"🆕 [Auto-Pilot] Setting PID {target_pid} to 'created'.")
                        db.update_project(target_pid, status="created")

                    # Ensure app_mode compatibility
                    if "mode" not in p_settings and "app_mode" in p_settings:
                        p_settings["mode"] = p_settings["app_mode"]

                    await self.run_workflow(target_topic, project_id=target_pid, config_dict=p_settings)
                    
                    print(f"✅ [Auto-Pilot] Project {target_pid} processing complete.")
                
                await asyncio.sleep(10) # 10초마다 확인
                
            except Exception as e:
                print(f"❌ [Auto-Pilot] Batch worker error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(20) # 에러 시 좀 더 길게 대기

autopilot_service = AutoPilotService()

