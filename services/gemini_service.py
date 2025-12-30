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

        prompt = f"""당신은 유튜브 콘텐츠 분석 전문가입니다.
아래 영상의 댓글{('과 스크립트' if transcript else '')}를 분석해주세요.

[영상 제목]
{video_title}
{script_section}
[댓글 목록]
{chr(10).join(comments[:50])}

다음 JSON 형식으로 반환해주세요:
{{
    "sentiment": {{
        "positive": 비율,
        "negative": 비율,
        "neutral": 비율
    }},
    "main_topics": ["주요 토픽 1", "주요 토픽 2", ...],
    "viewer_needs": ["시청자 니즈 1", "시청자 니즈 2", ...],
    "content_suggestions": ["콘텐츠 제안 1", "콘텐츠 제안 2", ...],
    "script_analysis": {{
        "structure": "서론-본론-결론 구조 요약",
        "hooks": "초반 몰입을 유도한 요소 (Hooks)",
        "pacing": "영상 전개 속도 및 톤앤매너",
        "key_message": "영상이 전달하고자 하는 핵심 메시지"
    }},
    "summary": "전체 요약 (2-3문장)"
}}

JSON만 반환하세요."""

        text = await self.generate_text(prompt, temperature=0.3)

        # JSON 파싱
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "파싱 실패", "raw": text}

    async def generate_script_structure(self, analysis_data: dict, recent_titles: List[str] = None, target_language: str = "ko") -> dict:
        """분석 데이터를 기반으로 대본 구조 자동 생성"""
        
        analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        
        history_instruction = ""
        if recent_titles:
            history_list = "\n".join([f"- {t}" for t in recent_titles])
            history_instruction = f"""
[중복 방지 주의사항]
최근에 다음과 같은 주제의 영상들이 제작되었습니다:
{history_list}

**위 영상들과는 겹치지 않는 새로운 관점(Angle)이나 소재를 반드시 선택해주세요.**
비슷한 주제라도 전혀 다른 접근 방식이나 에피소드를 다뤄야 합니다.
"""

        # [NEW] 언어/문화적 맥락 설정
        context_instruction = ""
        if target_language == "ja":
            context_instruction = """
[Cultural Context: JAPAN]
- The content must be tailored to a Japanese audience.
- Use Japanese examples, geographical locations (e.g., Tokyo, Osaka, Hokkaido), and cultural references.
- DO NOT use Korean examples (e.g., Seoul, Kimchi, K-Pop) unless the topic specifically requests it.
- Although the output structure must be written in Korean (for the user), the **content itself** must describe a Japanese context.
"""
        elif target_language == "en":
            context_instruction = """
[Cultural Context: GLOBAL/USA]
- The content must be tailored to a Global or US audience.
- Use international examples and cultural references.
- Although the output structure must be written in Korean (for the user), the **content itself** must describe a Global/US context.
"""
        elif target_language == "es":
             context_instruction = """
[Cultural Context: Spanish/Latin America]
- The content must be tailored to a Spanish-speaking audience.
- Use relevant cultural references.
- Although the output structure must be written in Korean (for the user), the **content itself** must describe a Spanish/Latin context.
"""

        prompt = f"""당신은 유튜브 콘텐츠 기획 전문가입니다.
아래의 분석 데이터를 바탕으로 가장 효과적인 영상 대본 구조를 기획해주세요.

[분석 데이터]
{analysis_json}

[충돌 방지 및 언어 지침]
최근 제작된 영상들과 겹치지 않는 새로운 관점(Angle)이나 소재를 선택하세요.
**반드시 한국어로 대본 구조를 작성해주세요.** (분석 데이터가 다른 언어여도 기획안은 한국어로 작성하여 사용자가 이해하기 쉽게 하세요)

**[중요] 문화적 맥락(Context) 지침:**
{context_instruction}
- 만약 타겟 언어가 일본어라면, 퀴즈나 예시도 '일본'과 관련된 것이어야 합니다. (한국x)
- 예: '지리 퀴즈'라면 '대한민국 수도'가 아니라 '일본 도도부현' 문제가 나와야 합니다.

**[중요] 분석 데이터에 명시된 'duration_category'를 반드시 준수하세요.**
- 만약 60분(3600초) 등 긴 영상이라면, 그 길이에 맞게 충분히 많은 섹션과 상세한 내용을 기획해야 합니다.
- 예상 길이를 임의로 줄이지 마세요.
{history_instruction}

다음 JSON 형식으로 기획안을 작성해주세요:
{{
    "hook": "영상 시작 5초 안에 시청자를 사로잡을 강렬한 멘트",
    "sections": [
        {{
            "title": "서론",
            "key_points": ["다룰 내용 1", "다룰 내용 2"]
        }},
        {{
            "title": "본론 1 (핵심 내용)",
            "key_points": ["상세 설명 1", "상세 설명 2"]
        }},
        {{
            "title": "본론 2 (반전/심화)",
            "key_points": ["..."]
        }},
        {{
            "title": "결론",
            "key_points": ["요약 및 제언"]
        }}
    ],
    "cta": "구독과 좋아요를 유도하는 자연스러운 멘트",
    "style": "영상 분위기 (예: 정보전달/유머러스/감동적)",
    "duration": 예상영상길이(초, 숫자만)
}}

JSON만 반환하세요."""

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

        prompt = f"""
        Act as a YouTube Trend Analyst and SEO Expert.
        Generate a list of 20-30 trending search keywords/topics on YouTube.
        
        **Target Audience & Context:**
        - Region/Language: {lang_name}
        - Time Period: {period_text}
        - Target Age Group: {age_text}

        Focus on broad, high-traffic topics relevant to this specific demographic and time.

        Assign a 'volume' score (Search Volume Index) from 1 to 100 for each keyword.
        **CRITICAL: Use a 'Power Law' distribution for volume scores.**
        - Only 1-2 keywords should have 95-100 (Viral).
        - 3-5 keywords should have 70-90.
        - The majority should be between 20-60.
        - Use this variance to make the bubble chart interesting.

        The keywords must be in the TARGET LANGUAGE ({language}).
        
        Format as JSON list:
        [
            {{"keyword": "Keyword in Target Language", "translation": "MEANING IN KOREAN (ONLY HANGUL - VERY IMPORTANT)", "volume": 98, "category": "Gaming"}},
            ...
        ]

        Example for Spanish (es):
        {{"keyword": "Eurocopa 2024", "translation": "유로 2024", "volume": 95, "category": "Sports"}}
        
        RETURN ONLY JSON.
        """
        
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
        """대본을 분석하여 장면별 이미지 프롬프트 생성"""
        
        # 5~8초마다 이미지 1장 생성하도록 계산
        num_scenes = max(3, duration_seconds // 6)
        
        style_instruction = ""
        if style_prompt:
            style_instruction = f"""
[스타일 지침 - 매우 중요]
모든 이미지 프롬프트에 다음 스타일을 반드시 반영하세요:
"{style_prompt}"

모든 prompt_en의 시작 부분에 이 스타일 키워드를 포함시켜야 합니다.
예: "{style_prompt}, ..."
"""

        # 10분(약 3000자) 이후 단일 이미지 처리 로직
        limit_instruction = ""
        if len(script) > 3000:
            limit_instruction = """
[중요: 10분 이후 단일 이미지 정책]
대본이 매우 깁니다(10분 이상). 시청자의 피로도를 줄이기 위해 다음과 같이 작성하세요:
1. **초반 10분 분량(대본의 앞부분 약 3,000자)**: 기존대로 장면별로 상세하고 다양한 이미지 프롬프트를 작성하세요.
2. **그 이후 나머지 분량**: 장면을 나누되, **모든 장면의 'prompt_en'을 'A consistent background image representing the main theme: [Your Theme Description]' 형태의 동일한 프롬프트로 통일하세요.**
   - 즉, 10분 이후의 모든 장면은 똑같은 이미지가 계속 보이도록 해야 합니다.
"""

        prompt = f"""당신은 유튜브 영상 연출 전문가입니다.
아래 대본을 {num_scenes}개의 장면(Scene)으로 나누고, 각 장면에 어울리는 이미지 프롬프트를 작성해주세요.

[대본]
{script}

{style_instruction}
{limit_instruction}

다음 JSON 형식으로 출력해주세요:
{{
    "scenes": [
        {{
            "scene_number": 1,
            "scene_text": "해당 장면에서 나오는 대본의 일부",
            "prompt_ko": "이미지 묘사 (한글)",
            "prompt_en": "{style_prompt or 'High quality, photorealistic'}, (영어 묘사)"
        }},
        ...
    ]
}}

- 이미지는 16:9 비율(가로형)에 적합해야 합니다.
- 텍스트가 없는 이미지를 묘사해주세요.
- JSON만 반환하세요.
"""

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
        return []

# 싱글톤 인스턴스
gemini_service = GeminiService()
