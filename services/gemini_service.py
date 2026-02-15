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

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()

            if "candidates" in result:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                error_msg = result.get('error', {}).get('message', str(result))
                raise Exception(f"Gemini Vision API 오류: {error_msg}")

    async def analyze_webtoon_panel(self, image_path: str, context: Optional[str] = None, voice_options: Optional[str] = None) -> dict:
        """웹툰 패널 한 칸을 분석하여 대사, 캐릭터, 연출 정보 추출"""
        
        context_inst = ""
        if context:
            context_inst = f"\n{context}\n"

        prompt = f"""
        Analyze this webtoon panel image.
        {context_inst}
        1. Extract all text/dialogue in Korean. 
           **EXCLUDE**: 
           - Legal notices, copyright warnings (e.g., "※본 작품은 저작권 법에 의해...", "불법 복제 금지"), logo credits, or watermarks.
           - **Onomatopoeia or stylized sound effect text** (e.g., "쾅!", "털썩", "슈우우", "덜덜"). These are visual sound effects, NOT dialogue.
           **INCLUDE**: Only actual character speech or narrative text meant to be read aloud.
        2. Identify who is speaking based on the dialogue and visual context. 
           - **CRITICAL**: Check the [KNOWN CHARACTERS] list in the context. If the character matches, YOU MUST USE THE EXACT SAME NAME.
           - Do NOT use generic names like "Man" or "Woman" if they match a known character (e.g. "Hero", "Jin-woo").
           - If the speaker's name is not explicitly shown, infer it from the context.
           - Only use 'Unknown' if absolutely impossible to infer. Do NOT use 'None' if there is dialogue.
        3. Describe the visual action and atmosphere briefly in English.
           - Append specific Camera Movement keywords at the end. (e.g., "[Camera: Zoom in]", "[Camera: Pan left]", "[Camera: Static]")
        4. Suggest appropriate sound effects (SFX) for this scene (e.g., Boom, Rain, Footsteps, Crowd noise).
        5. **focal_point_y**: A normalized value (float 0.0 to 1.0) indicating the vertical center of the most important subject (e.g., character's eyes/face, main object).
           - 0.0 is top, 1.0 is bottom.
           - This will be used to crop tall vertical panels without cutting through heads or waists.
        6. **is_meaningless**: Set to true if this image contains NO story content.

        Return ONLY a JSON object in this format:
        {{
            "dialogue": "extracted speech text here (empty if only SFX/copyright/logo)",
            "character": "speaker name or 'Unknown'",
            "visual_desc": "brief visual description in English",
            "motion_desc": "DETAILED description for AI Video Generation (Wan 2.1). Focus on movement (e.g. 'Hair blowing in wind', 'Fire flickering', 'Tears falling', 'Sword swinging'). ALSO include Camera Movement (e.g. 'Slow Pan Down along the body', 'Reviewing from top to bottom').",
            "atmosphere": "e.g. dramatic, funny, scary",
            "sound_effects": "suggested SFX list (comma separated) or 'None'",
            "focal_point_y": 0.5,
            "is_meaningless": false,
            "voice_recommendation": {{ "id": "voice_id_here", "name": "voice_name_here", "reason": "reason" }},
            "voice_settings": {{ "stability": 0.5, "similarity_boost": 0.75, "speed": 1.0, "reason": "why this tone?" }},
            "audio_direction": {{ "sfx_prompt": "detailed english description for sound generation", "bgm_mood": "e.g. suspense, happy, sad", "has_sfx": true }}
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
            
            response_text = await self.generate_text_from_image(prompt, img_bytes, mime_type="image/jpeg")
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
            
            # [CRITICAL] Fake Description Injection with VARIETY
            # 정보가 족할 때 획일적인 'Pan Down'만 나오지 않도록, 가짜 묘사를 상황별로 다르게 주입하여
            # Gemini가 다양한 연출(Wan, Zoom, Shake 등)을 제안하도록 유도함.
            raw_desc = str(sc.get('visual_desc') or '')
            
            # 정보가 정말 없거나 분석 실패인 경우
            if not raw_desc or "Analysis failed" in raw_desc or len(raw_desc) < 5:
                 import random
                 idx = sc.get('idx', 0)
                 
                 # 씬 번호 기반으로 다양성 부여 (단순 랜덤은 아님)
                 styles = [
                     ("Dynamic Action", "Intense movement, sparks flying, high tension.", "Mysterious"),
                     ("Emotional Close-up", "Character's face showing deep emotion, tears or anger.", "Sad/Angry"),
                     ("Wide Atmosphere", "A vast landscape with weather effects like rain or wind.", "Grand"),
                     ("Shocking Twist", "Sudden impact, screen shaking, dramatic zoom.", "Tense")
                 ]
                 
                 # 씬 호에 따라 스타일 순환
                 style_name, style_desc, style_mood = styles[idx % len(styles)]
                 
                 fake_desc = f"A {style_name} webtoon panel. {style_desc}"
                 d_text = sc.get('dialogue', '')
                 if d_text: fake_desc += f" Characters are saying: '{d_text}'"
                 
                 sc['visual_desc'] = fake_desc
                 sc['atmosphere'] = style_mood

                
            scenes_preview.append({
                "scene_number": sc.get("scene_number"),
                "dialogue": sc.get("dialogue"),
                "visual_desc": sc.get("visual_desc"),
                "character": sc.get("character"),
                "sound_effects": sc.get("sound_effects")
            })
            
        scenes_json = json.dumps(scenes_preview, ensure_ascii=False)
        
        prompt = f"""
        # ROLE: Hollywood Trailer Editor & VFX Supervisor
        You are creating a high-end cinematic video plan based on webtoon scenes.
        Your goal is to transform static images into a dynamic, immersive video experience using advanced AI video generation tools (Wan 2.1).

        [INPUT DATA]
        {scenes_json}

        [CRITICAL INSTRUCTION FOR 'motion_desc']
        The 'motion_desc' field is the DIRECT PROMPT for the AI Video Generator (Wan 2.1).
        It MUST be highly detailed, creative, and written in ENGLISH.
        
        DO NOT use generic terms like "moving", "animated", or "talking".
        Instead, use "cinematic vocabulary" to describe:
        1. **Micro-Motions**: "Subtle eye trembling", "Hair gently swaying in wind", "Fists clenching", "Tears welling up", "Chest heaving with breath".
        2. **Camera Movement**: "Slow dolly zoom", "Handheld camera shake", "Low angle tilt up", "Rapid crash zoom", "Smooth tracking shot".
        3. **Atmosphere & Lighting**: "Dust particles floating in god rays", "Flickering neon lights in background", "Dark ominous shadows stretching", "Sparks flying from fire".
        4. **Action**: "Explosive debris flying", "Sword slashing with motion blur", "Magic energy swirling spirally".

        [SCENE ANALYSIS GUIDELINES]
        - **Contextual Inference**: If the dialogue is angry, add "Camera shaking, intense red lighting, joyful sparks". If sad, "Slow rain falling, gloomy blue filter".
        - **Vertical Images**: IF the image is vertical (portrait), you MUST use 'pan_down' or 'pan_up' to reveal the full content.
        - **Static Dialogue**: IF the scene is just talking, add "Subtle breathing motion, blinking eyes, natural head movement" to keep it alive.
        - **Audio Direction**: Suggest immersive Sound Effects (SFX) and Background Music (BGM) that match the visual intensity. 
          sfx_prompt should include specific sounds (e.g., "Heavy footsteps on metal").
          bgm_mood should describe the tone (e.g., "Tense orchestral").
          **CRITICAL**: For 'sfx_prompt' or 'bgm_mood', NEVER return "None" or "null". If silent, use "Silence".
        - **Voice Recommendations (CONSISTENCY IS LAW)**: 
          - **NEVER** use "Silence" or "None" as a voice_name. 
          - The SAME character MUST use the EXACT SAME voice name in every scene they appear.
          - DO NOT mix voices for the same person (e.g., No switching between Adam and Josh).
          - **NARRATOR (내레이션)**: ALWAYS use "Brian".

        [OUTPUT FORMAT (JSON ONLY)]
        {{
            "overall_strategy": "Overall direction summary (Korean)",
            "bgm_style": "Recommended BGM style (Korean)",
            "character_plan": [ ... ],
            "scene_plans": [
                {{
                    "scene_number": 1,
                    "engine": "image" | "wan" | "akool",
                    "effect": "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "tilt_up" | "tilt_down" | "pan_down" | "pan_up" | "static" | "shake",
                    "motion_desc": "HIGHLY DETAILED ENGLISH PROMPT. (e.g., 'Cinematic extreme close-up of eye, pupil dilating, intense fear, camera slowly zooming in, dark moody lighting')",
                    "rationale": "Reason for direction (Korean). Focus on emotional impact.",
                    "sfx_priority": "High" | "Normal",
                    "cropping_advice": "Composition advice (Korean)",
                    "voice_name": "ElevenLabs Voice Name (e.g. Rachel, Adam, Josh, Dorothy, Nicole, Fin)",
                    "audio_direction": {{
                        "sfx_prompt": "Detailed English SFX prompt for ElevenLabs generation (e.g. 'Swords clashing with sparks, metallic ringing')",
                        "bgm_mood": "Mood description for BGM (e.g. 'Epic battle orchestral, fast pace')" 
                    }}
                }}
            ]
        }}
        """
        
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
            return {{ "overall_strategy": "Plan parsing failed", "raw": text }}
        except Exception as e:
            print(f"Plan Generation Error: {e}")
            return {{ "overall_strategy": f"Error: {str(e)}" }}

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

# 싱글톤 인스턴스
gemini_service = GeminiService()
