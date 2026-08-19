"""
[AIR STUDIO] Google NotebookLM-Style Grounded Script & 2-Host Dialogue Podcast Engine
- Step 1: Google Gemini 1.5 Pro / Flash for Deep Grounding & Fact Extraction (RAG)
- Step 2: Anthropic Claude 3.5 Haiku for Elite Korean Scriptwriting & Scene Breakdown
"""
import os
import json
import re
import httpx
from typing import Dict, Any, List, Optional
from config import config
from services.gemini_service import gemini_service

SCRIPT_WRITER_PROMPT_TEMPLATE = """당신은 최고 시청률의 유튜브 롱폼 다큐멘터리 및 토크쇼 메인 작가(Anthropic Claude)입니다.
구글 노트북LM(Gemini)이 심층 조사하여 정리한 [팩트 연구 브리프]를 바탕으로, 한국어 특유의 흡입력과 몰입감을 극대화한 최고 품질의 유튜브 롱폼 대본과 53개 씬(Scene) 구성을 작성하세요.

[요청 설정]
- 카테고리: {category}
- 목표 영상 분량: {duration_minutes}분 (약 4,000자~6,000자 대본 분량)
- 대본 포맷 모드: {mode_instruction}

[팩트 연구 브리프 (Gemini NotebookLM Grounding Research)]
\"\"\"
{research_summary}
\"\"\"

[원문 참고 자료 발췌]
\"\"\"
{source_text}
\"\"\"

[작성 지침]
1. {mode_specific_rules}
2. 문장력 및 흡입력: 시청자가 15~20분 동안 이탈하지 않도록 문장 끝맺음, 감정의 완급 조절, 생생한 구어체를 적용하세요.
3. 씬 구성(Scenes): 유튜브 롱폼 영상에 맞게 총 50개~53개의 씬으로 분할하세요.
   - 각 씬마다:
     * scene_number: 1, 2, ...
     * speaker: 대사를 말하는 화자 이름 (2인 대화 모드면 "진행자1" 또는 "진행자2", 1인 모드면 "나레이터")
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
    Generate complete grounded longform script & scenes:
    Step 1: Gemini 1.5 Research -> Step 2: Claude 3.5 Haiku Writer
    """
    if not source_text or not source_text.strip():
        raise ValueError("참고 자료(Source Text)가 비어 있습니다.")

    gemini_key = config.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
    claude_key = config.CLAUDE_API_KEY or os.environ.get("CLAUDE_API_KEY")

    if not gemini_key:
        raise ValueError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    # ──────────────────────────────────────────────────────────
    # 🔍 STEP 1: Gemini 1.5 - 심층 팩트 분석 (Research & Grounding)
    # ──────────────────────────────────────────────────────────
    research_prompt = f"""당신은 구글 노트북LM(NotebookLM)의 핵심 연구 분석관입니다.
제공된 [참고 자료]를 꼼꼼히 정독하고, 유튜브 롱폼({duration_minutes}분) 대본 집필에 필요한 핵심 팩트, 인물 관계, 타임라인, 가장 흥미로운 갈등/사연 포인트, 통계/인용구를 팩트 위주로 완벽하게 요약 정리(Research Brief)하세요.

[참고 자료]
\"\"\"
{source_text[:30000]}
\"\"\""""

    research_summary = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r_res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": research_prompt}]}], "generationConfig": {"temperature": 0.2}}
            )
            if r_res.status_code == 200:
                research_summary = r_res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[NotebookLM] Gemini research step error: {e}")

    if not research_summary:
        research_summary = source_text[:5000]

    # ──────────────────────────────────────────────────────────
    # ✍️ STEP 2: Claude 3.5 Haiku - 명품 대본 집필 & 53개 씬 생성 (Writer)
    # ──────────────────────────────────────────────────────────
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

    writer_prompt = SCRIPT_WRITER_PROMPT_TEMPLATE.format(
        category=category,
        duration_minutes=duration_minutes,
        mode=mode,
        mode_instruction=mode_instruction,
        mode_specific_rules=mode_specific_rules,
        research_summary=research_summary,
        source_text=source_text[:15000],
        is_dialogue_json=is_dialogue_json,
        speakers_json=speakers_json,
        default_speaker_1=default_speaker_1
    )

    parsed = None
    if claude_key:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                c_res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type": "application/json", "x-api-key": claude_key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 8192,
                        "temperature": 0.7,
                        "messages": [{"role": "user", "content": writer_prompt}]
                    }
                )
                if c_res.status_code == 200:
                    raw_content = c_res.json()["content"][0]["text"]
                    clean_json = re.sub(r"^```json\s*", "", raw_content.strip(), flags=re.MULTILINE)
                    clean_json = re.sub(r"^```\s*$", "", clean_json.strip(), flags=re.MULTILINE)
                    parsed = json.loads(clean_json.strip())
            except Exception as ce:
                print(f"[NotebookLM] Claude call failed: {ce}")

    if not parsed:
        # Fallback to Gemini 2.5 Flash
        async with httpx.AsyncClient(timeout=120.0) as client:
            g_res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": writer_prompt}]}], "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}}
            )
            if g_res.status_code != 200:
                raise RuntimeError(f"대본 생성 실패: {g_res.status_code}")
            raw = g_res.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean = re.sub(r"^```json\s*", "", raw.strip(), flags=re.MULTILINE)
            clean = re.sub(r"^```\s*$", "", clean.strip(), flags=re.MULTILINE)
            parsed = json.loads(clean.strip())

    if custom_title and custom_title.strip():
        parsed["title"] = custom_title.strip()

    return parsed