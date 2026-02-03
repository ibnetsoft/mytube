
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
        video_scene_count = config_dict.get("video_scene_count", 0)
        visual_style_key = config_dict.get("visual_style", "realistic")
        
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

        # 2. Assets (Video/Image)
        from services.replicate_service import replicate_service
        async def process_scene(p, is_video: bool):
            scene_num = p.get("scene_number")
            if p.get("image_url"): return True
            
            prompt_en = p.get("prompt_en", "cinematic scene")
            now = config.get_kst_time()
            try:
                if is_video:
                    images = await gemini_service.generate_image(prompt_en, aspect_ratio="9:16")
                    if not images: return False
                    
                    base_img_path = os.path.join(config.OUTPUT_DIR, f"temp_{project_id}_{scene_num}.png")
                    with open(base_img_path, 'wb') as f: f.write(images[0])
                    
                    video_data = await replicate_service.generate_video_from_image(base_img_path, prompt=f"Cinematic motion, {prompt_en}")
                    if video_data:
                        filename = f"vid_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.mp4"
                        out = os.path.join(config.OUTPUT_DIR, filename)
                        with open(out, 'wb') as f: f.write(video_data)
                        db.update_image_prompt_url(project_id, scene_num, f"/output/{filename}")
                        try: os.remove(base_img_path)
                        except: pass
                        return True
                
                # Image fallback or default
                images = await gemini_service.generate_image(prompt_en, aspect_ratio="9:16")
                if images:
                    filename = f"img_{project_id}_{scene_num}_{now.strftime('%H%M%S')}.png"
                    out = os.path.join(config.OUTPUT_DIR, filename)
                    with open(out, 'wb') as f: f.write(images[0])
                    db.update_image_prompt_url(project_id, scene_num, f"/output/{filename}")
                    return True
            except: pass
            return False

        # Workflow execution
        for i, p in enumerate(image_prompts):
            if i < video_scene_count: await process_scene(p, True)
            else: await process_scene(p, False)

        # 3. TTS (Universal Support)
        # Check Config -> Fallback to Global Settings -> Default
        provider = config_dict.get("voice_provider")
        voice_id = config_dict.get("voice_id")
        
        if not provider or not voice_id:
             p_settings = db.get_project_settings(1)
             if not provider: provider = p_settings.get("voice_provider", "google_cloud")
             if not voice_id: voice_id = p_settings.get("voice_id") or p_settings.get("voice_name", "ko-KR-Neural2-A")
        
        print(f"🎙️ [Auto-Pilot] Generating TTS with {provider} / {voice_id}")
        filename = f"auto_tts_{project_id}.mp3"
        
        # Use existing tts_service functions based on provider
        if provider == "elevenlabs":
            output_path = await tts_service.generate_elevenlabs(script, voice_id, filename)
        elif provider == "openai":
            output_path = await tts_service.generate_openai(script, voice_id, filename)
        elif provider == "gemini":
            output_path = await tts_service.generate_gemini(script, voice_id, filename)
        else: # Default: Google Cloud
            output_path = await tts_service.generate_google_cloud(script, voice_id, filename)
            
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(output_path)
        db.save_tts(project_id, provider, voice_id, output_path, clip.duration)
        clip.close()

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

        image_durations = tts_data["duration"] / len(images) if images else 5.0
        
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
            youtube_upload_service.upload_video(
                file_path=video_path, title=f"AI Auto Video {now.date()}",
                description="#Shorts #AI", tags=["ai", "shorts"],
                privacy_status="private", publish_at=publish_time
            )
            db.update_project_setting(project_id, "is_uploaded", 1)
        except: pass

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
