"""
Gemini API 서비스
- 텍스트 생성 (대본, 분석 등)
- 이미지 생성 (Imagen 3)
- 영상 생성 (Veo)
"""
import httpx
from typing import Optional, List
import base64
import os
import json
import re
import database as db

from config import config
from services.prompts import prompts


class GeminiService:
    def __init__(self):
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def api_key(self):
        return config.GEMINI_API_KEY

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """텍스트 생성"""
        url = f"{self.base_url}/models/gemini-2.0-flash:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()

            if "candidates" in result:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise Exception(f"Gemini API 오류: {result}")

    async def generate_text_from_image(self, prompt: str, image_bytes: bytes, mime_type: str = "image/png") -> str:
        """이미지 + 텍스트 생성 (Vision)"""
        url = f"{self.base_url}/models/gemini-2.0-flash:generateContent?key={self.api_key}"

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
                "temperature": 0.4, # Lower temperature for accurate description
                "maxOutputTokens": 2048
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()

            if "candidates" in result:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                error_msg = result.get('error', {}).get('message', str(result))
                print(f"❌ [Gemini Vision] API Error: {error_msg}")
                raise Exception(f"Gemini Vision API 오류: {error_msg}")

    async def analyze_webtoon_panel(self, image_path: str, context: Optional[str] = None, voice_options: Optional[str] = None) -> dict:
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
            
            response_text = await self.generate_text_from_image(prompt, img_bytes, mime_type=mime_type)
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

    async def generate_webtoon_plan(self, scenes: List[dict]) -> dict:
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
            text = await self.generate_text(prompt, temperature=0.7)
            
            # JSON 파싱
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
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
            
            Write the summary in Korean, formatted nicely for a web UI. Keep it to 3-5 sentences.
            Focus on proving that you understood the context.
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
        num_images: int = 1
    ) -> List[bytes]:
        """이미지 생성 (Imagen 3 우선, 실패 시 Imagen 2로 폴백)"""
        
        # [MODIFIED] Use a wider range of models for fallback
        models = [
            "imagen-4.0-generate-001",      # Imagen 4 (Confirmed working for this environment)
            "imagen-3.0-generate-001",      # Imagen 3 Standard
            "imagen-3.0-fast-generate-001", # Imagen 3 Fast
            "imagen-4.0-fast-generate-001", # Imagen 4 Fast
        ]
        
        last_error = None
        
        for model_name in models:
            try:
                url = f"{self.base_url}/models/{model_name}:predict?key={self.api_key}"
                print(f"🎨 [Imagen] Trying model: {model_name}")
                
                # [NEW] Style Reinforcement for Non-Realistic Styles
                # If the prompt contains stylistic markers but avoids realism, reinforce negative prompts
                stylistic_keywords = ["wimpy", "anime", "cartoon", "ghibli", "sketch", "line art", "doodle", "webtoon"]
                is_stylistic = any(kw in prompt.lower() for kw in stylistic_keywords)
                contains_photo = any(kw in prompt.lower() for kw in ["photo", "realistic", "8k", "cinematic"])
                
                final_prompt = prompt
                if is_stylistic and not contains_photo:
                    # Append massive negative reinforcement to force the style and avoid unwanted text
                    final_prompt += ". NO PHOTOREALISM. NO 3D RENDER. NO DEPTH OF FIELD. FLAT 2D STYLE ONLY. ABSOLUTELY NO REALISTIC TEXTURES. NO TEXT. NO WORDS. NO LETTERS. NO ALPHABET."

                payload = {
                    "instances": [{"prompt": final_prompt}],
                    "parameters": {
                        "sampleCount": num_images,
                        "aspectRatio": aspect_ratio,
                        "safetySetting": "block_low_and_above"
                    }
                }
                
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(url, json=payload)
                    
                    # 404 에러면 다음 모델 시도
                    if response.status_code == 404:
                        print(f"⚠️ [Imagen] Model {model_name} not found (404), trying next...")
                        last_error = f"Model {model_name} not found"
                        continue
                    
                    # 다른 에러는 즉시 실패
                    if response.status_code != 200:
                        error_info = response.text
                        print(f"❌ [Imagen] Error ({response.status_code}): {error_info}")
                        raise Exception(f"API Error ({response.status_code}): {error_info}")
                    
                    result = response.json()
                    print(f"🔍 [Imagen] Response from {model_name}:")
                    print(f"   Keys: {list(result.keys())}")
                    
                    images = []
                    if "predictions" in result:
                        print(f"   Predictions count: {len(result['predictions'])}")
                        for idx, pred in enumerate(result["predictions"]):
                            print(f"   Prediction {idx} keys: {list(pred.keys())}")
                            if "bytesBase64Encoded" in pred:
                                img_bytes = base64.b64decode(pred["bytesBase64Encoded"])
                                images.append(img_bytes)
                                print(f"   ✅ Decoded image {idx}, size: {len(img_bytes)} bytes")
                            # Add check for other formats if needed
                            elif "mimeType" in pred and "bytesBase64Encoded" in pred: # Some versions
                                 img_bytes = base64.b64decode(pred["bytesBase64Encoded"])
                                 images.append(img_bytes)
                                 print(f"   ✅ Decoded image {idx} (alt format), size: {len(img_bytes)} bytes")
                            else:
                                print(f"⚠️ [Imagen] Unknown prediction format: {pred.keys()}")
                                print(f"   Full prediction content: {pred}")
                                # Check if there's a safety/filter reason
                                if "error" in pred:
                                    print(f"   ❌ Error in prediction: {pred['error']}")
                                if "safetyRatings" in pred:
                                    print(f"   🚫 Safety ratings: {pred['safetyRatings']}")
                    else:
                        print(f"⚠️ [Imagen] No 'predictions' key in response. Keys: {result.keys()}")
                        print(f"   Full response: {str(result)[:500]}")

                    # Check if we got images (MOVED OUTSIDE else block!)
                    if images:
                        print(f"✅ [Imagen] Successfully generated {len(images)} image(s) with {model_name}")
                        return images
                    
                    # No images generated - try next model or fail
                    error_msg = result.get('error', {}).get('message', 'No image data in response')
                    print(f"⚠️ [Imagen] No images from {model_name}: {error_msg}")
                    last_error = f"No images: {error_msg}"
                    continue
                    
            except httpx.TimeoutException:
                print(f"⏱️ [Imagen] Timeout with {model_name}, trying next...")
                last_error = f"Timeout with {model_name}"
                continue
            except Exception as e:
                # 404가 아닌 다른 에러는 즉시 실패
                if "404" not in str(e):
                    raise
                print(f"⚠️ [Imagen] Error with {model_name}: {e}, trying next...")
                last_error = str(e)
                continue
        
        # 모든 모델 시도 실패
        if "No images" in str(last_error) or "Safety" in str(last_error):
             raise Exception(f"이미지 생성기(Imagen) 보안 필터에 의해 차단되었습니다. 유명인 이름, 브랜드명, 또는 부적절한 키워드가 포함되어 있는지 확인하세요. (Last error: {last_error})")
        raise Exception(f"모든 이미지 생성 모델 시도 실패. 잠시 후 다시 시도해주세요. (Last error: {last_error})")


    async def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        duration_seconds: int = 6, 
        aspect_ratio: str = "16:9"
    ) -> Optional[bytes]:
        """영상 생성 (Veo) - Text-to-Video or Image-to-Video"""
        model_name = "veo-3.0-fast-generate-001"
        url = f"{self.base_url}/models/{model_name}:predict?key={self.api_key}"
        
        # 기본 프롬프트 보강
        enhanced_prompt = f"{prompt}, cinematic movement, 4k, fluid motion"

        instance_data = {"prompt": enhanced_prompt}

        # 이미지 입력이 있는 경우 (Image-to-Video)
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    img_bytes = f.read()
                    encoded_img = base64.b64encode(img_bytes).decode("utf-8")
                    instance_data["image"] = {"bytesBase64Encoded": encoded_img}
            except Exception as e:
                print(f"Image read error: {e}")

        payload = {
            "instances": [instance_data],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": aspect_ratio  # [NEW] Pass Aspect Ratio
            }
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(url, json=payload)
                
                if response.status_code != 200:
                    print(f"Video Gen Error ({response.status_code}): {response.text}")
                    return None
                    
                result = response.json()

                if "predictions" in result:
                    pred = result["predictions"][0]
                    # 응답 포맷 체크
                    if "video" in pred and "bytesBase64Encoded" in pred["video"]:
                         return base64.b64decode(pred["video"]["bytesBase64Encoded"])
                    if "bytesBase64Encoded" in pred:
                        return base64.b64decode(pred["bytesBase64Encoded"])
                        
                print(f"Video Gen Unexpected Response: {result}")
                return None
                
            except Exception as e:
                print(f"Video Gen Exception: {e}")
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

    async def generate_script_structure(self, analysis_data: dict, recent_titles: List[str] = None, target_language: str = "ko", style_prompt: str = "", accumulated_knowledge: List[dict] = None) -> dict:
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
            except: pass

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

        text = await self.generate_text(prompt, temperature=0.5)
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        return {"error": "구조 생성 실패", "raw": text}
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

    async def generate_character_prompts_from_script(self, script: str, visual_style: str = "photorealistic") -> List[dict]:
        """대본을 분석하여 등장인물 정보 및 이미지 프롬프트 생성"""
        
        prompt = prompts.GEMINI_CHARACTER_PROMPTS.format(
            script=script[:8000], 
            visual_style=visual_style
        )
        
        text = await self.generate_text(prompt, temperature=0.5)
        
        # JSON 파싱
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("characters", [])
            except Exception as e:
                print(f"Character prompt JSON parse error: {e}")
                pass
        return []

    async def generate_image_prompts_from_script(self, script: str, duration_seconds: int, style_prompt: str = None, characters: List[dict] = None) -> List[dict]:
        """대본을 분석하여 장면별 이미지 프롬프트 생성 (가변 페이싱 및 캐릭터 일관성 적용)"""
        
        # [NEW] 가변 페이싱(Dynamic Pacing) 로직 - 사용자 요청에 따른 정밀 조정
        # 0 ~ 2분 (120s): 8초당 1장 (15장)
        # 2 ~ 5분 (180s): 20초당 1장 (9장)
        # 5 ~ 7분 (120s): 40초당 1장 (3장)
        # 7 ~ 10분 (180s): 60초당 1장 (3장)
        # 10 ~ 20분 (600s): 120초당 1장 (5장)
        # 20분 이후: 600초당 1장
        
        num_scenes = 0
        if duration_seconds <= 120:
            num_scenes = duration_seconds // 8
        elif duration_seconds <= 300:
            num_scenes = 15 + (duration_seconds - 120) // 20
        elif duration_seconds <= 420:
            num_scenes = 15 + 9 + (duration_seconds - 300) // 40
        elif duration_seconds <= 600:
            num_scenes = 15 + 9 + 3 + (duration_seconds - 420) // 60
        elif duration_seconds <= 1200:
            num_scenes = 30 + (duration_seconds - 600) // 120
        else:
            num_scenes = 35 + (duration_seconds - 1200) // 600
        
        num_scenes = max(3, int(num_scenes))
        
        # [CRITICAL] 실사 키워드 방지 로직 보강
        is_realistic = any(kw in style_prompt.lower() for kw in ["realistic", "photo", "cinematic", "8k"])
        style_conflict_prevention = ""
        if not is_realistic:
            style_conflict_prevention = """
[스타일 충돌 방지 - 엄격 준수]
현재 지정된 스타일은 실사(Photorealistic)가 아닙니다.
프롬프트 생성 시 'realistic', 'photorealistic', 'hyper-detailed', '8k', 'raw photo', 'masterpiece', 'cinematic lighting', 'depth of field', '3d render', 'octane render', 'unreal engine' 등의 실사 지향적 키워드를 **절대** 사용하지 마세요.
또한, 이미지 내에 어떠한 영어 텍스트, 로고, 브랜드명, 레이블도 포함되지 않도록 하세요. (ABSOLUTELY NO English text, NO logos, NO brand names, NO labels in the prompt or the image.)
인물과 배경 모두가 "{style_prompt}"의 매체 특성(그림체, 질감)을 완벽하게 따라야 하며, 조금이라도 실사 느낌이 섞이지 않도록 하세요.
"""

        style_instruction = f"""
[스타일 지침 - 매우 중요]
모든 이미지 프롬프트에 다음 스타일을 반드시 반영하세요:
"{style_prompt}"

모든 prompt_en의 시작 부분에 이 스타일 키워드를 포함시켜야 합니다.
예: "{style_prompt}, ..."
{style_conflict_prevention}
"""

        character_instruction = ""
        if characters:
            char_descriptions = "\n".join([f"- {c['name']} ({c['role']}): {c['prompt_en']}" for c in characters])
            character_instruction = f"""
[등장인물 일관성 지침 - 필수]
이 영상에는 다음 캐릭터들이 등장합니다. 장면별 prompt_en 생성 시 해당 인물이 등장한다면 아래 묘사를 그대로 사용하여 외형 일관성을 유지하세요:
{char_descriptions}
"""

        # [NEW] 장시간 영상 페이싱 지침 (사용자 요청 세분화 반영)
        limit_instruction = ""
        if duration_seconds > 0: # 짧은 영상도 일관된 지침 적용
            limit_instruction = f"""
[중요: 영상 페이싱 정책]
사용자의 몰입도를 유지하면서 제작 효율을 높이기 위해 다음 구간별 페이싱을 엄격히 준수하세요:
1. **초반 2분 (0~2분)**: 8초당 1장 수준으로 매우 역동적인 시각 변화를 주어 후킹하세요.
2. **몰입 단계 (2~5분)**: 20초당 1장 수준으로 핵심 장면 위주로 전환하세요.
3. **안정 단계 (5~7분)**: 40초당 1장 수준으로 전개 속도를 조절하세요.
4. **유지 단계 (7~10분)**: 1분당 1장 수준으로 분위기를 유지하세요.
5. **그 이후 (10분~20분)**: 2분당 1장, **(20분 이후)**: 10분당 1장 수준으로 큰 흐름만 짚어주세요.
- 위 페이싱에 맞춰 총 **{num_scenes}개**의 장면을 시간 순서대로 골고루 배분하여 JSON을 생성하세요.
"""

        prompt = prompts.GEMINI_IMAGE_PROMPTS.format(
            num_scenes=num_scenes,
            script=script,
            style_instruction=style_instruction,
            character_instruction=character_instruction, # [NEW]
            limit_instruction=limit_instruction,
            style_prefix=style_prompt or 'High quality, photorealistic'
        )

        text = await self.generate_text(prompt, temperature=0.7)

        # JSON 파싱
        import json
        import re

        try:
            # 1. Clean Markdown code blocks
            cleaned_text = re.sub(r'```json\s*|\s*```', '', text).strip()
            
            # 2. Try parsing the cleaned text directly
            try:
                data = json.loads(cleaned_text)
            except json.JSONDecodeError:
                # 3. If direct parse fails, try searching for JSON object or list
                json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned_text)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    return []

            # 4. Extract scenes list
            if isinstance(data, dict):
                scenes = data.get("scenes", [])
            elif isinstance(data, list):
                scenes = data
            else:
                scenes = []
            
            # [NEW] Hybrid Approach: Time-based correction
            # Split scenes that are too long (>20 seconds) into sub-images
            corrected_scenes = []
            MAX_SCENE_SECONDS = 20  # Maximum seconds per image
            MIN_SCENE_SECONDS = 5   # Minimum seconds per image
            
            for scene in scenes:
                estimated_sec = scene.get("estimated_seconds", 15)
                
                # If estimated_seconds is missing, calculate from text length
                if not estimated_sec or estimated_sec <= 0:
                    scene_text = scene.get("scene_text", "")
                    estimated_sec = max(5, len(scene_text) / 6)  # ~6 chars/sec for Korean
                
                if estimated_sec <= MAX_SCENE_SECONDS:
                    # Scene is fine, keep as is
                    scene["estimated_seconds"] = estimated_sec
                    corrected_scenes.append(scene)
                else:
                    # Scene is too long, split into sub-images
                    num_splits = int(estimated_sec / MAX_SCENE_SECONDS) + 1
                    sub_duration = estimated_sec / num_splits
                    
                    scene_text = scene.get("scene_text", "")
                    text_parts = self._split_text_evenly(scene_text, num_splits)
                    
                    for i in range(num_splits):
                        sub_scene = scene.copy()
                        sub_scene["scene_number"] = len(corrected_scenes) + 1
                        sub_scene["scene_title"] = f"{scene.get('scene_title', '')} ({i+1}/{num_splits})"
                        sub_scene["scene_text"] = text_parts[i] if i < len(text_parts) else scene_text
                        sub_scene["estimated_seconds"] = sub_duration
                        # Slightly vary the prompt for visual diversity
                        if i > 0:
                            sub_scene["prompt_en"] = scene.get("prompt_en", "") + f", variation {i+1}"
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
        except:
            return "nature calm loop" # Fallback

    async def generate_video(self, prompt: str, model: str = "veo-3.1-generate-preview") -> dict:
        """
        Gemini Veo (veo-3.1-generate-preview)를 사용한 비디오 생성
        """
        if not self.api_key:
             return {"status": "error", "error": "API Key is missing"}
        
        try:
             # 임시 동기 호출 (비동기 래퍼 필요 시 수정)
             # google.genai.Client 사용
             from google import genai
             client = genai.Client(api_key=self.api_key)
             
             print(f"DEBUG: Starting Veo generation for prompt: {prompt}")
             # 1. Generate Video
             # https://ai.google.dev/gemini-api/docs/video
             operation = client.models.generate_videos(
                 model=model,
                 prompt=prompt,
                 config={
                    'number_of_videos': 1,
                    # 'fps': 24, 
                    # 'duration_seconds': 5 # Preview is usually short
                 }
             )
             
             
             # Handle operation - it might be a string (operation name) or an object
             print(f"DEBUG: Operation type: {type(operation)}")
             
             # If operation is a string, we need to poll differently
             if isinstance(operation, str):
                 op_name = operation
                 print(f"DEBUG: Operation is a string (name): {op_name}")
                 
                 # Manual polling using the operation name
                 import time
                 max_attempts = 60  # 5 minutes
                 attempts = 0
                 
                 while attempts < max_attempts:
                     print(f"Polling operation status... (attempt {attempts + 1}/{max_attempts})")
                     time.sleep(5)
                     attempts += 1
                     
                     try:
                         # Try to get operation status
                         # The SDK might have a different method to check status
                         op_status = client.operations.get(op_name)
                         
                         # Check if it's done
                         if hasattr(op_status, 'done') and op_status.done:
                             operation = op_status
                             break
                         elif isinstance(op_status, dict) and op_status.get('done'):
                             operation = op_status
                             break
                     except Exception as e:
                         print(f"Polling error: {e}")
                         # If we can't poll, just wait and hope for the best
                         if attempts >= 30:  # After 2.5 minutes, try to get result anyway
                             try:
                                 operation = client.operations.get(op_name)
                                 break
                             except:
                                 pass
                 
                 if attempts >= max_attempts:
                     return {"status": "error", "error": "Video generation timed out"}
             
             # If operation is an object, use wait() or poll
             elif hasattr(operation, 'wait'):
                 print("DEBUG: Using operation.wait() method")
                 try:
                     operation = operation.wait(timeout=300)
                 except Exception as e:
                     print(f"Wait error: {e}")
                     return {"status": "error", "error": f"Wait failed: {str(e)}"}
             
             # Try using result() method (blocks until complete)
             elif hasattr(operation, 'result'):
                 print("DEBUG: Using operation.result property (checking if complete)")
                 try:
                     # First check if it's a method or property
                     if callable(operation.result):
                         print("DEBUG: result is callable (method)")
                         result_obj = operation.result(timeout=300)
                     else:
                         print("DEBUG: result is a property")
                         # For properties, we need to poll manually
                         import time
                         max_wait = 300  # 5 minutes
                         start_time = time.time()
                         
                         while time.time() - start_time < max_wait:
                             # Try to refresh operation status
                             if hasattr(operation, 'name'):
                                 try:
                                     fresh_op = client.operations.get(operation.name)
                                     operation = fresh_op
                                 except:
                                     pass
                             
                             # Check if done
                             if hasattr(operation, 'done'):
                                 if callable(operation.done):
                                     is_done = operation.done()
                                 else:
                                     is_done = operation.done
                                 
                                 if is_done:
                                     print("DEBUG: Operation completed!")
                                     break
                             
                             print(f"Waiting for completion... ({int(time.time() - start_time)}s elapsed)")
                             time.sleep(5)
                         
                         if time.time() - start_time >= max_wait:
                             return {"status": "error", "error": "Timeout waiting for video generation"}
                         
                         result_obj = operation.result
                     
                     print(f"DEBUG: Got result: {type(result_obj)}")
                 except Exception as e:
                     print(f"Result error: {e}")
                     import traceback
                     traceback.print_exc()
                     return {"status": "error", "error": f"Result failed: {str(e)}"}
             
             
             # Otherwise, try manual polling on the object
             else:
                 print("DEBUG: Manual polling on operation object")
                 import time
                 max_attempts = 60
                 attempts = 0
                 
                 while attempts < max_attempts:
                     if hasattr(operation, 'done') and operation.done:
                         break
                     
                     print(f"Waiting... (attempt {attempts + 1}/{max_attempts})")
                     time.sleep(5)
                     attempts += 1
                 
                 if attempts >= max_attempts:
                     return {"status": "error", "error": "Timeout"}
                  
             if operation.error:
                 print(f"Veo Error: {operation.error}")
                 return {"status": "error", "error": str(operation.error)}
                 
             # 3. Get Result
             # operation.result is likely a property, not a method
             result = operation.result 
             
             if not result:
                  return {"status": "error", "error": "No result returned"}
                  
             # Inspect structure based on new SDK
             if hasattr(result, 'generated_videos'):
                 generated_video = result.generated_videos[0]
                 video_url = generated_video.video.uri
             else:
                 # Fallback/Debug
                 print(f"DEBUG: Result structure: {result}")
                 video_url = getattr(result, 'uri', None)
             
             if not video_url:
                 return {"status": "error", "error": "Video URI not found in result"}
             
             return {
                 "status": "ok", 
                 "video_url": video_url,
                 "metadata": {
                     "model": model,
                     "prompt": prompt
                 }
             }

        except Exception as e:
            print(f"Veo Generation Failed: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

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
                dur = float(parts[2]) if len(parts) > 2 else 0.0
            else:
                # 이미지: PIL로 해상도 조회
                from PIL import Image
                img = Image.open(asset_path)
                w, h = img.size
                dur = 0.0

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
            except:
                pass
        
        return {"error": "대본 생성 실패", "raw": text}

    async def create_batch_job(self, input_file_path: str, model: str = "gemini-2.0-flash", display_name: str = "batch-job") -> dict:
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
