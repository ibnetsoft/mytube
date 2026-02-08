
import asyncio
import json
import os
import random
from datetime import datetime, timedelta
import httpx
from config import config
import database as db
from services.gemini_service import gemini_service
from services.prompts import prompts
from services.tts_service import tts_service
from services.video_service import video_service
from services.youtube_upload_service import youtube_upload_service


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


class AutoPilotService:
    def __init__(self):
        self.search_url = f"{config.YOUTUBE_BASE_URL}/search"
        self.config = {}  # Director Mode Configuration

    async def run_workflow(self, keyword: str, project_id: int = None, config_dict: dict = None):
        """오토파일럿 전체 워크플로우 실행"""
        print(f"🚀 [Auto-Pilot] '{keyword}' 작업 시작")
        self.config = config_dict or {}
        if "auto_plan" not in self.config:
            self.config["auto_plan"] = True  # Always generate plan data by default
        
        try:
            # 1~2. 소재 발굴 및 프로젝트 생성
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
            
            db.update_project(project_id, status="done")
            print(f"✨ [Auto-Pilot] 작업 완료! (Project ID: {project_id})")

        except Exception as e:
            print(f"❌ [Auto-Pilot] 오류 발생: {e}")
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
            "maxResults": 3, "order": "viewCount", "videoDuration": "short",
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
        image_style_key = config_dict.get("image_style", config_dict.get("visual_style", "realistic"))

        
        # Determine sequence duration based on method
        video_duration = 5.0
        if motion_method in ["extend", "slowmo"]:
            video_duration = 8.0

        # Get visual style prompt from presets
        style_presets = db.get_style_presets()
        style_data = style_presets.get(image_style_key, {})

        style_prefix = style_data.get("prompt_value", "photorealistic")
        
        # 1. Image Prompts
        # [CRITICAL FIX] Use actual target duration for image count calculation
        target_duration = config_dict.get("duration_seconds", 300)
        
        image_prompts = db.get_image_prompts(project_id)
        if not image_prompts:
            print(f"🖼️ [Auto-Pilot] Generating image prompts for {target_duration}s video...")
            # [NEW] 캐릭터 정보 조회 및 전달
            characters = db.get_project_characters(project_id)
            image_prompts = await gemini_service.generate_image_prompts_from_script(script, target_duration, style_prefix, characters=characters)
            db.save_image_prompts(project_id, image_prompts)
            image_prompts = db.get_image_prompts(project_id)
            print(f"🖼️ [Auto-Pilot] Generated {len(image_prompts)} image prompts")

        # Determine how many scenes to make as video
        if all_video:
            video_scene_count = len(image_prompts)
            print(f"🎬 [Auto-Pilot] 'ALL VIDEO' mode enabled. Generating {video_scene_count} video scenes.")
        else:
            video_scene_count = config_dict.get("video_scene_count", 0)

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
                    images = await gemini_service.generate_image(prompt_en, aspect_ratio=aspect_ratio)

                    if not images: return False
                    
                    filename = f"img_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.png"
                    image_abs_path = os.path.join(config.OUTPUT_DIR, filename)
                    with open(image_abs_path, 'wb') as f: f.write(images[0])
                    db.update_image_prompt_url(project_id, scene_num, f"/output/{filename}")
                
                if is_video:
                    try:
                        print(f"📹 [Auto-Pilot] Generating video for Scene {scene_num} (Method: {motion_method})")
                        video_data = await replicate_service.generate_video_from_image(
                            image_abs_path, 
                            prompt=f"Cinematic motion, {prompt_en}",
                            duration=video_duration,
                            method=motion_method
                        )
                        if video_data:
                            filename = f"vid_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                            out = os.path.join(config.OUTPUT_DIR, filename)
                            with open(out, 'wb') as f: f.write(video_data)
                            db.update_image_prompt_video_url(project_id, scene_num, f"/output/{filename}")
                            return True
                    except Exception as ve:
                        print(f"⚠️ [Auto-Pilot] Video generation failed for Scene {scene_num}: {ve}. Falling back to image.")
                
                return True # Image only path success
            except Exception as e:
                print(f"⚠️ [Auto-Pilot] Scene {scene_num} Asset Gen Error: {e}")
            return False

        # Workflow execution (Sequential for safety, could be parallelized)
        for i, p in enumerate(image_prompts):
            db.update_project(project_id, status=f"assets_{i+1}/{len(image_prompts)}")
            if i < video_scene_count: await process_scene(p, True)
            else: await process_scene(p, False)

        # [CRITICAL] Re-fetch image_prompts from DB to get updated video_url/image_url paths
        image_prompts = db.get_image_prompts(project_id)

        # 3. TTS (Scene-based Generation for Perfect Sync)
        db.update_project(project_id, status="generating_tts")
        # Check Config -> Fallback to Project Settings -> Default
        provider = config_dict.get("voice_provider")
        voice_id = config_dict.get("voice_id")
        
        if not provider or not voice_id:
             # Prefer current project settings over Project 1 fixed fallback
             p_settings = db.get_project_settings(project_id) or db.get_project_settings(1) or {}
             if not provider: provider = p_settings.get("voice_provider", "google_cloud")
             if not voice_id: voice_id = p_settings.get("voice_id") or p_settings.get("voice_name", "ko-KR-Neural2-A")
        
        print(f"🎙️ [Auto-Pilot] Generating Scene-based TTS with {provider} / {voice_id}")
        
        # [NEW] Scene별 오디오 및 Alignment 정보 수집
        scene_audio_files = []
        scene_durations = []
        all_alignments = []  # 전체 단어 타이밍 정보
        cumulative_audio_time = 0.0
        
        # 이미지가 생성된 Scene들만 대상으로 함 (순서 중요)
        sorted_prompts = sorted(image_prompts, key=lambda x: x.get('scene_number', 0))
        
        import uuid
        temp_audios = []
        
        for i, p in enumerate(sorted_prompts):
            db.update_project(project_id, status=f"tts_{i+1}/{len(sorted_prompts)}")
            
            text = p.get('scene_text') or p.get('narrative') or p.get('script') or ""
            if not text:
                scene_durations.append(3.0)
                cumulative_audio_time += 3.0
                continue

            scene_filename = f"temp_tts_{project_id}_{i}_{uuid.uuid4()}.mp3"
            
            try:
                # [NEW] ElevenLabs 전용: alignment 정보 포함된 결과 사용
                if provider == "elevenlabs":
                    result = await tts_service.generate_elevenlabs(text, voice_id, scene_filename)
                    
                    if result and result.get("audio_path"):
                        audio_path = result["audio_path"]
                        duration = result.get("duration", 3.0)
                        alignment = result.get("alignment", [])
                        
                        temp_audios.append(audio_path)
                        scene_audio_files.append(audio_path)
                        scene_durations.append(duration)
                        
                        # Alignment 정보에 누적 시간 offset 적용
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
                    # 다른 TTS 프로바이더 (기존 로직)
                    s_out = None
                    if provider == "openai":
                        s_out = await tts_service.generate_openai(text, voice_id, model="tts-1", filename=scene_filename)
                    elif provider == "gemini":
                        s_out = await tts_service.generate_gemini(text, voice_id, filename=scene_filename)
                    else:
                        s_out = await tts_service.generate_google_cloud(text, voice_id, filename=scene_filename)
                    
                    if s_out and os.path.exists(s_out):
                        temp_audios.append(s_out)
                        scene_audio_files.append(s_out)
                        
                        try:
                            from moviepy import AudioFileClip
                            ac = AudioFileClip(s_out)
                            dur = ac.duration
                            scene_durations.append(dur)
                            cumulative_audio_time += dur
                            ac.close()
                        except:
                            scene_durations.append(3.0)
                            cumulative_audio_time += 3.0
                    else:
                        scene_durations.append(3.0)
                        cumulative_audio_time += 3.0

            except Exception as e:
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
        
        if scene_audio_files:
            try:
                from moviepy import concatenate_audioclips, AudioFileClip
                clips = [AudioFileClip(f) for f in scene_audio_files]
                final_clip = concatenate_audioclips(clips)
                final_clip.write_audiofile(final_audio_path, logger=None)
                
                total_duration = final_clip.duration
                final_clip.close()
                for c in clips: c.close()
                
                # DB Save
                db.save_tts(project_id, provider, voice_id, final_audio_path, total_duration)
                
                # [CRITICAL] Calculate Cumulative Start Times for Frontend
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
                    auto_subtitles = self._alignment_to_subtitles(all_alignments, max_chars=40)
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

                # 3. Save Timeline Images (Order mapping)
                timeline_images = [p.get('video_url') or p.get('image_url') for p in sorted_prompts]
                # Filter out None/Empty
                timeline_images = [img for img in timeline_images if img]
                
                tl_images_path = os.path.join(config.OUTPUT_DIR, f"timeline_images_{project_id}.json")
                with open(tl_images_path, "w", encoding="utf-8") as f:
                    json.dump(timeline_images, f, ensure_ascii=False, indent=2)
                db.update_project_setting(project_id, "timeline_images_path", tl_images_path)
                
                print(f"✅ [Auto-Pilot] Scene-based TTS & Subtitles Complete. Total: {total_duration:.2f}s, Scenes: {len(scene_durations)}")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Audio Merge Failed: {e}")
                # Fallback to single file gen logic if merge fails?
        else:
             print("❌ No audio generated.")
        
        # Cleanup temps
        for f in temp_audios:
            try: os.remove(f)
            except: pass

    async def _generate_thumbnail(self, project_id: int, script: str, config_dict: dict):
        """대본 기반 썸네일 자동 기획 및 생성"""
        print(f"🎨 [Auto-Pilot] 썸네일 자동 생성 중... Project: {project_id}")
        
        # 1. 썸네일 기획 (Hook & Prompt)
        try:
            prompt = prompts.THUMBNAIL_IDEA_PROMPT.format(
                topic="Auto Generated Video", 
                script_summary=script[:1000]
            )
            # request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
            result_text = await gemini_service.generate_text(prompt, temperature=0.8)
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                plan = json.loads(json_match.group())
                hook_text = plan.get("hook_text", "충격적인 진실")
                image_prompt = plan.get("image_prompt", "A mysterious dark atmosphere, high quality")
            else:
                hook_text = "Must Watch"
                image_prompt = "Abstract background, 4k"
        except Exception as e:
            print(f"⚠️ 썸네일 기획 실패: {e}")
            hook_text = "Must Watch"
            image_prompt = "Abstract background, 4k"

        # 2. 배경 이미지 생성
        try:
            # [NEW] Art Style & Layout Inheritance
            image_style_key = config_dict.get("image_style", "realistic")
            style_presets = db.get_style_presets()
            style_data = style_presets.get(image_style_key, {})
            style_prefix = style_data.get("prompt_value", "photorealistic")

            # [NEW] Layout Style
            thumbnail_style_key = config_dict.get("thumbnail_style", "face")
            thumb_presets = db.get_thumbnail_style_presets()
            thumb_preset = thumb_presets.get(thumbnail_style_key, {})
            layout_desc = thumb_preset.get("prompt", "")
            
            # Combine everything for a consistent look
            final_thumb_prompt = f"ABSOLUTELY NO TEXT. Style: {style_prefix}. Composition: {layout_desc}. Subjects: {image_prompt}. 8k, high quality."

            # [CRITICAL] Determine aspect ratio based on duration (Long-form vs Shorts)
            duration_sec = config_dict.get("duration_seconds", 300)
            aspect_ratio = "16:9" if duration_sec > 60 else "9:16"
            
            images = await gemini_service.generate_image(final_thumb_prompt, aspect_ratio=aspect_ratio)
            if not images: return

            now = config.get_kst_time()
            bg_filename = f"thumb_bg_{project_id}_{now.strftime('%H%M%S')}.png"
            bg_path = os.path.join(config.OUTPUT_DIR, bg_filename)
            with open(bg_path, 'wb') as f: f.write(images[0])
            
            # 3. 텍스트 합성 (저장된 설정 반영)
            from services.thumbnail_service import thumbnail_service
            final_filename = f"thumbnail_{project_id}_{now.strftime('%H%M%S')}.jpg"
            final_path = os.path.join(config.OUTPUT_DIR, final_filename)
            
            # [CRITICAL] Try to load 'Saved Settings' from Project 1 (Template) or Current ID
            # Assuming Project 1 is the 'Global Config Holder' usually
            saved_thumb_data = db.get_thumbnails(1) 
            # OR check if the current project *already* has data (unlikely for new AutoPilot project)
            
            text_layers = []
            
            if saved_thumb_data and saved_thumb_data.get("full_settings"):
                print(f"🎨 [Auto-Pilot] 저장된 썸네일 설정을 불러옵니다 (From Project 1)")
                # Template 적용: 저장된 레이어 그대로 가져오되, 텍스트만 Hook으로 교체
                # 가장 큰 폰트를 가진 레이어를 '메인 텍스트'로 간주하고 교체
                layers = saved_thumb_data["full_settings"].get("layers", [])
                
                # Find main text layer (biggest font size)
                main_layer_idx = 0
                max_size = 0
                for i, l in enumerate(layers):
                    fs = int(l.get("font_size", 0))
                    if fs > max_size:
                        max_size = fs
                        main_layer_idx = i
                
                # Copy and Replace Text
                import copy
                text_layers = copy.deepcopy(layers)
                if text_layers:
                    # Replace Main Text
                    text_layers[main_layer_idx]["text"] = hook_text
                    
            else:
                # Fallback: Default Style based on config
                print(f"🎨 [Auto-Pilot] 저장된 설정 없음. 기본 스타일(Mystery) 적용")
                text_layers = [{
                    "text": hook_text,
                    "x": 640, "y": 600, 
                    "font_size": 100,
                    "color": "#00FF00", 
                    "stroke_color": "#000000",
                    "stroke_width": 8,
                    "font_family": "mystery" 
                }]

            success = thumbnail_service.create_thumbnail(bg_path, text_layers, final_path)
            
            if success:
                web_path = f"/output/{final_filename}"
                db.update_project_setting(project_id, "thumbnail_url", web_path)
                print(f"✅ [Auto-Pilot] 썸네일 생성 완료: {web_path}")
            
            try: os.remove(bg_path)
            except: pass
            
        except Exception as e:
            print(f"❌ 썸네일 생성 오류: {e}")

    async def _render_video(self, project_id: int):
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        settings = db.get_project_settings(project_id) or {}
        
        # 1. Load Subtitles (Prefer Saved)
        subs = []
        subtitle_path = settings.get("subtitle_path")
        if subtitle_path and os.path.exists(subtitle_path):
            try:
                with open(subtitle_path, "r", encoding="utf-8") as f:
                    subs = json.load(f)
            except: pass
            
        if not subs:
            print("🔍 [Auto-Pilot] No saved subtitles found. Generating via Whisper...")
            audio_path = tts_data["audio_path"]
            subs = video_service.generate_aligned_subtitles(audio_path, script_data["full_script"])
        
        if not subs: 
            subs = video_service.generate_smart_subtitles(script_data["full_script"], tts_data["duration"])

        # 2. Load Timeline Images
        images = []
        timeline_path = settings.get("timeline_images_path")
        if timeline_path and os.path.exists(timeline_path):
            try:
                with open(timeline_path, "r", encoding="utf-8") as f:
                    tl_urls = json.load(f)
                for url in tl_urls:
                    if not url: continue
                    fpath = os.path.join(config.OUTPUT_DIR, url.split("/")[-1])
                    if os.path.exists(fpath): images.append(fpath)
            except: pass
            
        if not images:
            # Fallback to image prompts
            for img in images_data:
                best_url = img.get("video_url") or img.get("image_url")
                if not best_url: continue
                fpath = os.path.join(config.OUTPUT_DIR, best_url.split("/")[-1])
                if os.path.exists(fpath): images.append(fpath)
                
        audio_path = tts_data["audio_path"]
        output_filename = f"autopilot_{project_id}_{config.get_kst_time().strftime('%H%M%S')}.mp4"

        # [IMPROVED] Calculate Durations from Start Timings
        image_durations = 5.0 # Default fallback
        timings_path = settings.get("image_timings_path")
        
        smart_sync_enabled = False
        if timings_path and os.path.exists(timings_path):
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
            image_durations = tts_data["duration"] / len(images) if images else 5.0
            print(f"⚠️ [Auto-Pilot] Fallback to N-Division Sync ({image_durations if not isinstance(image_durations, list) else 'list'}s per image)")
        
        # [NEW] Determine Resolution based on App Mode
        app_mode = settings.get("app_mode", "longform")
        resolution = (1920, 1080) if app_mode == "longform" else (1080, 1920)
        print(f"🎬 [Auto-Pilot] Rendering video with resolution: {resolution} (Mode: {app_mode})")

        final_path = video_service.create_slideshow(
            images=images, audio_path=audio_path, output_filename=output_filename,
            duration_per_image=image_durations, subtitles=subs, project_id=project_id,
            resolution=resolution
        )

        db.update_project_setting(project_id, "video_path", f"/output/{output_filename}")
        db.update_project(project_id, status="rendered")

    async def _upload_video(self, project_id: int, video_path: str):
        now = config.get_kst_time()
        publish_time = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0).isoformat()
        
        # Load generated metadata
        settings = db.get_project_settings(project_id)
        ai_title = settings.get("title") or f"AI Auto Video {now.date()}"
        ai_desc = settings.get("description") or "#Shorts #AI"
        ai_tags_str = settings.get("hashtags") or "ai,shorts"
        ai_tags = [t.strip() for t in ai_tags_str.split(",") if t.strip()]

        try:
            # 1. Video Upload (Schedule for next day 8 AM)
            response = youtube_upload_service.upload_video(
                file_path=video_path, 
                title=ai_title,
                description=ai_desc, 
                tags=ai_tags,
                privacy_status="private", 
                publish_at=publish_time
            )
            
            # 2. Thumbnail Upload
            video_id = response.get("id")
            settings = db.get_project_settings(project_id)
            thumb_url = settings.get("thumbnail_url")
            
            if video_id and thumb_url:
                # /output/filename.jpg -> LOCAL_PATH/filename.jpg
                fname = thumb_url.split("/")[-1]
                thumb_path = os.path.join(config.OUTPUT_DIR, fname)
                
                if os.path.exists(thumb_path):
                    print(f"🖼️ [Auto-Pilot] Uploading thumbnail: {thumb_path}")
                    try:
                        youtube_upload_service.set_thumbnail(video_id, thumb_path)
                    except Exception as te:
                        print(f"⚠️ Thumbnail upload failed: {te}")

            db.update_project_setting(project_id, "is_uploaded", 1)
        except Exception as e:
            print(f"❌ Upload failed: {e}")

    async def run_batch_workflow(self):
        """queued 상태의 프로젝트를 순차적으로 모두 처리"""
        print("🚦 [Batch] 일괄 제작 프로세스 시작...")
        import asyncio
        
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

                # [MODIFIED] Check if script already exists to decide start status
                # This enables "Queue after script generation"
                if p_settings.get("script") and len(p_settings.get("script").strip()) > 50:
                    print(f"📄 [Batch] 기존 대본 발견 (ID: {pid}). 'scripted' 단계부터 시작합니다.")
                    db.update_project(pid, status="scripted")
                else:
                    db.update_project(pid, status="analyzed")
                
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
                    "auto_plan": p_settings.get("auto_plan", True)
                }
                
                # 워크플로우 실행 (Wait for completion)
                await self.run_workflow(project.get('topic'), pid, config_dict)
                print(f"✅ [Batch] 프로젝트 완료: {pid}")
                
            except Exception as e:
                print(f"❌ [Batch] 프로젝트 실패 (ID: {pid}): {e}")
                db.update_project(pid, status="error")
                
            await asyncio.sleep(2)
    
    def _alignment_to_subtitles(self, alignments: list, max_chars: int = 40) -> list:
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

autopilot_service = AutoPilotService()
