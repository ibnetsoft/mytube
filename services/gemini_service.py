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
        url = f"{self.base_url}/models/imagen-3.0-generate-002:predict?key={self.api_key}"

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": num_images,
                "aspectRatio": aspect_ratio
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
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9"
    ) -> Optional[bytes]:
        """영상 생성 (Veo)"""
        # Veo API는 Vertex AI 또는 별도 엔드포인트 필요
        # 현재는 placeholder
        raise NotImplementedError("Veo API는 추가 설정이 필요합니다")

    async def analyze_comments(self, comments: List[str], video_title: str) -> dict:
        """댓글 분석"""
        prompt = f"""당신은 유튜브 콘텐츠 분석 전문가입니다.
아래 영상의 댓글들을 분석해주세요.

[영상 제목]
{video_title}

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

    async def generate_script_structure(self, analysis_data: dict) -> dict:
        """분석 데이터를 기반으로 대본 구조 자동 생성"""
        
        analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        
        prompt = f"""당신은 유튜브 콘텐츠 기획 전문가입니다.
아래의 분석 데이터를 바탕으로 가장 효과적인 영상 대본 구조를 기획해주세요.

[분석 데이터]
{analysis_json}

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
    "duration": 예상영상길이(초)
}}

JSON만 반환하세요."""

        text = await self.generate_text(prompt, temperature=0.5)

        # JSON 파싱
        import re

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        return {"error": "구조 생성 실패", "raw": text}


    async def generate_image_prompts_from_script(self, script: str, duration_seconds: int) -> List[dict]:
        """대본을 분석하여 장면별 이미지 프롬프트 생성"""
        
        # 5~8초마다 이미지 1장 생성하도록 계산
        num_scenes = max(3, duration_seconds // 6)
        
        prompt = f"""당신은 유튜브 영상 연출 전문가입니다.
아래 대본을 {num_scenes}개의 장면(Scene)으로 나누고, 각 장면에 어울리는 이미지 프롬프트를 작성해주세요.

[대본]
{script}

다음 JSON 형식으로 출력해주세요:
{{
    "scenes": [
        {{
            "scene_number": 1,
            "scene_text": "해당 장면에서 나오는 대본의 일부",
            "prompt_ko": "이미지 묘사 (한글)",
            "prompt_en": "High quality, photorealistic, cinematic lighting, 4k, (영어 묘사)"
        }},
        ...
    ]
}}

- 이미지는 유튜브 쇼츠 스타일에 맞는 세로 비율(9:16)에 적합해야 합니다.
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
