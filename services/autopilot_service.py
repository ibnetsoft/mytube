
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

class AutoPilotService:
    def __init__(self):
        self.search_url = f"{config.YOUTUBE_BASE_URL}/search"
        self.config = {}  # Director Mode Configuration

    async def run_workflow(self, keyword: str, project_id: int = None, config_dict: dict = None):
        """오토파일럿 전체 워크플로우 실행"""
        print(f"🚀 [Auto-Pilot] '{keyword}' 작업 시작")
        self.config = config_dict or {}
        
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
            if current_status == "created":
                video = await self._find_best_material(keyword)
                analysis_result = await self._analyze_video(video['id']['videoId'])
                db.save_analysis(project_id, video, analysis_result)
                db.update_project(project_id, status="analyzed")
                current_status = "analyzed"

            # 4. 기획 및 대본 작성
            if current_status == "analyzed":
                analysis = db.get_analysis(project_id)
                script = await self._generate_script(project_id, analysis.get("analysis_result", {}), self.config)
                db.update_project_setting(project_id, "script", script)
                db.update_project(project_id, status="scripted")
                current_status = "scripted"

            # 5. 에셋 생성 (이미지 & 썸네일 & 오디오)
            if current_status == "scripted":
                script_data = db.get_script(project_id)
                full_script = script_data["full_script"]
                
                # 5-1. 영상 소스 생성
                await self._generate_assets(project_id, full_script, self.config)
                
                # 5-2. [NEW] 썸네일 자동 생성
                # 오토파일럿 컨피그에 'auto_thumbnail': True가 있거나 기본 활성화
                if self.config.get('auto_thumbnail', True):
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

    async def _analyze_video(self, video_id: str):
        prompt = prompts.AUTOPILOT_ANALYZE_VIDEO.format(video_id=video_id)
        request = type('obj', (object,), {"prompt": prompt, "temperature": 0.7})
        result = await gemini_service.generate_content(request)
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result["text"])
            return json.loads(json_match.group()) if json_match else {"summary": result["text"]}
        except: return {"summary": result["text"]}

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
                 struct_prompt = f"""
Create a structured plan for a YouTube video based on this analysis.
Analysis: {json.dumps(analysis, ensure_ascii=False)}

Context:
- Video Topic: {db.get_project(project_id).get('topic')}
- Script Style: {style_desc}

Required Format (JSON Only):
{{
  "hook": "Strong opening sentence to grab attention",
  "sections": [
    {{ "title": "Section Title", "key_points": ["point1", "point2"] }}
  ],
  "cta": "Conclusion and call to action"
}}
Language: Korean
"""
                 request_s = type('obj', (object,), {"prompt": struct_prompt, "temperature": 0.7})
                 result_s = await gemini_service.generate_content(request_s)
                 
                 import re
                 match = re.search(r'\{[\s\S]*\}', result_s["text"])
                 if match:
                     new_struct = json.loads(match.group())
                     db.save_script_structure(project_id, new_struct)
                     manual_plan = {"structure": new_struct} # Update local var to trigger next block
                     print(f"✅ [Auto-Pilot] 자동 기획 완료 및 저장.")
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

