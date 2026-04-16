"""
Gemini API 서비스
- 텍스트 생성 (gemini-3.1-flash)
- 이미지 생성 (gemini-3.1-flash-image-preview / 나노바나나 2.0)
- 영상 생성 (Veo)
"""
import httpx
from typing import Optional, List
import base64
import os
import json
import re
import time as _time
import database as db

import google.generativeai as genai
from config import config
from services.prompts import prompts

from google import genai
from google.genai import types


class GeminiService:
    def __init__(self):
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._client = None
        self._client_key = None

    @property
    def client(self):
        """키가 바뀌면 자동으로 재생성 (Supabase 원격 키 로드 후 반영)"""
        current_key = config.GEMINI_API_KEY
        if self._client is None or self._client_key != current_key:
            if current_key:
                self._client = genai.Client(api_key=current_key)
                self._client_key = current_key
        return self._client

    @property
    def api_key(self):
        return config.GEMINI_API_KEY

    def log_debug(self, msg: str):
        """Write to debug.log for monitoring"""
        print(msg)
        try:
            from datetime import datetime
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] [Gemini] {msg}\n")
        except Exception:
            pass

    async def generate_text(self, prompt: str, temperature: float = 0.7, max_tokens: int = 8192, project_id: int = None, task_type: str = "text_gen") -> str:
        """텍스트 생성"""
        if not self.api_key:
            raise Exception("Gemini API 키가 설정되지 않았습니다. 어드민 웹에서 키를 저장한 후 앱을 재시작하세요.")
        url = f"{self.base_url}/models/gemini-3.1-flash:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        start_time = _time.time()
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(url, json=payload)
                result = response.json()

                if "candidates" in result:
                    candidate = result["candidates"][0]
                    finish_reason = candidate.get("finishReason", "")
                    text = candidate["content"]["parts"][0]["text"]
                    usage = result.get("usageMetadata", {})
                    in_tokens = usage.get('promptTokenCount', 0)
                    out_tokens = usage.get('candidatesTokenCount', 0)
                    elapsed = _time.time() - start_time
                    
                    print(f"[Gemini] finishReason={finish_reason}, outputTokens={out_tokens}, inputTokens={in_tokens}, elapsed={elapsed:.1f}s")
                    
                    # Always log, even if project_id is None
                    db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'success', 
                                 prompt_summary=prompt[:100], input_tokens=in_tokens, output_tokens=out_tokens, elapsed_time=elapsed)
                    
                    if finish_reason == "MAX_TOKENS":
                        print(f"[Gemini] WARNING: Output truncated by token limit!")
                    return text
                else:
                    elapsed = _time.time() - start_time
                    error_detail = result.get('error', {})
                    error_msg = error_detail.get('message', str(result)) if isinstance(error_detail, dict) else str(result)
                    db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'failed', 
                                 prompt_summary=prompt[:100], error_msg=error_msg, elapsed_time=elapsed)
                    raise Exception(f"Gemini API 오류: {error_msg}")
        except Exception as e:
            elapsed = _time.time() - start_time
            db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'failed', 
                         prompt_summary=prompt[:100], error_msg=str(e), elapsed_time=elapsed)
            raise e

    async def generate_text_from_image(self, prompt: str, image_bytes: bytes, mime_type: str = "image/png", project_id: int = None, task_type: str = "vision_gen") -> str:
        """이미지 + 텍스트 생성 (Vision)"""
        url = f"{self.base_url}/models/gemini-3.1-flash:generateContent?key={self.api_key}"

        encoded_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": encoded_image
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 8192
            }
        }

        start_time = _time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                result = response.json()

                if "candidates" in result:
                    candidate = result["candidates"][0]
                    text = candidate["content"]["parts"][0]["text"]
                    usage = result.get("usageMetadata", {})
                    in_tokens = usage.get('promptTokenCount', 0)
                    out_tokens = usage.get('candidatesTokenCount', 0)
                    elapsed = _time.time() - start_time
                    
                    db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'success', 
                                 prompt_summary=prompt[:100], input_tokens=in_tokens, output_tokens=out_tokens, elapsed_time=elapsed)
                    return text
                else:
                    elapsed = _time.time() - start_time
                    error_msg = result.get('error', {}).get('message', str(result)) if isinstance(result.get('error'), dict) else str(result)
                    db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'failed', 
                                 prompt_summary=prompt[:100], error_msg=error_msg, elapsed_time=elapsed)
                    raise Exception(f"Gemini Vision API 오류: {error_msg}")
        except Exception as e:
            elapsed = _time.time() - start_time
            db.add_ai_log(project_id, task_type, 'gemini-3.1-flash', 'google', 'failed', 
                         prompt_summary=prompt[:100], error_msg=str(e), elapsed_time=elapsed)
            raise e

    async def analyze_webtoon_panel(self, image_path: str, context: Optional[str] = None, voice_options: Optional[str] = None, project_id: int = None) -> dict:
        """웹툰 패널 한 칸을 분석하여 대사, 캐릭터, 연출 정보 추출"""
        
        context_inst = ""
        if context:
            context_inst = f"\n{context}\n"

        prompt = f"""
        Analyze this webtoon panel image for High-End AI Video Generation (Wan 2.1).
        {context_inst}

        [CORE PRODUCTION RULES (MUST FOLLOW)]
        0. Base Master Setting (Common for all cuts):
           "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, smooth camera movement, subtle parallax depth effect, soft volumetric lighting, atmospheric particles, high quality anime webtoon style, dramatic color grading, film grain subtle, slow cinematic motion, emotional pacing."
        
        1. Cut Type Classification & Motion Guide:
           - VERTICAL LONG (Action/Chapel/Drop): Purpose "Show Space". -> Action: "Slow upward/downward camera pan, 2.5D depth parallax, foreground separation, glowing light rays."
           - HORIZONTAL WIDE (Dialogue/Close-up): Method "Outpainting extension" or "Cinema Crop". -> Action: "Focus on facial expression, slow push-in, soft rim light, cinematic depth of field."
           - SMALL/EMPTY: Method "Fill Space". -> Action: "Place center, extend matching background, slow cinematic zoom, minimal motion, elegant tone."
        
        2. Context-Specific Add-ons:
           - Battle: "embers floating, dynamic light flicker, slight camera shake."
           - Divine: "holy golden light beams, divine glow, soft bloom effect."
           - Emotion: "slow zoom-in toward eyes, soft light, subtle breathing motion."

        [TASKS]
        1. Extract Dialogue in Korean (Exclude legal/watermarks/sfx-text).
        2. Identify Character (Check context characters).
        3. Determine Cut Category (Long/Tall, Wide/Panoramic, or Small/Square). 
           - **CRITICAL**: If width is much greater than height, it is WIDE. If height is much greater than width, it is LONG.
        4. Generate **motion_desc**: 
           - MANDATORY: Include the Base Master Setting (0).
           - Combine with Category Guide (1) and Scene Add-ons (2).
           - Describe secondary animations (hair blowing, embers, etc.).
        5. Suggest SFX & BGM mood.

        Return ONLY a JSON object in this format:
        {{
            "cut_type": "Long | Wide | Small",
            "dialogue": "Korean text",
            "character": "speaker name",
            "visual_desc": "brief visual description in English",
            "motion_desc": "FULL PRODUCTION PROMPT: [Base Master Settings] + [Cut-Specific Motion Guide] + [Scene Action Details]. Make it a single, fluid cinematic prompt in English for Wan 2.1 Video AI.",
            "focal_point_y": 0.5,
            "atmosphere": "mood",
            "sound_effects": "comma separated sfx",
            "voice_recommendation": {{ "id": "voice_id", "name": "voice_name", "reason": "reason" }},
            "audio_direction": {{ "sfx_prompt": "details for sound gen", "bgm_mood": "mood", "has_sfx": true }}
        }}
        """
        


        prompt += """
        [AUDIO DIRECTION GUIDE]
        1. **sfx_prompt**: 
           - MANDATORY if there is a visible sound effect text (e.g. "WOOSH") or clear action.
           - Generate a detailed English prompt for ElevenLabs. 
           - Format: "Footsteps on gravel, slow pace" or "Heavy rain with thunder".
           - Keep it under 100 characters.
        2. **bgm_mood**: Suggest the background music mood for this scene (e.g., "Tense", "Joyful").
        3. **has_sfx**: Set to true if a specific sound effect is required.

        [VOICE RECOMMENDATION GUIDE]
        """
        
        if voice_options:
            prompt += f"""
            - Select the best voice from this list:
            {voice_options}
            """
        else:
            prompt += """
            - Suggest a generic voice type (e.g. "Deep Male", "Soft Female", "Child").
            - Return "id": "unknown", "name": "Generic Description".
            """

        prompt += """
        [CRITICAL RULES]
        - **NEVER** return actual `null` or empty strings for required fields in JSON structure.
        - **sfx_prompt**: Provide a sound description if there is action. If silent, return "Silence".
        - **bgm_mood**: Suggest a mood if the scene has a clear atmosphere. If neutral or static, return "Silence".
        - If unsure, provide a best guess based on the visual context.
        
        RETURN JSON ONLY.
        """
        
        try:
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            
            # [FIX] 확장자에 따라 mime_type 자동 감지 (PNG를 JPEG로 잘못 보내면 API 오류 발생)
            ext = os.path.splitext(image_path)[1].lower()
            mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
            mime_type = mime_map.get(ext, 'image/jpeg')
            print(f"🔍 [Gemini] Analyzing panel: {os.path.basename(image_path)} (mime: {mime_type})")
            
            response_text = await self.generate_text_from_image(prompt, img_bytes, mime_type=mime_type, project_id=project_id, task_type='vision_analysis')
            print(f"DEBUG: Gemini RAW response for panel: {response_text[:400]}...")

            print(f"DEBUG: Gemini RAW response for panel: {response_text[:300]}...")

            
            # JSON 파싱
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            
            result = {}
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    print(f"JSON Decode Error in Panel Analysis. Raw: {response_text[:100]}...")
                    pass
            
            # [CRITICAL] Ensure mandatory fields exist for UI
            if "audio_direction" not in result:
                result["audio_direction"] = {"sfx_prompt": "", "bgm_mood": "", "has_sfx": False}
            if "voice_recommendation" not in result:
                result["voice_recommendation"] = {}
                
            # Basic fallbacks if completely failed
            if not result.get("visual_desc"):
                 result["visual_desc"] = response_text if not json_match else "Analysis parsing failed"
            
            return result
            
        except Exception as e:
            print(f"Panel analysis failed: {e}")
            # Ensure safe return even on crash
            return {
                "dialogue": "", 
                "character": "None", 
                "visual_desc": f"Error: {str(e)}", 
                "atmosphere": "Error",
                "audio_direction": {"sfx_prompt": "", "bgm_mood": "Error", "has_sfx": False},
                "voice_recommendation": {}
            }

    async def generate_webtoon_plan(self, scenes: List[dict], project_id: int = None) -> dict:
        """분석된 패널 정보를 바탕으로 비디오 제작을 위한 기획/기술 제안서 생성"""
        
        scenes_preview = []
        for s in scenes:
            # Handle both object and dict
            if hasattr(s, 'get'):
                sc = s
            else:
                sc = s.dict() if hasattr(s, 'dict') else vars(s)
            
            scenes_preview.append({
                "idx": sc.get("idx", 0),
                "scene_number": sc.get("scene_number"),
                "dialogue": sc.get("dialogue"),
                "visual_desc": sc.get("visual_desc"),
                "character": sc.get("character"),
                "scene_type": sc.get("scene_type", "3") # User classified type
            })
            
        scenes_json = json.dumps(scenes_preview, ensure_ascii=False)
        
        # [NEW] Load prompt from Settings
        prompt_template = db.get_global_setting("webtoon_plan_prompt", "")
        
        if not prompt_template or len(prompt_template.strip()) < 10:
            prompt_template = """
    # ROLE: Hollywood Trailer Editor & VFX Supervisor
    You are creating a high-end cinematic video production plan for a webtoon.
    Follow the [USER CINEMATIC MASTER GUIDE] strictly when generating specifications for each scene.

    [INPUT DATA (JSON SCENES)]
    [[SCENES_JSON]]

    [USER CINEMATIC MASTER GUIDE (STRICT ADHERENCE - MUST BE DYNAMIC!)]
    0. Base Master Setting (Common for ALL cuts):
       "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, DRAMATIC CAMERA MOVEMENT, smooth physics, high quality anime webtoon style. NEVER BE STATIC."

    1. Production Types (scene_type):
       - TYPE 1 (Vertical Long): "Show Space" -> Fast or slow upward/downward camera pan (pan_down, pan_up), strong parallax.
       - TYPE 2 (Horizontal Wide): "Panoramic Vista" -> ALWAYS use continuous side-panning (pan_left or pan_right) across the wide image to reveal details.
       - TYPE 3 (Small/Empty): "Fill Space" -> Zoom in continuously or push in to character.
       - TYPE 4 (Transition): "Consistency" -> Fade with particles.
       - TYPE 5 (PSD Depth): "3D Illusion" -> 3D camera move, foreground parallax.
       - TYPE 6 (Unified Tone): High contrast, dramatic animated motion.

    [CORE INSTRUCTIONS]
    1. **overall_strategy**: Summarize the production direction in Korean.
    2. **bgm_style**: Recommend BGM style in Korean.
    3. **scene_specifications**: For each scene, generate:
       - **scene_number**: The number from input.
       - **engine**: "akool" (PRIMARY - Seedance AI video), "wan" (fallback), or "image" (2D still). ALWAYS use "akool" as default.
       - **effect**: MUST NOT BE 'static'! ALWAYS pick "pan_left", "pan_right", "pan_up", "pan_down", "zoom_in", or "zoom_out". 
         * If image is wide (Type 2 or character face), strongly prefer "pan_left" or "pan_right" to explore the scene.
       - **motion**: FULL CINEMATIC PROMPT in English. 
         * MUST include explicit camera movement instructions (e.g., "Camera pans continuously from left to right", "Camera zooms in smoothly").
         * MUST include character micro-expressions (e.g., "Lips are quivering slightly", "Eyes blinking", "Hair blowing aggressively in wind").
       - **rationale**: (Korean) Why this dynamic motion is crucial.
       - **cropping_advice**: (Korean) Focus on Zoom-to-Fill 9:16 aspect ratio so there are no black letterboxes.

    [OUTPUT FORMAT (JSON ONLY)]
    {
        "overall_strategy": "Overall direction (Korean)",
        "bgm_style": "BGM (Korean)",
        "scene_specifications": [
            {
                "scene_number": 1,
                "engine": "akool",
                "effect": "pan_right | pan_left | pan_down | pan_up | zoom_in | zoom_out",
                "motion": "Detailed cinematic prompt in English focusing heavily on CAMERA PANNING and CHARACTER MOTION.",
                "motion_ko": "위 영어 프롬프트의 자연스러운 한글 번역",
                "rationale": "Reason (Korean)",
                "cropping_advice": "Advice on filling 9:16 screen tight (Korean)"
            }
        ]
    }
    
    **IMPORTANT**: For NARRATOR (내레이션), always use the voice 'Brian'. 
    Videos MUST NOT BE STATIC. Provide clear, strong camera movement keywords in the 'motion' string.
    """

        prompt = prompt_template.replace("[[SCENES_JSON]]", scenes_json)
        
        try:
            text = await self.generate_text(prompt, temperature=0.7, project_id=project_id, task_type='webtoon_plan')
            
            # JSON 파싱
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except Exception:
                    pass
            return { "overall_strategy": "Plan parsing failed", "raw": text, "scene_specifications": [] }
        except Exception as e:
            print(f"Plan Generation Error: {e}")
            return { "overall_strategy": f"Error: {str(e)}", "scene_specifications": [] }

    async def summarize_story(self, scenes: List[dict]) -> str:
        """분석된 전체 장면들을 요약하여 전체적인 상황 파악 리포트 생성"""
        try:
            summary_data = []
            for s in scenes:
                ana = s.get('analysis', {})
                summary_data.append({
                    "n": s.get('scene_number'),
                    "char": ana.get('character'),
                    "diag": ana.get('dialogue'),
                    "visual": ana.get('visual_desc')
                })
            
            prompt = f"""
            Identify and summarize the overall situation/plot of this webtoon based on the following scene analyses.
            Explain:
            1. What is happening globally?
            2. Who are the main characters and their current emotions?
            3. What is the tone/atmosphere?
            
            [INPUT DATA]
            {json.dumps(summary_data, ensure_ascii=False)}
            
            """
            
            summary = await self.generate_text(prompt, temperature=0.5)
            return summary.strip()
        except Exception as e:
            print(f"Summary Generation Error: {e}")
            return "상황 요약을 생성하지 못했습니다."

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        num_images: int = 1,
        project_id: int = None
    ) -> List[bytes]:
        """이미지 생성 (Imagen 폴백 체인: imagen-4 → imagen-3 → imagen-3-fast)"""

        # 스타일 키워드 검사
        stylistic_keywords = ["k_manhwa", "k_webtoon", "anime", "cartoon", "ghibli", "sketch", "line art", "doodle", "wimpy", "webtoon", "infographic", "black and white", "minimalist"]
        is_stylistic = any(kw in prompt.lower() for kw in stylistic_keywords)
        contains_photo = any(kw in prompt.lower() for kw in ["photo", "realistic", "8k", "cinematic"])
        is_infographic = "infographic" in prompt.lower()
        is_wimpy = any(kw in prompt.lower() for kw in ["wimpy", "stick figure", "stickman", "졸라맨", "jollaman"])
        if is_wimpy and any(kw in prompt.lower() for kw in ["webtoon", "manhwa", "k-manhwa", "k만화", "k_manhwa"]):
            is_wimpy = False
        is_jollaman = any(kw in prompt.lower() for kw in ["wimpy", "stick figure", "stickman", "졸라맨", "jollaman"])

        final_prompt = prompt
        if is_stylistic and not contains_photo:
            if is_infographic:
                final_prompt += ", professional graphic design, vector illustration, clean lines"
            else:
                final_prompt += ", flat 2D style, no photorealism, no text, no words"

        if is_wimpy:
            final_prompt = (
                "EXACTLY TWO ARMS ONLY. NO EXTRA ARMS. NO EXTRA HANDS. "
                "THE CHARACTER MUST HAVE A PAIR OF BLACK DOT EYES AND A SMALL ARC SMILE ON THE FACE. "
                + final_prompt
                + ", the character has exactly one left arm and one right arm total,"
                " no third arm no fourth arm no duplicate limbs,"
                " flat 2D vector no gradients no 3D, perfectly bald smooth round white circular head, no hair, no hairstyle,"
                " a pair of distinct black dot eyes and a simple black arc smile (MUST HAVE EYES AND MOUTH),"
                " Face must NEVER be blank or empty. pure white background, single scene"
            )
        elif is_jollaman:
            final_prompt = (
                "EXACTLY TWO ARMS ONLY. NO EXTRA ARMS. NO EXTRA HANDS. "
                + final_prompt
                + ", the character has a perfectly bald smooth round white circular head, no hair, no hairstyle,"
                " a pair of distinct black dot eyes and a simple black arc smile (MUST HAVE EYES AND MOUTH),"
                " Face must NEVER be blank or empty. strictly two arms total, no extra limbs"
            )

        if not is_stylistic and not is_wimpy and not is_jollaman:
            final_prompt += (
                ", single person, solo, exactly two arms, exactly two hands, exactly five fingers per hand, "
                "anatomically correct, perfect human anatomy, natural arm position"
            )
        else:
            # 스타일리시/카툰 모드일 때는 실사 유도 지시문 배제
            final_prompt += ", flat 2D vector illustration, strictly minimal, no shadows, no gradients, hand-drawn sketch style"


        # 나노바나나 2.0 (Gemini 3.1 Flash Image Preview) — 폴백 없음
        start_time = _time.time()
        try:
            self.log_debug(f"🎨 [Gemini Image] Trying Nano Banana 2.0 (gemini-3.1-flash-image-preview)")

            response = await self.client.aio.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=final_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    candidate_count=num_images,
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio if aspect_ratio in ["1:1", "16:9", "9:16", "3:4", "4:3"] else "16:9"
                    )
                )
            )

            elapsed = _time.time() - start_time
            images = []
            if response.candidates:
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            images.append(part.inline_data.data)

            if not images:
                raise Exception("Nano Banana 2.0 returned no image data")

            # 토킹 추정 및 기록 (이미지당 1000토큰으로 가정하거나 usage_metadata 사용)
            usage = getattr(response, 'usage_metadata', None)
            in_tokens = usage.prompt_token_count if usage else 1000
            out_tokens = (usage.candidates_token_count if usage else 2000) * len(images) # 갯수 곱하기
            
            self.log_debug(f"✅ [Gemini Image] Nano Banana 2.0 succeeded, {len(images)} image(s)")
            db.add_ai_log(project_id, 'image', 'gemini-3.1-flash-image-preview', 'google', 'success', 
                         prompt_summary=prompt[:100], elapsed_time=elapsed, 
                         input_tokens=in_tokens, output_tokens=out_tokens)
            return images

        except Exception as e:
            elapsed = _time.time() - start_time
            self.log_debug(f"❌ [Gemini Image] Nano Banana 2.0 failed: {e}")
            db.add_ai_log(None, 'image', 'gemini-3.1-flash-image-preview', 'google', 'failed', prompt_summary=prompt[:100], error_msg=str(e), elapsed_time=elapsed)
            raise Exception(f"이미지 생성 실패 (Nano Banana 2.0): {e}")

    async def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        duration_seconds: int = 5, 
        aspect_ratio: str = "16:9",
        model: str = "veo-3.1-fast-generate-preview",
        project_id: int = None,
        **kwargs
    ) -> Optional[bytes]:
        """영상 생성 (Veo) - 최신 SDK 방식 사용. 바이트 데이터를 직접 반환함."""
        # Cap duration for preview model
        if "preview" in model:
            duration_seconds = min(duration_seconds, 5)
        
        self.log_debug(f"📹 [Veo] Starting full video generation (dur={duration_seconds}s, ratio={aspect_ratio}): {prompt[:50]}...")
        
        # Veo는 현재 텍스트 기반이므로 대략적인 토큰 소모량 기록 (추후 API에서 정확히 받으면 수정)
        # 이미지 분석 없이 텍스트만 보낼 경우 500/1000 정도의 가상 토큰 부여
        db.add_ai_log(project_id, 'video', model, 'google', 'processing', prompt_summary=prompt[:100], input_tokens=500, output_tokens=1000)

        res = await self.generate_video_preview(prompt=prompt, image_path=image_path, model=model, aspect_ratio=aspect_ratio)
        if res.get("status") == "ok" and res.get("video_url"):
            # Download the video
            try:
                self.log_debug(f"📥 [Veo] Downloading video from {res['video_url']}...")
                download_url = res['video_url']
                if "generativelanguage.googleapis.com" in download_url and "key=" not in download_url:
                    sep = "&" if "?" in download_url else "?"
                    download_url += f"{sep}key={self.api_key}"
                
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    resp = await client.get(download_url)


                    if resp.status_code == 200:
                        self.log_debug(f"✅ [Veo] Download complete ({len(resp.content)} bytes)")
                        return resp.content
                    else:
                        self.log_debug(f"❌ [Veo] Download failed with status {resp.status_code}")
            except Exception as e:
                self.log_debug(f"⚠️ [Veo] Download failed: {e}")
        else:
            self.log_debug(f"❌ [Veo] Generation failed: {res.get('error')}")
        return None



    async def analyze_comments(self, comments: List[str], video_title: str, transcript: Optional[str] = None) -> dict:
        """댓글 및 대본 분석"""
        
        script_section = ""
        if transcript:
            # 토큰 제한 고려하여 앞부분 5000자만 사용
            script_preview = transcript[:5000]
            script_section = f"""
[영상 스크립트 (앞부분 발췌)]
{script_preview}
... (후략)
"""

        prompt = prompts.GEMINI_ANALYZE_COMMENTS.format(
            script_indicator=('과 스크립트' if transcript else ''),
            video_title=video_title,
            script_section=script_section,
            comments_text=chr(10).join(comments[:50])
        )

        text = await self.generate_text(prompt, temperature=0.3)

        # JSON 파싱
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "파싱 실패", "raw": text}

    async def generate_thumbnail_texts(self, topic: str, script: str, style: str, language: str = "ko") -> dict:
        """대본 및 스타일 기반 썸네일 후킹 문구 생성"""
        
        # Script truncation to avoid token limits
        safe_script = script[:3000] if script else f"Topic: {topic}"
        
        prompt = prompts.GEMINI_THUMBNAIL_HOOK_TEXT.format(
            script=safe_script,
            thumbnail_style=style,
            image_style=style, # Same for now
            target_language=language
        )

        try:
            text = await self.generate_text(prompt, temperature=0.8)
            
            # JSON Parsing
            import json
            import re
            
            # Clean Markdown
            cleaned_text = re.sub(r'```json\s*|\s*```', '', text).strip()
            
            # Try parse
            try:
                data = json.loads(cleaned_text)
                return data
            except json.JSONDecodeError:
                match = re.search(r'\{[\s\S]*\}', cleaned_text)
                if match:
                    return json.loads(match.group(0))
                else:
                    # Fallback
                    return {"texts": [], "reasoning": "JSON parse failed"}
                    
        except Exception as e:
            print(f"Thumbnail Text Gen Error: {e}")
            return {"texts": [], "reasoning": str(e)}

    async def extract_success_strategy(self, analysis_data: dict) -> List[dict]:
        """분석 결과에서 일반화된 성공 전략(Knowledge) 추출"""
        analysis_json = json.dumps(analysis_data, ensure_ascii=False)
        
        prompt = prompts.GEMINI_EXTRACT_STRATEGY.format(
            analysis_json=analysis_json
        )

        try:
            text = await self.generate_text(prompt, temperature=0.3)
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"[Gemini] Strategy extraction failed: {e}")
            
        return []

    async def generate_script_structure(self, analysis_data: dict, recent_titles: List[str] = None, target_language: str = "ko", style_prompt: str = "", accumulated_knowledge: List[dict] = None, project_id: int = None) -> dict:
        """분석 데이터를 기반으로 대본 구조 자동 생성 (내용과 전략의 분리 + 누적 지식 활용)"""
        
        # [NEW] 분석 데이터 분리 (내용 vs 전략)
        topic_keyword = analysis_data.get('topic', '주제 없음')
        success_strategy = analysis_data.get('success_analysis', {})
        script_style = analysis_data.get('script_style', 'story')


        # [NEW] 목표 길이에 따른 최소 섹션 수 계산 (Moved Up)
        duration_seconds = analysis_data.get('duration', 60)
        if isinstance(analysis_data.get('duration_category'), str):
            try:
                duration_seconds = int(re.search(r'\d+', analysis_data['duration_category']).group())
            except Exception: pass

        # [NEW] 스타일별 특화 지침 (기존 코드 유지)
        specialized_instruction = ""
        if script_style == "story":
            specialized_instruction = f"""
[EXTREMELY IMPORTANT: CREATIVE STORYTELLING]
- **CONTENT DECOUPLING**: You are NOT a summarizer. DO NOT use names (e.g., channel names like 'Dolby', guest names like 'Asra'), specific places, or the exact plot from the benchmarked video.
- **ZERO PLAGIARISM**: If you copy the benchmark video's story, you FAIL.
- **ACTUAL TASK**: Create a 100% ORIGINAL horror story based only on the keyword "{topic_keyword}".
- **HOW TO USE BENCHMARK**: Only look at the *technique*. (e.g., 'The way it built tension at 15s', 'The use of a specific psychological hook') - but use a DIFFERENT scare to do it.
"""
        else:
            specialized_instruction = f"[STYLE: INFORMATIONAL] Focus on '{topic_keyword}'."

        # [NEW] 숏폼(Shorts) 강력 제약 추가
        if duration_seconds <= 60:
            specialized_instruction += f"""
\n[CRITICAL SHORTFORM CONSTRAINT]
- This is a {duration_seconds}-second SHORTFORM video.
- **IGNORE** any minimum section requirements mentioned elsewhere.
- You MUST generate **MAXIMUM 3 SECTIONS** (e.g., Hook -> Core -> Outro).
- Keep descriptions concise and fast-paced.
"""

        # [NEW] 누적 지식 활용 지침
        knowledge_instruction = ""
        if accumulated_knowledge:
            knowledge_list = "\n".join([f"- [{k['category']}] {k['pattern']}: {k['insight']}" for k in accumulated_knowledge])
            knowledge_instruction = f"""
### 3. 누적된 성공 전략 베스트 프랙티스 (Success Knowledge DB)
아래는 과거에 성공했던 다른 영상들로부터 당신이 직접 추출하여 학습한 '성공 문법' 리스트입니다. 이번 기획에 적극 활용하세요:
{knowledge_list}
"""

        # [NEW] 언어/문화적 맥락 설정
        context_instruction = "Korean context."
        if target_language == "ja": context_instruction = "Japanese context."
        elif target_language == "en": context_instruction = "Global context."
        elif target_language == "vi": context_instruction = "Vietnamese context."
        

        
        min_sections = 4
        
        # [MODIFIED] 숏폼(60초 이하)일 경우 섹션 수 제한 (Intro, Body, Outro 최대 3개)
        if duration_seconds <= 60:
            min_sections = 3
        elif duration_seconds > 300: 
            min_sections = max(8, duration_seconds // 45)
        if duration_seconds > 1800: min_sections = max(20, duration_seconds // 60)
        if duration_seconds > 3600: min_sections = max(40, duration_seconds // 70)

        history_instruction = ""
        if recent_titles:
            history_list = "\n".join([f"- {t}" for t in recent_titles])
            history_instruction = f"Avoid repeating these topics: {history_list}"

        prompt = prompts.GEMINI_SCRIPT_STRUCTURE.format(
            topic_keyword=topic_keyword,
            user_notes=analysis_data.get('user_notes', '없음'),
            specialized_instruction=specialized_instruction,
            duration_seconds=duration_seconds,
            min_sections=min_sections,
            custom_prompt_section=f"[Custom Prompt]: {style_prompt}" if style_prompt else "",
            knowledge_instruction=knowledge_instruction,
            success_strategy_json=json.dumps(success_strategy, ensure_ascii=False),
            target_language_context=context_instruction,
            history_instruction=history_instruction
        )

        start_time = _time.time()
        try:
            text = await self.generate_text(prompt, temperature=0.5, project_id=project_id, task_type='script_gen')
            elapsed = _time.time() - start_time
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    res = json.loads(json_match.group())
                    # generate_text 내부에 이미 자동 로그 기능이 있지만, 
                    # 여기서 이미 로그를 남기고 있으므로 중복을 피하거나 보강합니다.
                    # 여기서는 상세 task_type ('script')을 위해 유지하거나 로그 호출을 수정합니다.
                    # 일단 유지하되 input/output_tokens는 generate_text에서 자동 처리되지 않도록 넘기지 않겠습니다.
                    # (generate_text에 project_id를 넘기지 않으면 자동로그 안됨)
                    return res
                except Exception:
                    pass
            db.add_ai_log(None, 'script', 'gemini-3.1-flash', 'google', 'failed', prompt_summary=topic_keyword, error_msg="JSON parse failed", elapsed_time=elapsed)
            return {"error": "구조 생성 실패", "raw": text}
        except Exception as e:
            elapsed = _time.time() - start_time
            db.add_ai_log(None, 'script', 'gemini-3.1-flash', 'google', 'failed', prompt_summary=topic_keyword, error_msg=str(e), elapsed_time=elapsed)
            print(f"Script Structure Gen Error: {e}")
            return {"error": f"구조 생성 실패: {str(e)}"}
    async def generate_nursery_rhyme_ideas(self) -> List[dict]:
        """동요 아이디어 10개 생성"""
        prompt = prompts.GEMINI_NURSERY_RHYME_IDEAS
        
        try:
            text = await self.generate_text(prompt, temperature=0.8)
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("ideas", [])
        except Exception as e:
            print(f"Nursery Ideas Gen Error: {e}")
        return []

    async def develop_nursery_song(self, title: str, summary: str) -> dict:
        """아이디어를 바탕으로 완성된 동요 가사 생성"""
        prompt = prompts.GEMINI_NURSERY_RHYME_DEVELOP.format(
            title=title,
            summary=summary
        )
        
        try:
            text = await self.generate_text(prompt, temperature=0.7)
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Nursery Song Develop Error: {e}")
        return {}

    async def generate_nursery_image_prompts(self, title: str, lyrics: str) -> List[dict]:
        """가사 기반 3D 애니메이션 스타일 이미지 프롬프트 생성"""
        prompt = prompts.GEMINI_NURSERY_RHYME_IMAGE_PROMPTS.format(
            title=title,
            lyrics=lyrics
        )
        
        try:
            text = await self.generate_text(prompt, temperature=0.7)
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("scenes", [])
        except Exception as e:
            print(f"Nursery Image Prompts Gen Error: {e}")
        return []

    async def generate_random_cooking_plan(self, count: int) -> dict:
        """랜덤 요리 조리 단계 및 영상 프롬프트 생성"""
        prompt = prompts.GEMINI_RANDOM_COOKING_PLAN.format(count=count)
        
        try:
            text = await self.generate_text(prompt, temperature=0.9) # Higher temperature for randomness
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Cooking Plan Gen Error: {e}")
        return {}

    async def generate_title_recommendations(self, keyword: str, topic: str = "", language: str = "ko") -> List[str]:
        """추천 제목 5개 생성"""
        prompt = f"""
        당신은 유튜브 콘텐츠 기획 전문가입니다.
        다음 정보를 바탕으로 클릭률(CTR)이 높은 롱폼/쇼츠 유튜브 제목 5개를 제안해주세요.

        [정보]
        - 키워드: {keyword}
        - 주제/설명: {topic}
        - 언어: {language}

        [요구사항]
        1. 5개의 제목을 생성하세요.
        2. 어그로성보다는 호기심을 유발하거나, 혜택을 명확히 하거나, 감정을 자극하는 제목을 만드세요.
        3. 50자 이내로 짧고 강렬하게.
        4. 번호 붙이지 말고 오직 JSON 배열로 반환하세요. 예: ["제목1", "제목2", ...]
        """

        try:
            response_text = await self.generate_text(prompt, temperature=0.8)
            cleaned_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            match = re.search(r'\[.*\]', cleaned_text, re.DOTALL)
            
            if match:
                titles = json.loads(match.group(0))
                return titles[:5]
            else:
                # Fallback
                return [line.strip().lstrip('-').lstrip('1.').strip() for line in cleaned_text.split('\n') if line.strip()][:5]
        except Exception as e:
            print(f"Title Gen Error: {e}")
            return []


    async def generate_blog_content(self, source_content: str, platform: str, blog_style: str, language: str = "ko", user_notes: str = "") -> dict:
        """참고 자료를 바탕으로 블로그 포스팅 생성"""
        prompt = prompts.GEMINI_GENERATE_BLOG.format(
            source_content=source_content[:15000],  # 토큰 제한 고려
            platform=platform,
            blog_style=blog_style,
            target_language=language,
            user_notes=user_notes
        )

        try:
            text = await self.generate_text(prompt, temperature=0.7)
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            return {"error": "블로그 생성 실패", "raw": text}
        except Exception as e:
            print(f"Blog Generation Error: {e}")
            return {"error": str(e)}

    async def generate_video_metadata(self, script_text: str) -> dict:
        """대본을 바탕으로 제목, 설명, 태그 생성"""
        prompt = prompts.AUTOPILOT_GENERATE_METADATA.format(script_text=script_text)
        try:
            response_text = await self.generate_text(prompt, temperature=0.7)
            
            # Clean Markdown code blocks
            cleaned_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            
            # Use regex to find JSON object
            json_match = re.search(r'\{[\s\S]*\}', cleaned_text)
            if json_match:
                return json.loads(json_match.group(0))
            
            # Fallback if parsing fails
            return {
                "title": f"New Video {config.get_kst_time().date()}",
                "description": "#AI #Shorts",
                "tags": ["ai", "shorts"]
            }
        except Exception as e:
            print(f"Metadata Gen Error: {e}")
            return {
                "title": f"Video {config.get_kst_time().date()}",
                "description": "#AI",
                "tags": ["ai"]
            }


    async def generate_trending_keywords(self, language: str = "ko", period: str = "now", age: str = "all") -> list:
        """
        언어/기간/연령별 인기 유튜브 트렌드 키워드 생성 (Search Volume 시뮬레이션)
        """
        lang_name = ""
        if language == "ko": lang_name = "South Korea (Korean)"
        elif language == "ja": lang_name = "Japan (Japanese)"
        elif language == "en": lang_name = "USA/International (English)"
        elif language == "es": lang_name = "Spain/Latin America (Spanish)"
        elif language == "vi": lang_name = "Vietnam (Vietnamese)"
        else: lang_name = "South Korea (Korean)"

        # 기간 텍스트
        period_text = "REAL-TIME / NOW"
        if period == "week": period_text = "THIS WEEK (Last 7 days)"
        elif period == "month": period_text = "THIS MONTH (Last 30 days)"

        # 연령 텍스트
        age_text = "ALL Ages"
        if age == "10s": age_text = "Teenagers (10-19)"
        elif age == "20s": age_text = "Young Adults (20-29)"
        elif age == "30s": age_text = "Adults (30-39)"
        elif age == "40s": age_text = "Middle-aged (40-49)"
        elif age == "50s": age_text = "Seniors (50+)"

        prompt = prompts.GEMINI_TRENDING_KEYWORDS.format(
            lang_name=lang_name,
            period_text=period_text,
            age_text=age_text,
            language=language
        )
        
        try:
            text = await self.generate_text(prompt, temperature=0.9)
            
            import json
            import re
            
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
            else:
                # Fallback data if parse fails
                return []
                
        except Exception as e:
            print(f"Trend keywords generation failed: {e}")
            return []

    async def generate_commerce_copywriting(self, product_info: dict) -> dict:
        """제품 정보를 바탕으로 쇼츠용 매운맛 카피라이팅 3종 생성"""
        
        prompt = f"""
        당신은 100만 조회수를 만드는 숏폼 마케팅 천재 카피라이터입니다.
        아래 제품 정보를 바탕으로 시청자를 즉시 사로잡는(Hooking) 쇼츠 대본 3가지를 작성하세요.
        
        [제품 정보]
        - 제품명: {product_info.get('product_name')}
        - 가격: {product_info.get('product_price')}
        - 특징: {product_info.get('product_description')}
        
        [요구사항]
        1. 3가지 전략으로 작성할 것:
           A. [공감/고통] "아직도 00하세요? 이거 쓰면 해결됩니다." (문제 제기 -> 해결)
           B. [결과/반전] "이거 하나 바꿨더니 00이 달라졌어요." (드라마틱한 변화 강조)
           C. [충격/가성비] "사장님이 미쳤어요? 이 가격에 이게 된다고?" (가격 대비 성능 강조)
           
        2. 각 대본은 'Hook(3초) -> Body(설명) -> CTA(행동유도)' 구조를 가질 것.
        3. 말투는 빠르고 강렬하게, 구어체 사용. (존댓말/반말 혼용 가능하나 자연스럽게)
        4. 전체 길이는 읽었을 때 30초 이내 분량.
        
        [출력 형식]
        오직 JSON 객체로 반환하세요:
        {{
            "copywriting": [
                {{
                    "type": "pain_point",
                    "title": "공감형 (문제해결)",
                    "hook": "...",
                    "body": "...",
                    "cta": "..."
                }},
                {{
                    "type": "benefit",
                    "title": "결과강조형 (비포애프터)",
                    "hook": "...",
                    "body": "...",
                    "cta": "..."
                }},
                {{
                    "type": "shock",
                    "title": "충격형 (가성비끝판왕)",
                    "hook": "...",
                    "body": "...",
                    "cta": "..."
                }}
            ]
        }}
        """
        
        try:
            text = await self.generate_text(prompt, temperature=0.8)
            import json
            import re
            
            cleaned = re.sub(r'```json\s*|\s*```', '', text).strip()
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                return json.loads(match.group(0))
            else:
                return {"copywriting": []}
                
        except Exception as e:
            print(f"Copywriting Gen Error: {e}")
            return {"copywriting": []}

    async def generate_amazon_trends(self) -> List[dict]:
        """미국 아마존 트렌드 키워드 생성"""
        from config import config
        current_date = config.get_kst_time().strftime("%Y-%m-%d")
        
        prompt = f"""
        Current Date: {current_date}
        Target Market: USA (Amazon.com)
        Role: Amazon Affiliate Marketing Expert
        
        Identify 5 high-potential, trending product keywords for Amazon Affiliate marketing right now.
        Consider seasonality (holidays, weather), viral trends (TikTok/Instagram), and new tech releases.
        
        Return ONLY a JSON array of objects:
        [
            {{
                "keyword": "search term",
                "reason": "Why it sells now (short)"
            }},
            ...
        ]
        """
        
        try:
            text = await self.generate_text(prompt, temperature=0.9)
            import json, re
            cleaned = re.sub(r'```json\s*|\s*```', '', text).strip()
            match = re.search(r'\[[\s\S]*\]', cleaned)
            if match:
                return json.loads(match.group(0))
            return []
        except Exception as e:
            print(f"Trend Gen Error: {e}")
            return []

    async def generate_character_prompts_from_script(self, script: str, visual_style: str = "photorealistic", char_ethnicity: str = None, project_id: int = None) -> List[dict]:
        """대본을 분석하여 등장인물 정보 및 이미지 프롬프트 생성 (캐릭터 설정 단계)"""
        ethnicity_instruction = ""
        if char_ethnicity:
            ethnicity_instruction = f"""
[인종/인종적 배경 지침 - 절대 준수]
- 이 영상의 모든 인물은 다음 인종/배경을 가져야 합니다: "{char_ethnicity}"
- 서양인(Caucasian) 위주가 아닌, 위 지침에 따른 신체적 특징을 가진 인물을 묘사하세요.
"""

        prompt = prompts.GEMINI_CHARACTER_PROMPTS.format(
            script=script[:8000],
            visual_style=visual_style,
            ethnicity_instruction=ethnicity_instruction
        )
        
        text = await self.generate_text(prompt, temperature=0.5, project_id=project_id, task_type='character_extraction')
        
        # JSON 파싱
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                chars = data.get("characters", [])
                
                # [ETHNICITY ENFORCEMENT]
                if char_ethnicity and chars:
                    eth_key = char_ethnicity.split(",")[0].strip().lower()
                    for char in chars:
                        pen = char.get("prompt_en", "")
                        if pen and eth_key not in pen.lower():
                            char["prompt_en"] = f"{char_ethnicity}, {pen}"
                return chars
            except Exception as e:
                print(f"Character prompt JSON parse error: {e}")
                pass
        return []

    def _sanitize_wimpy_prompt(self, prompt: str) -> str:
        """졸라맨 프롬프트에서 복잡한 팔 포즈 및 머리카락 키워드 강제 제거"""
        import re

        # 물건 들기 패턴
        holding_patterns = [
            r'holding\s+\w+', r'carrying\s+\w+', r'gripping\s+\w+', r'holds\s+\w+', r'carries\s+\w+',
            r'hold(?:ing)?\s+(?:a|an|the)\s+\w+', r'carry(?:ing)?\s+(?:a|an|the)\s+\w+',
            r'supporting\s+(?:a|an|the)\s+\w+', r'leaning\s+on\s+\w+',
        ]

        # 팔/주먹 들기 패턴 — Flux가 3번째 팔을 추가하는 원인
        raised_arm_patterns = [
            r'fist[s]?\s+(?:raised|up|pump|pump(?:ing)?|clench(?:ed)?)',
            r'raised\s+fist[s]?',
            r'(?:both\s+)?arms?\s+(?:raised|up|extended|outstretched|lifted|spread|pointing|gesturing|moving|waiving|celebrating|waving)',
            r'(?:left|right)\s+arm\s+(?:raised|up|extended|lifted|pointing|spread|moving|waiving)',
            r'punch(?:ing)?', r'flex(?:ing)?\s+(?:muscle|arm|bicep)', r'muscle[s]?\s+flex',
            r'clench(?:ed|ing)?\s+fist[s]?', r'fist[s]?\s+clench',
            r'arms?\s+wide', r'wide\s+arms?', r'outstretched\s+arms?',
            r'victory\s+pose', r'triumphant\s+pose', r'power\s+pose', r'pointing\s+at',
            r'clapping', r'hug(?:ging)?', r'shrugging', r'dancing', r'running\s+with\s+arms',
            r'throwing\s+arms', r'arms\s+in\s+the\s+air'
        ]

        # 머리카락 및 머리 장식 패턴 (뿔, 귀, 모자 등 포함)
        hair_patterns = [
            r'\w+\s+hair', r'hair\s+style', r'hair\s+color', r'hairstyle', r'black\s+hair',
            r'brown\s+hair', r'blonde\s+hair', r'with\s+hair', r'has\s+hair', r'long\s+hair',
            r'short\s+hair', r'swept-back\s+hair', r'undercut', r'fade\s+cut',
            r'head\s+with\s+black\s+shape', r'black\s+cap\s+on\s+head', r'horn[s]?',
            r'ear[s]?', r'cap[s]?', r'hat[s]?', r'headpiece', r'ribbon', r'wig',
            r'beard', r'mustache', r'sideburns', r'ponytail', r'mohawk',
        ]

        # 1. 머리카락 관련 표현 무조건 제거
        for p in hair_patterns:
            prompt = re.sub(p, '', prompt, flags=re.IGNORECASE)

        has_holding = any(re.search(p, prompt, re.IGNORECASE) for p in holding_patterns)
        has_raised = any(re.search(p, prompt, re.IGNORECASE) for p in raised_arm_patterns)

        # 2. 맹목적으로 무조건 추가할 해부학 규칙 (초강력 버전 - 괴물 방지)
        # 핵심: EXACTLY TWO ARMS 를 문장 맨 뒤에도 붙여서 강조
        anatomy_safeguard = (
            " strictly correct anatomy, ONLY TWO ARMS TOTAL (one left arm, one right arm), "
            "ONLY TWO HANDS TOTAL, no third arm, no fourth arm, no extra limbs, "
            "strictly humanoid structure with only two arms attached to torso. "
            "THE CHARACTER FACE MUST HAVE: a pair of distinct black dot eyes and a simple black arc smile (smile expression). "
            "Face must NEVER be blank or empty. Head is a perfectly bare smooth bald white sphere with NO details and NO hair. "
            "STRICTLY EXACTLY TWO ARMS ONLY, NO EXTRA APPENDAGES, NO MUTATED LIMBS."
        )

        if has_holding or has_raised:
            trigger = "holding" if has_holding else "raised-arm"
            print(f"⚠️ [Wimpy Sanitize] Detected {trigger} pose in prompt — replacing with SAFE-POSE")
            # 모든 복잡한 팔 표현 제거
            for p in holding_patterns + raised_arm_patterns:
                prompt = re.sub(p, '', prompt, flags=re.IGNORECASE)
            # 팔/손 관련 기타 표현 제거
            prompt = re.sub(r',\s*,', ',', prompt)
            prompt = re.sub(r'\s+', ' ', prompt).strip()
            # SAFE-POSE: 절대로 팔이 늘어날 수 없는 가장 안전한 자세
            safe_pose = (
                "The character stands in a neutral posture. "
                "The left arm and left hand hang naturally straight down by the left side of the body. "
                "The right arm and right hand hang naturally straight down by the right side of the body. "
                "ONLY TWO ARMS AND ONLY TWO HANDS ARE VISIBLE. "
                "The character has two black dot eyes and a small mouth on its face."
            )
            prompt = re.sub(r'\.\s*$', '', prompt.strip())
            prompt = prompt + ". " + safe_pose
        
        # 3. 문장 끝에 anatomy_safeguard 강제 삽입
        prompt = re.sub(r'\s+', ' ', prompt).strip()
        if anatomy_safeguard.strip() not in prompt:
            prompt = prompt.rstrip(" .") + ". " + anatomy_safeguard
            
        return prompt

    async def generate_motion_desc(self, scene_text: str, prompt_en: str = "", project_id: int = None) -> str:
        """씬 내용을 기반으로 영상 모션 프롬프트 생성 (300자 이내 영어, 씬 맥락 반영)"""
        visual_hint = prompt_en[:500] if prompt_en else ""
        prompt = f"""You are a cinematic video director creating a motion prompt for an AI video generator (Wan 2.1 / Seedance).
The motion prompt will animate a still illustration into a short video clip.

Scene narrative (Korean): {scene_text}

Visual scene description: {visual_hint}

Your task: Write a detailed motion prompt that:
1. Reflects the EMOTIONAL TONE and NARRATIVE of the scene (crisis, joy, tension, revelation, etc.)
2. Describes specific CAMERA MOVEMENT that matches the mood
3. Describes what the CHARACTER and BACKGROUND ELEMENTS are DOING (not just standing)
4. Creates VISUAL STORYTELLING that matches the script content

Rules:
- Output ONLY the motion prompt text. No explanation, no quotes, no labels.
- Maximum 300 characters total.
- English only.
- Include: [camera movement] + [character action] + [background/environment movement] + [atmosphere/lighting]
- Be SPECIFIC to THIS scene — avoid generic phrases like "character looks up" unless the scene calls for it.

Camera options (choose what fits the mood):
  Crisis/fall: slow push in, dramatic zoom in, slight camera shake, tilt down
  Revelation: slow zoom out, pull back reveal, gentle pan across
  Tension: static shot with subtle sway, slow creep forward, slight handheld shake
  Positive/calm: gentle pan right, slow zoom in, soft floating movement

Character action options (match the narrative):
  Shock/crisis: character stumbles back in shock, character covers mouth in disbelief, character stares wide-eyed
  Determination: character steps forward confidently, character raises fist decisively, character nods firmly
  Anxiety/worry: character paces nervously, character looks left and right frantically
  Curiosity/thinking: character tilts head and looks up thoughtfully, character strokes chin
  Explanation: character gestures expressively toward viewer, character points at background element

Background movement (add life to the scene):
  Crisis scenes: debris falls and scatters, buildings crumble slowly, smoke drifts upward
  Economic scenes: stock chart arrows animate downward/upward, coins scatter, graph bars rise/fall
  Crowd scenes: background figures shift and murmur, crowd ripples with movement
  Nature/weather: clouds drift slowly, light rays shift, shadows lengthen

Examples of GOOD detailed prompts:
- "slow push in toward character, character stumbles back in shock as building crumbles in background, debris falls from above, dramatic dark lighting with rising dust, tense atmosphere"
- "pull back reveal, character gestures at rising bar charts, background crowd of office workers celebrates, warm golden light floods from windows, optimistic energy"
- "slight camera shake, character paces nervously left and right, shadowy figures loom closer from background, cold blue tinted lighting, suspenseful atmosphere"
- "gentle pan right, character points decisively at world map, flag icons animate into position, bold graphic elements slide in from sides, bright confident lighting"

Now write the motion prompt for THIS scene:"""

        result = await self.generate_text(prompt, temperature=0.7, project_id=project_id, task_type='motion_guide')
        result = result.strip().strip('"').strip("'").splitlines()[0].strip()
        # 300자 제한 - 단어 중간에서 잘리지 않도록
        if len(result) > 300:
            cut = result[:300]
            last_sep = max(cut.rfind(','), cut.rfind(' '))
            result = cut[:last_sep].rstrip(', ') if last_sep > 100 else cut
        return result

    async def generate_motion_desc_from_image(self, image_path: str, scene_text: str = "", project_id: int = None) -> str:
        """생성된 이미지를 직접 분석하여 영상 모션 프롬프트 생성 (Gemini Vision)"""
        import os
        if not image_path or not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")

        context_hint = f"\nScene narrative (Korean): {scene_text[:300]}" if scene_text else ""

        prompt = f"""You are a cinematic video director. Analyze this illustration and create a motion prompt to animate it into a short AI video clip (Wan 2.1 / Seedance).{context_hint}

Look at the image carefully and determine:
1. What are the main subjects and their positions?
2. What is the overall mood and atmosphere?
3. What camera movement would best enhance this scene?
4. What natural motions should the characters/objects have?

Write a concise motion prompt that:
- Starts with a specific CAMERA MOVEMENT (slow zoom in, pan right, pull back, etc.)
- Describes CHARACTER ACTIONS if a character is present
- Describes BACKGROUND ELEMENT MOVEMENTS (charts animating, objects moving, lights shifting)
- Ends with ATMOSPHERE/LIGHTING description
- Maximum 300 characters total
- English only
- Output ONLY the motion prompt. No explanation, no labels, no quotes.

Examples:
- "slow zoom in toward central figure, character gestures confidently at glowing chart, bar graph rises dramatically, warm spotlight effect, energetic atmosphere"
- "gentle pan right across world map, trade route arrows animate between continents, cargo icons drift slowly, cool blue ambient lighting, serious tone"
- "static shot with subtle camera drift, character turns to face viewer with determined expression, background figures disperse, dramatic side lighting, tense atmosphere"

Motion prompt for this image:"""

        result = await self.generate_text_from_image(prompt, image_bytes, mime_type, project_id=project_id, task_type='motion_guide_vision')
        result = result.strip().strip('"').strip("'").splitlines()[0].strip()
        if len(result) > 300:
            cut = result[:300]
            last_sep = max(cut.rfind(','), cut.rfind(' '))
            result = cut[:last_sep].rstrip(', ') if last_sep > 100 else cut
        return result

    async def generate_image_prompts_from_script(self, script: str, duration_seconds: int, style_prompt: str = None, characters: List[dict] = None, target_scene_count: int = None, style_key: str = None, gemini_instruction: str = None, reference_image_url: str = None, char_ethnicity: str = None, project_id: int = None) -> List[dict]:
        """대본을 분석하여 장면별 이미지 프롬프트 생성 (가변 페이싱 및 캐릭터 일관성 적용)"""

        # target_scene_count가 전달된 경우 우선 사용 (씬 분석 결과)
        if target_scene_count and target_scene_count > 0:
            num_scenes = target_scene_count
            print(f"[Gemini] Using user-specified scene count: {num_scenes}")
        else:
            # [NEW] 6-Step Dynamic Pacing Policy
            # 1. 0 ~ 1분 (60s): 5초당 1장 (12장) - 후킹 강화
            # 2. 1 ~ 3분 (120s): 10초당 1장 (12장)
            # 3. 3 ~ 5분 (120s): 15초당 1장 (8장)
            # 4. 5 ~ 10분 (300s): 20초당 1장 (15장)
            # 5. 10 ~ 20분 (600s): 30초당 1장 (20장)
            # 6. 20분 이후: 40초당 1장
            num_scenes = 0
            if duration_seconds <= 60:
                num_scenes = duration_seconds // 5
            elif duration_seconds <= 180:
                num_scenes = 12 + (duration_seconds - 60) // 10
            elif duration_seconds <= 300:
                num_scenes = 12 + 12 + (duration_seconds - 180) // 15
            elif duration_seconds <= 600:
                num_scenes = 12 + 12 + 8 + (duration_seconds - 300) // 20
            elif duration_seconds <= 1200:
                num_scenes = 47 + (duration_seconds - 600) // 30
            else:
                num_scenes = 67 + (duration_seconds - 1200) // 40
            num_scenes = max(3, int(num_scenes))
            print(f"[Gemini] Calculated scene count (6-Step Pacing) from {duration_seconds}s: {num_scenes}")
        
        # 스타일 분류 — wimpy/졸라맨 키워드 기반
        _sk_lower = (style_key or "").lower()
        _sp_lower = (style_prompt or "").lower()
        _wimpy_kws = ["wimpy", "stick", "졸라맨", "jollaman"]
        is_wimpy_style = any(kw in _sk_lower for kw in _wimpy_kws) or any(kw in _sp_lower for kw in _wimpy_kws)
        print(f"[Gemini] style_key={style_key!r}, is_wimpy_style={is_wimpy_style}")

        # 모든 스타일에 공통 적용: 텍스트 금지 + 해부학적 정확성
        universal_prevention = """
[이미지 품질 규칙 - 모든 스타일 공통 필수 준수]
1. **NO TEXT IN IMAGE (절대 금지)**: 생성되는 이미지 안에 어떤 언어(영어/한국어/일본어 등)의 텍스트, 단어, 레이블, 자막, 워터마크, 로고, 말풍선도 절대 포함하지 마세요.
   - 해부도, 다이어그램, 차트, 포스터, 간판 등 원래 텍스트가 있는 소재를 묘사할 때도 글자 없이 시각적 요소만 묘사하세요.
   - "4k", "8k", "HD", "4K", "UHD" 등 해상도 키워드를 prompt_en에 절대 포함하지 마세요 — 이미지에 텍스트 워터마크로 나타납니다.
   - 모든 prompt_en 끝에 반드시 추가: "no text, no words, no letters, no labels, no watermarks, no captions"
2. **CRITICAL: CORRECT ANATOMY — EXACTLY TWO ARMS AND TWO HANDS (해부학적 정확성 - 절대 최우선)**:
   - 인물·캐릭터의 팔은 반드시 정확히 **2개**, 손도 반드시 정확히 **2개**, 손가락은 각 손당 **5개**입니다.
   - 팔 3개·손 3개·여분의 팔다리·떠다니는 팔·분리된 팔은 절대 금지.
   - **물건을 잡고 있는 장면에서도 동일**: 한 손으로 물건을 잡으면 나머지 한 손만 존재합니다.
   - 예: 책을 한 손으로 들고 있을 때 → 책 잡은 손 1개 + 반대쪽 손 1개 = 총 손 2개만 허용.
   - **여러 인물이 등장하는 장면**: 각 인물 당 팔 2개, 손 2개. 인물 수 × 2 = 총 팔 수.
   - 모든 prompt_en에 반드시 포함: "(exactly two arms:1.5), (exactly two hands:1.5), (five fingers per hand:1.4), (anatomically correct hands:1.4), (correct body proportions:1.3), correct anatomy, no extra limbs, no extra hands, no extra arms, no floating arms, no disconnected arms, no deformed arms, no mutated hands"
"""

        custom_instruction = ""
        if gemini_instruction and gemini_instruction.strip():
            import re as _re
            # ${VARIABLE} 템플릿 변수를 자연어 지시로 교체 (Gemini가 그대로 복사하는 버그 방지)
            _var_map = {
                r'\$\{OBJECT\}':      '[대본 속 핵심 사물/캐릭터를 영어로 구체 묘사]',
                r'\$\{EXPRESSION\}':  '[이 장면의 캐릭터 감정 표현]',
                r'\$\{ACTION\}':      '[이 장면의 구체적인 동작]',
                r'\$\{ENVIRONMENT\}': '[이 장면의 구체적인 배경 환경]',
            }
            cleaned_instruction = gemini_instruction.strip()
            for pattern, replacement in _var_map.items():
                cleaned_instruction = _re.sub(pattern, replacement, cleaned_instruction)
            custom_instruction = "\n[커스텀 지침 - 필수 준수]\n" + cleaned_instruction + "\n"

        style_instruction = f"""
[스타일 지침]
모든 이미지 프롬프트에 다음 스타일을 반드시 반영하세요:
"{style_prompt}"

모든 prompt_en의 시작 부분에 이 스타일 키워드를 포함시켜야 합니다.
예: "{style_prompt}, ..."

{universal_prevention}
{custom_instruction}
"""

        character_instruction = ""
        if characters:
            char_descriptions = "\n".join([f"- {c['name']} ({c['role']}): {c['prompt_en']}" for c in characters])
            character_instruction = f"""
[등장인물 일관성 지침 - 필수]
이 영상에는 다음 캐릭터들이 등장합니다. 장면별 prompt_en 생성 시 해당 인물이 등장한다면 아래 묘사를 참고하세요:
{char_descriptions}

[캐릭터 외형 일관성]
- 모든 씬에서 캐릭터의 외형(헤어스타일, 의상 등)을 동일하게 유지하세요.
"""

        ethnicity_instruction = ""
        if char_ethnicity:
            ethnicity_instruction = f"""
[인종/인종적 배경 지침 - 절대 준수]
- 이 영상의 모든 인물은 다음 인종/배경을 가져야 합니다: "{char_ethnicity}"
- 서양인(Caucasian) 위주로 생성되지 않도록, 위 지침에 기술된 신체적 특징(눈매, 피부톤, 골격 등)을 모든 프롬프트에 명시적으로 반영하세요.
"""

        # 장면 수 지침 생성
        if target_scene_count and target_scene_count > 0:
            # 사용자가 씬 수를 직접 지정한 경우 - 명확하게 해당 수 생성 지시
            limit_instruction = f"""
[중요: 장면 수 정책 - 반드시 준수]
- 반드시 정확히 **{num_scenes}개**의 장면을 생성해야 합니다. 더 많거나 적으면 안 됩니다.
- 아래 대본 구간 전체를 **처음부터 끝까지** {num_scenes}개로 균등하게 나누세요.
- ⚠️ 절대 금지: 어떤 구간도 건너뛰지 마세요. 도입부 전환(소개, 예고, 목차 설명, 시나리오 소개)도 반드시 씬으로 포함하세요.
- 각 씬의 scene_text: 해당 구간의 원본 대본 텍스트를 요약 없이 그대로 인용하세요 (최소 50자 이상).
- 연속된 씬들의 scene_text를 이어 붙이면 대본 전체가 순서대로 재구성되어야 합니다.
- JSON 배열에 반드시 scene_number 1번부터 {num_scenes}번까지 순서대로 포함하세요.
"""
        else:
            # 자동 계산된 경우 - 기존 페이싱 지침 사용
            limit_instruction = f"""
[중요: 영상 페이싱 정책]
사용자의 몰입도를 극대화하기 위해 다음 6단계 구간별 페이싱을 엄격히 준수하세요:
1. **황금 시간대 (0~1분)**: 5초당 1장 수준으로 매우 빠르게 화면을 전환하여 시선을 고정시키세요 (총 12장).
2. **몰입 단계 (1~3분)**: 10초당 1장 수준으로 긴장감을 유지하세요.
3. **전개 단계 (3~5분)**: 15초당 1장 수준으로 내용을 깊이 있게 전달하세요.
4. **설명 단계 (5~10분)**: 20초당 1장 수준으로 정보를 명확히 시각화하세요.
5. **안정 단계 (10~20분)**: 30초당 1장 수준으로 흐름을 이어가세요.
6. **마무리 단계 (20분 이후)**: 40초당 1장 수준으로 대미를 장식하세요.
- ⚠️ 절대 금지: 대본의 어떤 구간도 건너뛰지 마세요. 도입부 전환(소개, 예고, 목차 설명)도 반드시 씬으로 포함하세요.
- 각 씬의 scene_text: 해당 구간의 원본 대본 텍스트를 요약 없이 그대로 인용하세요 (최소 50자 이상).
- 연속된 씬들의 scene_text를 이어 붙이면 대본 전체가 순서대로 재구성되어야 합니다.
- 위 페이싱에 맞춰 총 **{num_scenes}개**의 장면을 시간 순서대로 골고루 배분하여 JSON을 생성하세요.
"""

        # ── 청크(Chunk) 분할 생성 ──────────────────────────────────────────────
        # 긴 스크립트를 단일 Gemini 호출로 처리하면 출력 토큰 한계(8192)로 인해
        # 중간 내용이 누락되거나 씬이 압축됩니다.
        # 스크립트가 길거나 씬 수가 많으면 청크로 나눠 각각 생성 후 합산합니다.
        CHUNK_CHARS = 8000    # 청크당 최대 글자 수
        # 졸라맨/커스텀 스타일은 prompt_char+prompt_bg+flow_prompt 때문에 씬당 토큰이 많으므로 더 작게
        SCENES_PER_CHUNK = 4 if (gemini_instruction and len(gemini_instruction) > 300) else 6

        # 씬 수가 많으면 스크립트 길이와 무관하게 청크 모드 사용
        use_chunked = num_scenes > SCENES_PER_CHUNK

        import json
        import re
        import math

        def _sanitize_json_strings(text: str) -> str:
            """JSON 문자열 내부의 raw 개행/탭 문자를 이스케이프 (Gemini가 자주 포함시킴)"""
            result = []
            in_string = False
            escape = False
            for ch in text:
                if escape:
                    result.append(ch)
                    escape = False
                elif ch == '\\':
                    result.append(ch)
                    escape = True
                elif ch == '"' and not escape:
                    in_string = not in_string
                    result.append(ch)
                elif in_string and ch == '\n':
                    result.append('\\n')
                elif in_string and ch == '\r':
                    result.append('\\r')
                elif in_string and ch == '\t':
                    result.append('\\t')
                else:
                    result.append(ch)
            return ''.join(result)

        def _parse_text_to_scenes(raw_text: str) -> list:
            """Gemini 응답 텍스트에서 scenes 리스트를 추출 (잘린 JSON도 복구 시도)"""
            cleaned = re.sub(r'```json\s*|\s*```', '', raw_text).strip()

            # 1차: 정상 파싱 (JSON string 내 개행 sanitize 후 시도)
            try:
                data = json.loads(_sanitize_json_strings(cleaned))
                if isinstance(data, dict):
                    return data.get("scenes", [])
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError as e:
                print(f"[SceneParse] Error: {e}")

            # 2차: 배열/객체 블록 추출 후 파싱 (sanitize 적용)
            try:
                m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned)
                if m:
                    data = json.loads(_sanitize_json_strings(m.group(0)))
                    if isinstance(data, dict):
                        return data.get("scenes", [])
                    elif isinstance(data, list):
                        return data
            except Exception:
                pass

            # 3차: JSON이 잘린 경우 완성된 개별 scene 객체만 추출 (sanitize 적용)
            try:
                scenes = []
                for obj_match in re.finditer(r'\{[^{}]*"scene_number"[^{}]*\}', cleaned, re.DOTALL):
                    try:
                        obj = json.loads(_sanitize_json_strings(obj_match.group(0)))
                        if isinstance(obj, dict) and obj.get("scene_number"):
                            scenes.append(obj)
                    except Exception:
                        pass
                if scenes:
                    print(f"[SceneParse] Fallback: extracted {len(scenes)} partial scenes")
                    return scenes
            except Exception:
                pass

            return []

        def _split_script_into_chunks(text: str, chunk_size: int) -> list:
            """문장 경계 기준으로 스크립트를 청크로 분할"""
            if len(text) <= chunk_size:
                return [text]
            chunks = []
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                if end < len(text):
                    # 문장 끝(마침표/느낌표/물음표) 기준으로 자르기
                    cut = max(
                        text.rfind('다.', start, end),
                        text.rfind('요.', start, end),
                        text.rfind('죠.', start, end),
                        text.rfind('습니다.', start, end),
                    )
                    if cut > start + chunk_size // 2:
                        end = cut + 2  # 문장 부호 포함
                chunks.append(text[start:end].strip())
                start = end
            return [c for c in chunks if c]

        style_prefix_val = style_prompt or 'High quality illustration'

        def _safe_format(template: str, **kwargs) -> str:
            """format() safe version: replaces {key} placeholders, then converts {{ }} escapes to { }"""
            result = template
            for k, v in kwargs.items():
                result = result.replace('{' + k + '}', str(v))
            # Convert Python format escapes {{ → { and }} → } (same as str.format())
            result = result.replace('{{', '{').replace('}}', '}')
            return result

        # ── 레퍼런스 이미지 로딩 (스타일 프리셋 썸네일) ──────────────────
        _ref_image_bytes: bytes | None = None
        _ref_mime: str = "image/jpeg"
        if reference_image_url and reference_image_url.strip():
            try:
                import httpx as _httpx
                _ref_url = reference_image_url.strip()
                # 로컬 경로(/static/...) 처리
                if _ref_url.startswith("/"):
                    import os as _os
                    _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                    _local = _os.path.join(_base, _ref_url.lstrip("/"))
                    if _os.path.exists(_local):
                        with open(_local, "rb") as _f:
                            _ref_image_bytes = _f.read()
                        _ext = _os.path.splitext(_local)[1].lower()
                        _ref_mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(_ext.lstrip("."), "image/jpeg")
                else:
                    async with _httpx.AsyncClient(timeout=15.0) as _hc:
                        _resp = await _hc.get(_ref_url)
                        if _resp.status_code == 200:
                            _ref_image_bytes = _resp.content
                            _ct = _resp.headers.get("content-type", "")
                            if "png" in _ct: _ref_mime = "image/png"
                            elif "webp" in _ct: _ref_mime = "image/webp"
                if _ref_image_bytes:
                    print(f"[RefImage] Loaded style reference image ({len(_ref_image_bytes)} bytes, {_ref_mime})")
            except Exception as _e:
                print(f"[RefImage] Failed to load reference image: {_e}")
                _ref_image_bytes = None

        async def _gen_text_or_vision(prompt_text: str) -> str:
            """레퍼런스 이미지가 있으면 Vision(멀티모달), 없으면 텍스트 전용 호출"""
            if _ref_image_bytes:
                ref_hint = "\n\n[STYLE REFERENCE IMAGE ATTACHED]\nThe attached image shows the exact visual style, character design, and art direction to follow. Use it as the primary visual reference when writing image prompts."
                return await self.generate_text_from_image(prompt_text + ref_hint, _ref_image_bytes, _ref_mime)
            return await self.generate_text(prompt_text, temperature=0.7)

        if use_chunked:
            # ── 청크 분할 모드 ─────────────────────────────────────────────
            # 씬 수 기반 최소 청크 수 계산 (각 청크 최대 SCENES_PER_CHUNK 씬)
            min_chunks = math.ceil(num_scenes / SCENES_PER_CHUNK)  # e.g., ceil(15/8)=2
            natural_chunks = _split_script_into_chunks(script, CHUNK_CHARS)
            if len(natural_chunks) >= min_chunks:
                script_chunks = natural_chunks
            else:
                # 스크립트가 짧아도 min_chunks 개로 강제 분할
                n = min_chunks
                part_len = max(1, len(script) // n)
                script_chunks = [
                    script[i * part_len : (i + 1) * part_len if i < n - 1 else len(script)].strip()
                    for i in range(n)
                ]
                script_chunks = [c for c in script_chunks if c]
            num_chunks = len(script_chunks)
            # 씬 수를 청크별로 배분 (비례 배분)
            base_per_chunk = num_scenes // num_chunks
            remainder = num_scenes % num_chunks
            chunk_scene_counts = [base_per_chunk + (1 if i < remainder else 0) for i in range(num_chunks)]

            print(f"[ChunkedGen] {num_chunks} chunks, scenes: {chunk_scene_counts}, total={num_scenes}")

            all_scenes = []
            for c_idx, (chunk_text, c_scenes) in enumerate(zip(script_chunks, chunk_scene_counts)):
                if c_scenes <= 0:
                    continue
                chunk_limit = f"""
[중요: 장면 수 정책 - 반드시 준수]
- 반드시 정확히 **{c_scenes}개**의 장면을 생성해야 합니다.
- [현재 씬 생성 구간] 전체를 **처음부터 끝까지** {c_scenes}개로 균등하게 나누세요.
- ⚠️ 어떤 구간도 건너뛰지 마세요. 도입부, 전환, 예고도 씬으로 처리하세요.
- 각 씬의 scene_text: 해당 구간 원본 대본을 그대로 인용 (요약 금지, 장면 간 중복 금지).
- [중요] 장면들의 scene_text를 모두 이어 붙이면 [현재 씬 생성 구간] 전체가 하나도 빠짐없이, 그리고 중복 없이 완벽히 복원되어야 합니다.
- 각 scene_text는 이전 씬이나 다음 씬의 문장을 포함하지 않아야 합니다.
- JSON 배열에 scene_number 1부터 {c_scenes}까지 순서대로 포함하세요.
- [전체 대본 맥락]은 전체 흐름/세계관/캐릭터를 파악하는 데만 사용하고, 씬 생성은 [현재 씬 생성 구간]에서만 하세요.
"""
                # [CONTEXT-AWARE] 전체 대본을 맥락으로 제공하고, 현재 청크만 씬 생성 대상으로 지정
                # → Gemini가 전체 스토리 흐름/설정/캐릭터를 파악한 뒤 해당 구간 프롬프트 생성
                chunk_text_with_context = (
                    f"[전체 대본 - 전체 흐름/세계관/캐릭터 파악용, 씬 생성 대상 아님]\n"
                    f"{script}\n\n"
                    f"[현재 씬 생성 구간 - 이 부분에 대해서만 {c_scenes}개 씬 생성]\n"
                    f"{chunk_text}"
                )
                c_prompt = _safe_format(
                    prompts.GEMINI_IMAGE_PROMPTS,
                    num_scenes=c_scenes,
                    script=chunk_text_with_context,
                    style_instruction=style_instruction,
                    character_instruction=character_instruction,
                    ethnicity_instruction=ethnicity_instruction,
                    limit_instruction=chunk_limit,
                    style_prefix=style_prefix_val
                )
                c_text = await _gen_text_or_vision(c_prompt)
                c_scene_list = _parse_text_to_scenes(c_text)
                print(f"[ChunkedGen] Chunk {c_idx+1}/{num_chunks}: got {len(c_scene_list)} scenes")
                all_scenes.extend(c_scene_list)

            scenes = all_scenes
        else:
            # ── 단일 호출 모드 (기존) ──────────────────────────────────────
            prompt = _safe_format(
                prompts.GEMINI_IMAGE_PROMPTS,
                num_scenes=num_scenes,
                script=script,
                style_instruction=style_instruction,
                character_instruction=character_instruction,
                ethnicity_instruction=ethnicity_instruction,
                limit_instruction=limit_instruction,
                style_prefix=style_prefix_val
            )
            text = await _gen_text_or_vision(prompt)
            scenes = _parse_text_to_scenes(text)

        try:
            # [STYLE ENFORCEMENT] Gemini가 생성한 prompt_en에 스타일 접두사가 빠진 경우 자동 주입
            if style_prompt:
                # 스타일 키워드 중 핵심 단어 추출 (첫 3단어 정도)
                style_check_words = style_prompt.lower().split(",")[0].strip().split()[:3]
                style_check_key = " ".join(style_check_words) if style_check_words else ""

                enforced_count = 0
                for scene in scenes:
                    pen = scene.get("prompt_en", "")
                    if pen and style_check_key and style_check_key not in pen.lower():
                        scene["prompt_en"] = f"{style_prompt}, {pen}"
                        enforced_count += 1
                if enforced_count > 0:
                    print(f"[StyleEnforce] Injected style prefix into {enforced_count}/{len(scenes)} scenes")

            # [ETHNICITY ENFORCEMENT]
            if char_ethnicity:
                # Get the first part of the ethnicity description (e.g., "East Asian")
                eth_key = char_ethnicity.split(",")[0].strip().lower()
                eth_enforced_count = 0
                for scene in scenes:
                    pen = scene.get("prompt_en", "")
                    if pen and eth_key not in pen.lower():
                        # Inject after style if style exists, else at front
                        if style_prompt and style_prompt.lower() in pen.lower():
                            # Find end of style
                            scene["prompt_en"] = pen.replace(style_prompt, f"{style_prompt}, {char_ethnicity}")
                        else:
                            scene["prompt_en"] = f"{char_ethnicity}, {pen}"
                        eth_enforced_count += 1
                if eth_enforced_count > 0:
                    print(f"[EthnicityEnforce] Injected ethnicity into {eth_enforced_count}/{len(scenes)} scenes")


            # [FIX] target_scene_count가 지정된 경우 씬 분리 없이 그대로 반환
            # (씬 분리 로직이 사용자 지정 씬 수를 초과하게 만들 수 있으므로)
            if target_scene_count and target_scene_count > 0:
                # Renumber scenes sequentially
                for idx, scene in enumerate(scenes):
                    scene["scene_number"] = idx + 1
                print(f"[Gemini] Returning {len(scenes)} scenes (target={target_scene_count})")
                return scenes

            # [NEW] Hybrid Approach: Time-based correction (자동 계산 모드에서만 사용)
            # Split scenes that are too long (>20 seconds) into sub-images
            corrected_scenes = []
            MAX_SCENE_SECONDS = 30  # Maximum seconds per image (30초로 상향 → 불필요한 분할 감소)

            # 서브씬 분할 시 카메라 각도 변형 (동일 이미지 반복 방지)
            _SUB_ANGLE_VARIANTS = [
                "",  # 첫 번째는 원본
                ", close-up shot, tight framing on subject",
                ", wide establishing shot, zoom out to reveal environment",
                ", medium shot from side angle",
                ", overhead bird's eye angle",
            ]
            _SUB_BG_VARIANTS = [
                "",
                ", foreground detail emphasized",
                ", wide view with full environment visible",
                ", background elements in focus",
                ", different perspective angle",
            ]

            for scene in scenes:
                estimated_sec = scene.get("estimated_seconds", 15)

                # If estimated_seconds is missing, calculate from text length
                if not estimated_sec or estimated_sec <= 0:
                    scene_text_len = scene.get("scene_text", "")
                    estimated_sec = max(5, len(scene_text_len) / 6)  # ~6 chars/sec for Korean

                if estimated_sec <= MAX_SCENE_SECONDS:
                    # Scene is fine, keep as is
                    scene["estimated_seconds"] = estimated_sec
                    corrected_scenes.append(scene)
                else:
                    # Scene is too long, split into sub-images
                    num_splits = min(int(estimated_sec / MAX_SCENE_SECONDS) + 1, 4)  # 최대 4분할
                    sub_duration = estimated_sec / num_splits

                    scene_text = scene.get("scene_text", "")
                    text_parts = self._split_text_evenly(scene_text, num_splits)

                    for i in range(num_splits):
                        sub_scene = scene.copy()
                        sub_scene["scene_number"] = len(corrected_scenes) + 1
                        sub_scene["scene_title"] = f"{scene.get('scene_title', '')} ({i+1}/{num_splits})"
                        sub_scene["scene_text"] = text_parts[i] if i < len(text_parts) else scene_text
                        sub_scene["estimated_seconds"] = sub_duration
                        if i > 0:
                            # 단순 "variation N" 대신 카메라 각도/구도 변형으로 시각 다양성 확보
                            angle_mod = _SUB_ANGLE_VARIANTS[i % len(_SUB_ANGLE_VARIANTS)]
                            sub_scene["prompt_en"] = scene.get("prompt_en", "") + angle_mod
                            bg_mod = _SUB_BG_VARIANTS[i % len(_SUB_BG_VARIANTS)]
                            if sub_scene.get("prompt_bg"):
                                sub_scene["prompt_bg"] = scene.get("prompt_bg", "") + bg_mod
                        corrected_scenes.append(sub_scene)

            # Renumber scenes sequentially
            for idx, scene in enumerate(corrected_scenes):
                scene["scene_number"] = idx + 1

            print(f"[Hybrid] Original: {len(scenes)} scenes → Corrected: {len(corrected_scenes)} scenes")
            return corrected_scenes
            
        except Exception as e:
            print(f"JSON Parse Error in generate_image_prompts: {e}")
            pass
            
        return []
    
    def _split_text_evenly(self, text: str, num_parts: int) -> list:
        """텍스트를 균등하게 분할 (문장 경계 우선)"""
        if not text or num_parts <= 1:
            return [text]
        
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        if len(sentences) <= num_parts:
            # Not enough sentences, split by characters
            part_len = len(text) // num_parts
            parts = []
            for i in range(num_parts):
                start = i * part_len
                end = (i + 1) * part_len if i < num_parts - 1 else len(text)
                parts.append(text[start:end].strip())
            return parts
        
        # Distribute sentences evenly
        sentences_per_part = len(sentences) // num_parts
        parts = []
        for i in range(num_parts):
            start_idx = i * sentences_per_part
            end_idx = (i + 1) * sentences_per_part if i < num_parts - 1 else len(sentences)
            parts.append(" ".join(sentences[start_idx:end_idx]))
        
        return parts

    async def generate_video_search_keywords(self, script_segment: str, mood_style: str = "cinematic") -> str:
        """
        Stock Video 검색을 위한 영어 검색어 생성
        복잡한 프롬프트 대신 검색 엔진(Pexels)에 적합한 단순 키워드 조합 생성
        예: "Snowy winter night loop", "Fireplace burning cozy"
        """
        prompt = f"""
        You are a Stock Video Search Assistant. Convert the following context into a generic, simple English search query for a stock video site (Pexels/Shutterstock).
        
        [Context]
        Script: "{script_segment[:200]}"
        Mood: {mood_style}
        
        [Requirements]
        - Output ONLY the Search Query. No markdown, no quotes.
        - Use 3-5 simple English words.
        - Add 'loop' or 'background' if appropriate for ambient scenes.
        - Example: "Snowy winter night loop", "City rain timelapse", "Calm ocean waves"
        
        Search Query:
        """
        try:
            query = await self.generate_text(prompt, temperature=0.3)
            return query.strip().replace('"', '').replace("Search Query:", "").strip()
        except Exception:
            return "nature calm loop" # Fallback

    async def generate_video_preview(self, prompt: str, image_path: Optional[str] = None, model: str = "veo-3.1-fast-generate-preview", aspect_ratio: str = "16:9") -> dict:
        """Gemini Veo를 사용한 비디오 생성 (동기 SDK를 스레드에서 실행)"""
        if not self.api_key:
            return {"status": "error", "error": "API Key is missing"}

        import asyncio
        def _run_sync():
            import time
            try:
                # [FIX] Use the class-level client instead of creating a new one
                client = self.client

                self.log_debug(f"🎬 [Veo] Using class-level SDK Client. Model={model}")
                
                # Image-to-Video 처리
                image_arg = None
                if image_path and os.path.exists(image_path):
                    try:
                        ext = os.path.splitext(image_path)[1].lower()
                        mime_type = "image/png" if ext == ".png" else "image/jpeg"
                        with open(image_path, "rb") as f:
                            image_arg = {"image_bytes": f.read(), "mime_type": mime_type}
                        self.log_debug(f"🖼️ [Veo] Using reference image: {os.path.basename(image_path)}")
                    except Exception as ie:
                        self.log_debug(f"⚠️ [Veo] Image load failed: {ie}")

                operation = client.models.generate_videos(
                    model=model,
                    prompt=prompt,
                    image=image_arg,
                    config={
                        'number_of_videos': 1,
                        'aspect_ratio': aspect_ratio
                    }
                )
                self.log_debug(f"🎬 [Veo] Operation started: {type(operation).__name__} (id: {getattr(operation, 'id', 'unknown')})")

                # 폴링: client.operations.get(operation 객체) 로 갱신
                max_wait = 300
                start = _time.time()
                while not operation.done:
                    elapsed = int(_time.time() - start)
                    if elapsed >= max_wait:
                        db.add_ai_log(None, 'video', model, 'google', 'failed', prompt_summary=prompt[:100], error_msg="Timeout (5m)", elapsed_time=float(elapsed))
                        return {"status": "error", "error": "Veo 영상 생성 시간 초과 (5분)"}
                    self.log_debug(f"⏳ [Veo] Waiting... {elapsed}s")
                    _time.sleep(20)
                    operation = client.operations.get(operation)

                final_elapsed = _time.time() - start
                self.log_debug(f"🎬 [Veo] Operation done: {type(operation).__name__}")


                # 에러 확인
                op_error = getattr(operation, 'error', None)
                if op_error:
                    return {"status": "error", "error": str(op_error)}

                # 결과 탐색: response → result → operation 자체 순서로 generated_videos 찾기
                def _find_video_uri(obj):
                    if obj is None:
                        return None
                    
                    def _get_val(o, key, default=None):
                        if isinstance(o, dict): return o.get(key, default)
                        return getattr(o, key, default)

                    # 1. generated_videos (Vertex/Gemini AI 표준)
                    gv = _get_val(obj, 'generated_videos')
                    if gv and len(gv) > 0:
                        try:
                            # gv[0].video.uri or gv[0].uri
                            first = gv[0]
                            v_obj = _get_val(first, 'video')
                            if v_obj:
                                u = _get_val(v_obj, 'uri')
                                if u: return u
                            u = _get_val(first, 'uri')
                            if u: return u
                        except Exception: pass

                    # 2. videos (Legacy/Other)
                    vs = _get_val(obj, 'videos')
                    if vs and len(vs) > 0:
                        try:
                            first = vs[0]
                            u = _get_val(first, 'uri')
                            if u: return u
                            v_obj = _get_val(first, 'video')
                            if v_obj:
                                u = _get_val(v_obj, 'uri')
                                if u: return u
                        except Exception: pass
                    
                    # 3. Direct uri attribute
                    u = _get_val(obj, 'uri')
                    if u: return u
                    
                    return None

                # Try to find URI in various places
                uri = None
                candidates = [
                    ("response", getattr(operation, 'response', None)),
                    ("result", getattr(operation, 'result', None)),
                    ("operation", operation)
                ]
                
                for name, cand in candidates:
                    uri = _find_video_uri(cand)
                    if uri:
                        self.log_debug(f"✅ [Veo] Video URI found in {name}: {uri}")
                        db.add_ai_log(None, 'video', model, 'google', 'success', prompt_summary=prompt[:100], elapsed_time=final_elapsed)
                        return {"status": "ok", "video_url": uri}

                # 마지막 디버그 덤프 (실패 시 원인 파악을 위해 상세 출력)
                self.log_debug(f"🎬 [Veo] URI Not Found. op_type={type(operation).__name__}")

                try:
                    # 상세 객체 정보 로깅 (pydantic 모델이면 to_dict 사용 시도)
                    if hasattr(operation, 'to_dict'):
                        import json
                        op_dump = json.dumps(operation.to_dict(), indent=2, default=str)
                    else:
                        op_dump = str(operation)
                except: op_dump = "Could not dump operation"
                
                print(f"🎬 [Veo] Full Operation Info: {op_dump[:2000]}")
                
                # 안전 필터 확인 (힌트 제공)
                safety_msg = ""
                res = getattr(operation, 'response', getattr(operation, 'result', None))
                if res:
                    sr = getattr(res, 'safety_ratings', None) or (res.get('safety_ratings') if isinstance(res, dict) else None)
                    if sr: safety_msg = f" (Safety Ratings: {sr})"
                
                db.add_ai_log(None, 'video', model, 'google', 'failed', prompt_summary=prompt[:100], error_msg=f"URI not found{safety_msg}", elapsed_time=final_elapsed)
                return {"status": "error", "error": f"Video URI를 찾을 수 없음{safety_msg} (모든 결과 영역 탐색 실패)"}

            except Exception as e:
                import traceback
                traceback.print_exc()
                return {"status": "error", "error": str(e)}

        return await asyncio.to_thread(_run_sync)

    async def match_images_to_subtitles(self, subtitles: List[dict], image_data: List[dict]) -> dict:
        """
        자막(텍스트)와 이미지(프롬프트)를 분석하여 최적의 매칭(타이밍)을 생성
        output: { "assignments": [ {"image_index": 0, "subtitle_index": 0}, ... ] }
        """
        
        # 데이터 간소화 (토큰 절약)
        subs_simplified = [{"id": i, "text": s['text'], "start": s['start'], "end": s['end']} for i, s in enumerate(subtitles)]
        imgs_simplified = [{"id": i, "prompt": img.get('prompt', 'Unknown Scene')} for i, img in enumerate(image_data)]
        
        prompt = f"""
        You are a Professional Video Editor.
        Your task is to assign the provided Images (described by prompts) to the Subtitles (timeline) to create a cohesive video flow.

        [Inputs]
        1. Subtitles (Timeline):
        {json.dumps(subs_simplified, ensure_ascii=False, indent=1)}

        2. Available Images (Asset Pool):
        {json.dumps(imgs_simplified, ensure_ascii=False, indent=1)}

        [Instructions]
        - Assign EVERY Image to a specific Subtitle index where it should START appearing.
        - Images should be distributed logically based on the narrative context (Semantic Match).
        - If an image matches a specific keyword in a subtitle, place it there.
        - Ensure images are spread out; do not clump them all at the beginning.
        - Return the result as a JSON object with a list of assignments.

        [Output Format]
        {{
            "assignments": [
                {{ "image_id": 0, "subtitle_id": 2 }},
                {{ "image_id": 1, "subtitle_id": 5 }},
                ...
            ]
        }}
        """

        try:
            print(f"[Gemini Sync] Sending {len(subs_simplified)} subs and {len(imgs_simplified)} images to AI...")
            text = await self.generate_text(prompt, temperature=0.1)
            print(f"[Gemini Sync] Response: {text[:200]}...") # Log first 200 chars
            
            # JSON 파싱
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                print(f"[Gemini Sync] Parsed Data: {data}")
                return data
            print("[Gemini Sync] JSON Parse Failed")
            return {"assignments": []}
            
        except Exception as e:
            print(f"Image-Subtitle Match Failed: {e}")
            return {"assignments": []}

    async def analyze_success_and_creation(self, video_info: dict) -> dict:
        """
        영상의 성공 요인을 분석하고 벤치마킹 콘텐츠를 생성
        """
        title = video_info.get('title', '')
        channel = video_info.get('channelTitle', '')
        # Stats might be inside 'statistics' dict or direct keys depending on how it's passed
        views = video_info.get('statistics', {}).get('viewCount', video_info.get('viewCount', 0))
        likes = video_info.get('statistics', {}).get('likeCount', video_info.get('likeCount', 0))
        
        # Optional: Top comment if available
        top_comment = video_info.get('top_comment', '정보 없음')

        prompt = prompts.GEMINI_SUCCESS_ANALYSIS.format(
            title=title,
            channel=channel,
            views=views,
            likes=likes,
            top_comment=top_comment
        )

        try:
            text = await self.generate_text(prompt, temperature=0.7)
            
            import json
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"error": "JSON Parsing Failed", "raw": text}
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # [NEW] Level 2: Gemini Vision 기반 자산 유형 자동 분류
    # ============================================================

    # 유형 → 효과 매핑 테이블
    ASSET_EFFECT_MAP = {
        "tall_scene":   "pan_down",   # 세로로 긴 단일 장면 → Full-travel pan down
        "comic_panel":  "split_zoom", # 만화/웹툰 컷 모음 → 컷별 순차 zoom-in
        "fast_cut":     "none",       # 빠른 컷 편집 영상 → 효과 없음 (그대로)
        "normal":       "ken_burns",  # 일반 이미지/영상 → Ken Burns zoom
    }

    async def classify_asset_type(
        self,
        asset_path: str,
        extra_hint: str = ""
    ) -> dict:
        """
        [Level 2] 이미지 또는 영상 파일을 Gemini Vision으로 분석하여
        유형과 권장 영상 효과를 반환합니다.

        Parameters:
            asset_path: 이미지(.jpg/.png) 또는 영상(.mp4/.mov) 파일 경로
            extra_hint: 추가 힌트 텍스트 (예: "웹툰 컷이 포함된 이미지")

        Returns:
            {
                "asset_type": "tall_scene" | "comic_panel" | "fast_cut" | "normal",
                "recommended_effect": "pan_down" | "split_zoom" | "none" | "ken_burns",
                "confidence": 0.0 ~ 1.0,
                "reason": "분류 이유 설명",
                "aspect_ratio_hint": "tall" | "wide" | "square",  # 규칙 기반 보조 정보
                "source": "gemini" | "rule_based" | "fallback"
            }
        """
        import os

        if not os.path.exists(asset_path):
            return self._classify_fallback("파일 없음")

        ext = os.path.splitext(asset_path)[1].lower()
        is_video = ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']

        # --- Step 1: 규칙 기반 선처리 (빠른 필터) ---
        rule_result = self._classify_by_rules(asset_path, is_video)
        if rule_result.get("confidence", 0) >= 0.95:
            # 규칙으로 충분히 확신하면 Gemini 호출 생략
            print(f"🔍 [Level1 Rule] {os.path.basename(asset_path)} → {rule_result['asset_type']} (conf={rule_result['confidence']:.2f})")
            return rule_result

        # --- Step 2: 이미지/프레임 추출 ---
        try:
            image_bytes, mime_type = self._extract_frame_bytes(asset_path, is_video)
        except Exception as e:
            print(f"⚠️ [Classify] Frame extraction failed: {e}")
            return rule_result if rule_result else self._classify_fallback(str(e))

        # --- Step 3: Gemini Vision 분류 ---
        hint_text = f"\n추가 힌트: {extra_hint}" if extra_hint else ""
        prompt = f"""아래 이미지를 분석하여 영상 제작 용도로 사용할 자산 유형을 정확히 분류해주세요.{hint_text}

분류 기준:
1. **tall_scene**: 세로로 매우 긴 단일 장면 이미지/영상 (위아래로 스크롤해서 봐야 하는 구조, 만화 칸 없이 하나의 장면이 이어짐)
2. **comic_panel**: 웹툰/만화처럼 여러 컷(칸)이 격자나 수직으로 나열된 이미지 (각 컷 사이에 여백이나 테두리가 있음)
3. **fast_cut**: 빠르게 여러 장면이 교차 편집된 영상 (이미 역동적 편집이 포함됨)
4. **normal**: 일반적인 사진/일러스트/AI 생성 이미지 (16:9, 1:1, 9:16 비율의 단일 장면)

**반드시 아래 JSON 형식으로만 답하세요** (다른 텍스트 없이):
{{"asset_type": "tall_scene|comic_panel|fast_cut|normal", "confidence": 0.0~1.0, "reason": "한 줄 이유"}}"""

        try:
            raw = await self.generate_text_from_image(prompt, image_bytes, mime_type)
            parsed = self._parse_json_from_text(raw)

            asset_type = parsed.get("asset_type", "normal")
            # 유효한 타입인지 검증
            if asset_type not in self.ASSET_EFFECT_MAP:
                asset_type = "normal"

            confidence = float(parsed.get("confidence", 0.7))
            reason = parsed.get("reason", "")

            # 규칙 기반 결과와 Gemini 결과가 충돌하면 confidence 낮춤
            if rule_result.get("asset_type") and rule_result["asset_type"] != asset_type:
                confidence = min(confidence, 0.65)
                reason += f" [규칙 기반: {rule_result['asset_type']}와 상충]"

            result = {
                "asset_type": asset_type,
                "recommended_effect": self.ASSET_EFFECT_MAP.get(asset_type, "ken_burns"),
                "confidence": confidence,
                "reason": reason,
                "aspect_ratio_hint": rule_result.get("aspect_ratio_hint", "unknown"),
                "source": "gemini"
            }
            print(f"🤖 [Level2 Gemini] {os.path.basename(asset_path)} → {asset_type} (conf={confidence:.2f}) | {reason}")
            return result

        except Exception as e:
            print(f"⚠️ [Classify] Gemini failed: {e}. Using rule result.")
            return rule_result if rule_result else self._classify_fallback(str(e))

    def _classify_by_rules(self, asset_path: str, is_video: bool) -> dict:
        """규칙 기반 선분류 (빠른 메타데이터 분석)"""
        import os
        try:
            if is_video:
                # 영상: ffprobe로 해상도 조회
                import subprocess
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                probe_exe = ffmpeg_exe.replace("ffmpeg", "ffprobe")
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(
                    [probe_exe, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height,duration",
                     "-of", "csv=p=0", asset_path],
                    capture_output=True, text=True, startupinfo=startupinfo
                )
                parts = result.stdout.strip().split(",")
                w, h = int(parts[0]), int(parts[1])
            else:
                # 이미지: PIL로 해상도 조회
                from PIL import Image
                img = Image.open(asset_path)
                w, h = img.size

            ratio = h / w if w > 0 else 1.0

            # 종횡비 기반 분류
            if ratio >= 2.0:
                # 세로 2배 이상 → tall_scene 확신
                return {
                    "asset_type": "tall_scene",
                    "recommended_effect": "pan_down",
                    "confidence": 0.95,
                    "reason": f"종횡비 {ratio:.2f} ≥ 2.0 → 세로로 긴 장면",
                    "aspect_ratio_hint": "tall",
                    "source": "rule_based"
                }
            elif ratio >= 1.5:
                # 세로 이미지 (일반 9:16 등) → Gemini에 위임
                return {
                    "asset_type": "normal",
                    "recommended_effect": "ken_burns",
                    "confidence": 0.5,
                    "reason": f"종횡비 {ratio:.2f} (세로형, 추가 분석 필요)",
                    "aspect_ratio_hint": "tall",
                    "source": "rule_based"
                }
            elif ratio < 0.7:
                # 가로로 긴 이미지
                return {
                    "asset_type": "normal",
                    "recommended_effect": "ken_burns",
                    "confidence": 0.7,
                    "reason": f"종횡비 {ratio:.2f} → 가로 이미지",
                    "aspect_ratio_hint": "wide",
                    "source": "rule_based"
                }
            else:
                # 정사각형에 가까운 비율 → 판단 보류
                return {
                    "asset_type": "normal",
                    "recommended_effect": "ken_burns",
                    "confidence": 0.4,
                    "reason": f"종횡비 {ratio:.2f} → 일반",
                    "aspect_ratio_hint": "square",
                    "source": "rule_based"
                }
        except Exception as e:
            return self._classify_fallback(str(e))

    def _extract_frame_bytes(self, asset_path: str, is_video: bool) -> tuple:
        """이미지/영상에서 분석용 이미지 바이트 추출"""
        import os
        if is_video:
            # 영상: 첫 프레임 추출 (ffmpeg)
            import subprocess
            import tempfile
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                frame_path = tmp.name
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run([
                ffmpeg_exe, "-y", "-i", asset_path,
                "-vframes", "1", "-q:v", "2", frame_path
            ], check=True, capture_output=True, startupinfo=startupinfo)
            with open(frame_path, "rb") as f:
                data = f.read()
            os.remove(frame_path)
            return data, "image/jpeg"
        else:
            # 이미지: 단순 읽기 (크기 제한 적용)
            from PIL import Image
            import io
            img = Image.open(asset_path).convert("RGB")
            # 너무 크면 축소 (Gemini 용량 제한 고려)
            max_dim = 1024
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            ext = os.path.splitext(asset_path)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            return buf.getvalue(), mime

    def _classify_fallback(self, reason: str = "") -> dict:
        """분류 실패 시 안전한 기본값 반환"""
        return {
            "asset_type": "normal",
            "recommended_effect": "ken_burns",
            "confidence": 0.0,
            "reason": f"분류 실패 (fallback): {reason}",
            "aspect_ratio_hint": "unknown",
            "source": "fallback"
        }

    def _parse_json_from_text(self, text: str) -> dict:
        """텍스트에서 JSON 추출"""
        import json
        import re
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        return {}

    async def generate_deep_dive_script(self, project_id: int, topic: str, duration_seconds: int = 180, target_language: str = "ko", user_notes: str = "없음", mode: str = "monologue") -> dict:
        """여러 소스를 학습하여 고품질 롱폼 대본 생성 (NotebookLM 스타일)"""
        
        # 1. 프로젝트 소스 로드
        sources = db.get_project_sources(project_id)
        if not sources:
            sources_text = "제공된 참고 자료가 없습니다. 일반적인 지식을 바탕으로 작성하세요."
        else:
            sources_list = []
            for i, s in enumerate(sources):
                # content가 None인 경우를 대비해 빈 문자열 처리
                content = s.get('content') or ""
                info = f"Source {i+1} [{s['type']}]: {s['title']}\nContent: {content[:3000]}"
                sources_list.append(info)
            sources_text = "\n\n".join(sources_list)

        # 2. 언어 설정
        context_instruction = "Korean context"
        if target_language == "ja": context_instruction = "Japanese context"
        elif target_language == "en": context_instruction = "Global context"
        elif target_language == "vi": context_instruction = "Vietnamese context"

        # 3. 프롬프트 구성 (모드에 따라 분기)
        prompt_template = prompts.GEMINI_DEEP_DIVE_SCRIPT
        if mode == "dialogue":
            prompt_template = prompts.GEMINI_DEEP_DIVE_DIALOGUE

        prompt = prompt_template.format(
            sources_text=sources_text,
            topic_keyword=topic,
            duration_seconds=duration_seconds,
            target_language_context=context_instruction,
            user_notes=user_notes
        )

        text = await self.generate_text(prompt, temperature=0.4) # Slightly higher for dialogue flow
        
        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return result
            except Exception:
                pass
        
        return {"error": "대본 생성 실패", "raw": text}

    async def create_batch_job(self, input_file_path: str, model: str = "gemini-3.1-flash-live-preview", display_name: str = "batch-job") -> dict:
        """
        [새로운 기능] Gemini Batch API - 대규모 백그라운드 처리를 위한 일괄 작업 예약 (비용 50% 절감)
        JSONL 파일을 업로드하고 비동기 배치 작업을 생성합니다.
        """
        import asyncio
        from google import genai
        
        def _run_batch():
            client = genai.Client(api_key=self.api_key)
            # 1. 파일 업로드
            uploaded_file = client.files.upload(
                file=input_file_path,
                config={"mime_type": "jsonl"}
            )
            # 2. 배치 작업 생성
            batch_job = client.batches.create(
                model=model,
                src=uploaded_file.name,
                config={"display_name": display_name}
            )
            return {
                "job_name": batch_job.name,
                "job_state": batch_job.state.name if hasattr(batch_job.state, 'name') else str(batch_job.state),
                "file_name": uploaded_file.name
            }
        
        # 블로킹 작업이므로 스레드 풀에서 실행
        return await asyncio.to_thread(_run_batch)

    async def get_batch_job_status(self, job_name: str) -> dict:
        """
        배치 작업 상태를 확인합니다.
        """
        import asyncio
        from google import genai
        
        def _get_status():
            client = genai.Client(api_key=self.api_key)
            batch_job = client.batches.get(name=job_name)
            
            dest_file = None
            if hasattr(batch_job, 'dest') and batch_job.dest and hasattr(batch_job.dest, 'file_name'):
                dest_file = batch_job.dest.file_name
                
            return {
                "job_name": batch_job.name,
                "job_state": batch_job.state.name if hasattr(batch_job.state, 'name') else str(batch_job.state),
                "dest_file": dest_file,
                "error_message": str(getattr(batch_job, 'error_message', '')) if getattr(batch_job, 'error_message', None) else None
            }
            
        return await asyncio.to_thread(_get_status)

    async def download_batch_results(self, dest_file_name: str) -> str:
        """
        모두 완료된 배치 작업의 결과를 다운로드하여 JSONL 포맷의 문자열로 반환합니다.
        """
        import asyncio
        from google import genai
        
        def _download():
            client = genai.Client(api_key=self.api_key)
            file_content_bytes = client.files.download(file=dest_file_name)
            return file_content_bytes.decode("utf-8")
            
        return await asyncio.to_thread(_download)


# 싱글톤 인스턴스
gemini_service = GeminiService()
