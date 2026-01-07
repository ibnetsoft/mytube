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
        self.api_key = config.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

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

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        num_images: int = 1
    ) -> List[bytes]:
        """이미지 생성 (Imagen 3)"""
        url = f"{self.base_url}/models/imagen-4.0-generate-001:predict?key={self.api_key}"
        print(f"DEBUG: Image Gen URL: {url}") # DEBUGGING

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": num_images,
                "aspectRatio": aspect_ratio,
                "safetySetting": "block_low_and_above"
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()

            images = []
            if "predictions" in result:
                for pred in result["predictions"]:
                    if "bytesBase64Encoded" in pred:
                        img_bytes = base64.b64decode(pred["bytesBase64Encoded"])
                        images.append(img_bytes)

            return images

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
        
        # [NEW] 목표 길이에 따른 최소 섹션 수 계산
        duration_seconds = analysis_data.get('duration', 60)
        if isinstance(analysis_data.get('duration_category'), str):
            try:
                duration_seconds = int(re.search(r'\d+', analysis_data['duration_category']).group())
            except: pass
        
        min_sections = 4
        if duration_seconds > 300: min_sections = max(8, duration_seconds // 45)
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

    async def generate_trending_keywords(self, language: str = "ko", period: str = "now", age: str = "all") -> list:
        """
        언어/기간/연령별 인기 유튜브 트렌드 키워드 생성 (Search Volume 시뮬레이션)
        """
        lang_name = ""
        if language == "ko": lang_name = "South Korea (Korean)"
        elif language == "ja": lang_name = "Japan (Japanese)"
        elif language == "en": lang_name = "USA/International (English)"
        elif language == "es": lang_name = "Spain/Latin America (Spanish)"
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

    async def generate_image_prompts_from_script(self, script: str, duration_seconds: int, style_prompt: str = None) -> List[dict]:
        """대본을 분석하여 장면별 이미지 프롬프트 생성 (가변 페이싱 적용)"""
        
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
        
        style_instruction = ""
        if style_prompt:
            style_instruction = f"""
[스타일 지침 - 매우 중요]
모든 이미지 프롬프트에 다음 스타일을 반드시 반영하세요:
"{style_prompt}"

모든 prompt_en의 시작 부분에 이 스타일 키워드를 포함시켜야 합니다.
예: "{style_prompt}, ..."
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
            limit_instruction=limit_instruction,
            style_prefix=style_prompt or 'High quality, photorealistic'
        )

        text = await self.generate_text(prompt, temperature=0.7)

        # JSON 파싱
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("scenes", [])
            except:
                pass
                pass
        return []

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
             

             

             
             # Handle case where operation is just a name string or an object
             op_name = None
             if isinstance(operation, str):
                 op_name = operation
                 print(f"DEBUG: Operation started (name only): {op_name}")
                 # Fetch the actual operation object
                 operation = client.operations.get(op_name)
             elif hasattr(operation, 'name'):
                 op_name = operation.name
                 print(f"DEBUG: Operation started: {op_name}")
             else:
                 print(f"DEBUG: Unknown operation type: {type(operation)}")
                 op_name = str(operation)
             
             
             # 2. Poll for completion (Manual)
             # Note: 'operation.result' might be a property returning None if not done, 
             # so we must poll 'operation.done' using client.operations.get()
             import time
             
             while not operation.done:
                 print("Waiting for video generation...")
                 time.sleep(5)
                 # Correct way to refresh operation in google.genai SDK
                 # Signature is get(operation, *, config=...)
                 operation = client.operations.get(operation.name)
                 
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

# 싱글톤 인스턴스
gemini_service = GeminiService()