Instructions:
1. You MUST follow the 'User Plan' structure (Hook, Body, Conclusion, etc).
2. The 'structure' contains specific Hooks and plot points selected by the user. Do NOT change them.
3. Use the 'Reference Analysis' only to enrich the content details.
4. Output the full script in Korean.
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

        request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
        result = await gemini_service.generate_content(request)
        script = result["text"]
        
        # Save script
        # Calculate approximate duration (char count / 15 chars per sec is rough, usually 5 chars/sec for speech)
        # Using a safer estimate provided by user input usually, but here auto-calc
        target_duration_sec = config_dict.get("duration_seconds", 300) 
        db.save_script(project_id, script, len(script), target_duration_sec)
        
        return script

    async def _generate_assets(self, project_id: int, script: str, config_dict: dict):
        all_video = config_dict.get("all_video", False)
        motion_method = config_dict.get("motion_method", "standard")
        visual_style_key = config_dict.get("visual_style", "realistic")
        
        # Determine sequence duration based on method
        video_duration = 5.0
        if motion_method in ["extend", "slowmo"]:
            video_duration = 8.0

        # Get visual style prompt from presets
        style_presets = db.get_style_presets()
        style_data = style_presets.get(visual_style_key, {})
        style_prefix = style_data.get("prompt_value", "photorealistic")
        
        # 1. Image Prompts
        image_prompts = db.get_image_prompts(project_id)
        if not image_prompts:
            image_prompts = await gemini_service.generate_image_prompts_from_script(script, 50, style_prefix)
            db.save_image_prompts(project_id, image_prompts)
            image_prompts = db.get_image_prompts(project_id)

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
                    images = await gemini_service.generate_image(prompt_en, aspect_ratio="9:16")
                    if not images: return False
                    
                    filename = f"img_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.png"
                    image_abs_path = os.path.join(config.OUTPUT_DIR, filename)
                    with open(image_abs_path, 'wb') as f: f.write(images[0])
                    db.update_image_prompt_url(project_id, scene_num, f"/output/{filename}")
                
                if is_video:
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
                
                return True # Image only path success
            except Exception as e:
                print(f"⚠️ [Auto-Pilot] Scene {scene_num} Asset Gen Error: {e}")
            return False

        # Workflow execution (Sequential for safety, could be parallelized)
        for i, p in enumerate(image_prompts):
            if i < video_scene_count: await process_scene(p, True)
            else: await process_scene(p, False)

        # 3. TTS (Scene-based Generation for Perfect Sync)
        # Check Config -> Fallback to Global Settings -> Default
        provider = config_dict.get("voice_provider")
        voice_id = config_dict.get("voice_id")
        
        if not provider or not voice_id:
             p_settings = db.get_project_settings(1)
             if not provider: provider = p_settings.get("voice_provider", "google_cloud")
             if not voice_id: voice_id = p_settings.get("voice_id") or p_settings.get("voice_name", "ko-KR-Neural2-A")
        
        print(f"🎙️ [Auto-Pilot] Generating Scene-based TTS with {provider} / {voice_id}")
        
        # [NEW] Scene별 오디오 생성 및 병합
        scene_audio_files = []
        scene_durations = []
        
        # 이미지가 생성된 Scene들만 대상으로 함 (순서 중요)
        # image_prompts는 이미 DB에서 로드됨
        # 정렬 보장
        sorted_prompts = sorted(image_prompts, key=lambda x: x.get('scene_number', 0))
        
        import uuid
        temp_audios = [] # cleanup list
        
        for i, p in enumerate(sorted_prompts):
            # Scene Text 추출 (narrative or scene_text or script)
            text = p.get('scene_text') or p.get('narrative') or p.get('script') or ""
            if not text:
                # 텍스트 없는 씬 (이미지만 존재) -> 기본 3초 침묵? 아니면 그냥 스킵?
                # 시각적인 연출을 위해 2~3초 할당하고 오디오는 무음 처리하는 것이 자연스러움.
                # 하지만 구현 복잡도를 낮추기 위해, 아주 짧은 무음(0.1초) 추가하거나 이전 오디오를 연장.
                # 여기서는 텍스트가 없으면 오디오 생성 스킵하고 duration을 3.0초(Default)로 설정하여
                # 나중에 영상 생성 시 '오디오 없는 구간'으로 처리하기엔 video_service가 복잡해짐.
                # 심플하게: "..." 같은 무음 텍스트로 생성 시도하거나 Skip.
                scene_durations.append(3.0) 
                continue

            scene_filename = f"temp_tts_{project_id}_{i}_{uuid.uuid4()}.mp3"
            
            try:
                # Call TTS Service per scene
                s_out = None
                if provider == "elevenlabs":
                    s_out = await tts_service.generate_elevenlabs(text, voice_id, scene_filename)
                elif provider == "openai":
                    s_out = await tts_service.generate_openai(text, voice_id, model="tts-1", filename=scene_filename)
                elif provider == "gemini":
                    s_out = await tts_service.generate_gemini(text, voice_id, filename=scene_filename)
                else:
                    s_out = await tts_service.generate_google_cloud(text, voice_id, filename=scene_filename)
                
                if s_out and os.path.exists(s_out):
                    temp_audios.append(s_out)
                    scene_audio_files.append(s_out)
                    
                    # Measure Duration
                    from moviepy.editor import AudioFileClip
                    try:
                        ac = AudioFileClip(s_out)
                        dur = ac.duration
                        scene_durations.append(dur)
                        ac.close()
                    except:
                        scene_durations.append(3.0) # Fallback
                else:
                    print(f"⚠️ Scene {i} TTS Gen Failed. Using default duration.")
                    scene_durations.append(3.0)

            except Exception as e:
                print(f"⚠️ Scene {i} TTS Error: {e}")
                scene_durations.append(3.0)
        
        # Merge Audios
        final_filename = f"auto_tts_{project_id}.mp3"
        final_audio_path = os.path.join(config.OUTPUT_DIR, final_filename)
        
        if scene_audio_files:
            try:
                from moviepy.editor import concatenate_audioclips, AudioFileClip
                clips = [AudioFileClip(f) for f in scene_audio_files]
                final_clip = concatenate_audioclips(clips)
                final_clip.write_audiofile(final_audio_path, logger=None)
                
                total_duration = final_clip.duration
                final_clip.close()
                for c in clips: c.close()
                
                # DB Save
                db.save_tts(project_id, provider, voice_id, final_audio_path, total_duration)
                
                # [CRITICAL] Save Scene Timings !
                # We need to pass this to render_video.
                # Save as project setting 'image_timings_path' json
                timings_path = os.path.join(config.OUTPUT_DIR, f"image_timings_{project_id}.json")
                with open(timings_path, "w", encoding="utf-8") as f:
                     json.dump(scene_durations, f)
                db.update_project_setting(project_id, "image_timings_path", timings_path)
                
                print(f"✅ [Auto-Pilot] Scene-based TTS Complete. Total: {total_duration:.2f}s, Scenes: {len(scene_durations)}")
                
            except Exception as e:
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
            request = type('obj', (object,), {"prompt": prompt, "temperature": 0.8})
            result = await gemini_service.generate_content(request)
            import re
            json_match = re.search(r'\{[\s\S]*\}', result["text"])
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
            images = await gemini_service.generate_image(image_prompt, aspect_ratio="16:9")
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
            saved_thumb_data = db.get_thumbnail_data(1) 
            # OR check if the current project *already* has data (unlikely for new AutoPilot project)
            
            text_layers = []
            
            if saved_thumb_data and "layers" in saved_thumb_data:
                print(f"🎨 [Auto-Pilot] 저장된 썸네일 설정을 불러옵니다 (From Project 1)")
                # Template 적용: 저장된 레이어 그대로 가져오되, 텍스트만 Hook으로 교체
                # 가장 큰 폰트를 가진 레이어를 '메인 텍스트'로 간주하고 교체
                layers = saved_thumb_data["layers"]
                
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
                db.update_project_setting(project_id, "thumbnail_path", web_path)
                print(f"✅ [Auto-Pilot] 썸네일 생성 완료: {web_path}")
            
            try: os.remove(bg_path)
            except: pass
            
        except Exception as e:
            print(f"❌ 썸네일 생성 오류: {e}")

    async def _render_video(self, project_id: int):
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        
        images = []
        for img in images_data:
            if not img.get("image_url"): continue
            fpath = os.path.join(config.OUTPUT_DIR, img["image_url"].split("/")[-1])
            if os.path.exists(fpath): images.append(fpath)
                
        audio_path = tts_data["audio_path"]
        output_filename = f"autopilot_{project_id}_{config.get_kst_time().strftime('%H%M%S')}.mp4"

        subs = video_service.generate_aligned_subtitles(audio_path, script_data["full_script"])
        if not subs: subs = video_service.generate_simple_subtitles(script_data["full_script"], tts_data["duration"])

        # [IMPROVED] Smart Duration Calculation
        image_durations = 5.0 # Default fallback
        
        # 1. Try to load saved scene timings (from Scene-based TTS)
        settings = db.get_project_settings(project_id)
        timings_path = settings.get("image_timings_path")
        
        smart_sync_enabled = False
        if timings_path and os.path.exists(timings_path):
            try:
                with open(timings_path, "r", encoding="utf-8") as f:
                    loaded_durations = json.load(f)
                    
                # Durations count vs Images count check
                # Note: images list might be filtered (only URLs). loaded_durations count follows prompt count.
                # If they diff significantly, fallback or truncated.
                if loaded_durations:
                    # If we have more durations than images, slice it
                    if len(loaded_durations) >= len(images):
                        image_durations = loaded_durations[:len(images)]
                    else:
                        # Less durations? Pad with average or last
                        # Or just use mixed list. create_slideshow handles list.
                        # Extend with remainder average
                        rem_dur = tts_data["duration"] - sum(loaded_durations)
                        rem_cnt = len(images) - len(loaded_durations)
                        if rem_cnt > 0:
                            avg = max(3.0, rem_dur / rem_cnt)
                            image_durations = loaded_durations + [avg] * rem_cnt
                        else:
                            image_durations = loaded_durations
                            
                    print(f"✅ [Auto-Pilot] Smart Sync Applied: {len(image_durations)} scenes")
                    smart_sync_enabled = True
            except Exception as e:
                print(f"⚠️ Failed to load smart timings: {e}")

        # 2. Fallback to Simple N-Division
        if not smart_sync_enabled:
            image_durations = tts_data["duration"] / len(images) if images else 5.0
            print(f"⚠️ [Auto-Pilot] Fallback to N-Division Sync ({image_durations:.2f}s per image)")
        
        final_path = video_service.create_slideshow(
            images=images, audio_path=audio_path, output_filename=output_filename,
            duration_per_image=image_durations, subtitles=subs, project_id=project_id
        )
        db.update_project_setting(project_id, "video_path", f"/output/{output_filename}")
        db.update_project(project_id, status="rendered")

    async def _upload_video(self, project_id: int, video_path: str):
        now = config.get_kst_time()
        publish_time = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0).isoformat()
        try:
            # 1. Video Upload (Schedule for next day 8 AM)
            response = youtube_upload_service.upload_video(
                file_path=video_path, title=f"AI Auto Video {now.date()}",
                description="#Shorts #AI", tags=["ai", "shorts"],
                privacy_status="private", publish_at=publish_time
            )
            
            # 2. Thumbnail Upload
            video_id = response.get("id")
            settings = db.get_project_settings(project_id)
            thumb_url = settings.get("thumbnail_path")
            
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
                # 상태 변경: analyzed (오토파일럿이 이어서 작업할 수 있도록)
                db.update_project(pid, status="analyzed")
                
                # 설정 로드
                p_settings = db.get_project_settings(pid) or {}
                config_dict = {
                    "script_style": p_settings.get("script_style", "default"),
                    "duration_seconds": p_settings.get("duration_seconds", 300),
                    "voice_provider": p_settings.get("voice_provider"),
                    "voice_id": p_settings.get("voice_id"),
                    "visual_style": "realistic", 
                    "thumbnail_style": "face", 
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

autopilot_service = AutoPilotService()
