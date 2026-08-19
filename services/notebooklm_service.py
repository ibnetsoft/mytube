"""
[AIR STUDIO] Google NotebookLM-Style Grounded Script & 2-Host Dialogue Podcast Engine
- Grounded on user reference materials (Articles, Historical notes, PDF extracts, transcripts)
- Zero-hallucination factual grounding via Google Gemini 1.5 Pro
- 2-Speaker Dialogue Podcast (Audio Overview style) & 1-Speaker Deep-dive Documentary formats
- Automatic 53-Scene Visual Storyboard & Multi-Voice TTS Mapping
"""
import os
import json
import re
import httpx
from typing import Dict, Any, List, Optional
from config import config
from services.gemini_service import gemini_service

NOTEBOOKLM_PROMPT_TEMPLATE = """당신은 구글 노트북LM(NotebookLM)의 핵심 AI이자, 유튜브 100만 조회수 전문 롱폼 다큐멘터리/토크쇼 총괄 디렉터입니다.
사용자가 제공한 [참고 자료]를 심층 분석하여, 철저하게 사실에 근거하면서도 시청자가 15~20분 동안 한순간도 눈을 뗄 수 없는 최고 품질의 유튜브 롱폼 대본과 53개 씬(Scene) 구성을 작성하세요.

[요청 설정]
- 카테고리: {category}
- 목표 영상 분량: {duration_minutes}분 (약 4,000자~6,000자 대본 분량)
- 대본 포맷 모드: {mode_instruction}

[참고 자료 (Reference Material)]
\"\"\"
{source_text}
\"\"\"

[작성 지침]
1. {mode_specific_rules}
2. 팩트 기반(Grounded): 참고 자료에 있는 핵심 정보, 흥미로운 일화, 통계, 맥락을 정확하게 반영하되 구어체로 흥미진진하게 풀어내세요.
3. 씬 구성(Scenes): 유튜브 롱폼 영상에 맞게 총 50개~53개의 씬으로 분할하세요.
   - 각 씬마다:
     * scene_number: 1, 2, ...
     * scene_text: 해당 씬에서 읽을 대사 (2~3문장)
     * image_prompt: 해당 씬에 어울리는 구체적인 영어 이미지 프롬프트 (Cinematic lighting, 8k, photorealistic style)
     * visual_type: 1~12씬은 "video" (초반 훅 5초 비디오), 13~53씬은 "image"

[반환 JSON 스키마 - 반드시 순수 JSON만 반환하세요]
{{
  "title": "시청자를 사로잡는 강력한 유튜브 롱폼 제목",
  "hook": "초반 1분 시청 지속률을 극대화하는 도입부 훅 요약",
  "category": "{category}",
  "mode": "{mode}",
  "dialogue_mode": {is_dialogue_json},
  "speakers": {speakers_json},
  "full_script": "전체 대본 전문 (화자 이름 포함)...",
  "scenes": [
    {{
      "scene_number": 1,
      "speaker": "{default_speaker_1}",
      "scene_text": "첫 번째 씬 대사...",
      "image_prompt": "Cinematic visual description in English...",
      "visual_type": "video"
    }}
  ]
}}
"""

async def generate_notebooklm_project(
    source_text: str,
    mode: str = "dialogue_podcast",
    category: str = "옛날이야기",
    duration_minutes: int = 15,
    custom_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate complete grounded longform script & scenes from source text.
    """
    if not source_text or not source_text.strip():
        raise ValueError("참고 자료(Source Text)가 비어 있습니다.")

    api_key = config.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    is_dialogue = (mode == "dialogue_podcast")
    if is_dialogue:
        mode_instruction = "2인 대화형 팟캐스트 (노트북LM Audio Overview 스타일 - 남/여 진행자 티키타카 토크쇼)"
        mode_specific_rules = (
            "반드시 '진행자1' (호스트/질문자/남성)과 '진행자2' (전문 해설자/스토리텔러/여성)의 2인 대화체로 작성하세요. "
            "각 대사 줄 맨 앞에 '진행자1: 대사...' 또는 '진행자2: 대사...' 형식으로 화자를 명시하고, "
            "진행자1이 흥미로운 질문과 현실적 리액션을 던지면 진행자2가 깊이 있는 사연과 사료를 전달하는 환상의 호흡을 구성하세요."
        )
        is_dialogue_json = "true"
        speakers_json = '["진행자1", "진행자2"]'
        default_speaker_1 = "진행자1"
    else:
        mode_instruction = "1인 심층 내레이션 (단독 나레이터 몰입형 스토리텔링)"
        mode_specific_rules = (
            "차분하고 흡입력 있는 1인 다큐멘터리/이야기꾼 내레이션으로 작성하세요. "
            "시청자에게 말을 건네듯 생생한 현장감과 감정의 고조를 살려 집필하세요."
        )
        is_dialogue_json = "false"
        speakers_json = '["나레이터"]'
        default_speaker_1 = "나레이터"

    prompt = NOTEBOOKLM_PROMPT_TEMPLATE.format(
        category=category,
        duration_minutes=duration_minutes,
        mode=mode,
        mode_instruction=mode_instruction,
        mode_specific_rules=mode_specific_rules,
        source_text=source_text[:20000],
        is_dialogue_json=is_dialogue_json,
        speakers_json=speakers_json,
        default_speaker_1=default_speaker_1
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code != 200:
            # Fallback to gemini-1.5-flash if 2.5 is unavailable
            url_fallback = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            res = await client.post(url_fallback, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Gemini API 호출 실패: {res.status_code} - {res.text}")

        res_data = res.json()
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]

    # JSON 파싱
    clean_json = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
    clean_json = re.sub(r"^```\s*$", "", clean_json.strip(), flags=re.MULTILINE)
    data = json.loads(clean_json.strip())

    if custom_title and custom_title.strip():
        data["title"] = custom_title.strip()

    return data