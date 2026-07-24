import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from services.web_admin_client import web_admin_client
from services.gemini_service import gemini_service

router = APIRouter(prefix="/api/voices", tags=["Voices"])

class RecommendRequest(BaseModel):
    language: str
    gender: Optional[str] = None
    age_group: Optional[str] = None
    tone: Optional[str] = None
    genre: Optional[str] = None

@router.post("/recommend")
def recommend_voices(req: RecommendRequest):
    # Fetch all active voices
    resp = web_admin_client.supabase_get('voice_profiles', params={'is_active': 'eq.true'})
    if resp is None or resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to fetch voice profiles from database")
    
    voices = resp.json()
    if not voices:
        return {"voices": []}
        
    scored_voices = []
    
    for voice in voices:
        score = 0
        reasons = []
        
        # 1. Language Match (+40)
        if voice.get('language') and req.language and voice.get('language').lower() == req.language.lower():
            score += 40
            reasons.append("language")
            
        # 2. Gender Match (+20)
        if voice.get('gender') and req.gender and voice.get('gender').lower() == req.gender.lower():
            score += 20
            reasons.append("gender")
            
        # 3. Age Group Match (+15)
        if voice.get('age_group') and req.age_group and voice.get('age_group').lower() == req.age_group.lower():
            score += 15
            reasons.append("age_group")
            
        # 4. Tone Match (+10)
        if voice.get('tone') and req.tone and voice.get('tone').lower() == req.tone.lower():
            score += 10
            reasons.append("tone")
            
        # 5. Genre Match (+15)
        recommended_genres = voice.get('recommended_genres') or []
        if req.genre and recommended_genres:
            if any(req.genre.lower() == g.lower() for g in recommended_genres):
                score += 15
                reasons.append("genre")
                
        if reasons:
            if len(reasons) > 1:
                reason_str = "Matched " + ", ".join(reasons[:-1]) + " and " + reasons[-1] + "."
            else:
                reason_str = "Matched " + reasons[0] + "."
        else:
            reason_str = "No specific match."
            
        scored_voices.append({
            "id": voice.get("id"),
            "voice_name": voice.get("voice_name"),
            "provider": voice.get("provider"),
            "provider_voice_id": voice.get("provider_voice_id"),
            "score": score,
            "matched": reasons,
            "reason": reason_str
        })
        
    # Sort by score descending
    scored_voices.sort(key=lambda x: x["score"], reverse=True)
    
    # Return Top 5
    top_5 = scored_voices[:5]

    return {"voices": top_5}


class InferCharactersRequest(BaseModel):
    script: str
    language: Optional[str] = "ko"
    characters: Optional[List[str]] = None


@router.post("/infer-characters")
async def infer_characters(req: InferCharactersRequest):
    """대본 문맥을 바탕으로 각 화자(등장인물)의 성별/연령대를 AI로 추론.
    멀티보이스 자동 배정이 이름 순서가 아니라 실제 성별에 맞는 목소리를 고르도록 하기 위함."""
    script_excerpt = (req.script or "")[:6000]
    names_hint = ""
    if req.characters:
        names_hint = "이미 감지된 화자 이름 목록(참고용, 이 목록에 있는 이름을 우선 사용): " + ", ".join(req.characters)

    prompt = f"""다음 대본에 등장하는 화자(내레이터 포함)의 성별과 연령대를 추론하세요.
이름/호칭(예: 할머니, 아빠, 민수)뿐 아니라 대사 내용과 문맥도 함께 고려하세요.

{names_hint}

대본:
{script_excerpt}

각 화자에 대해 아래 JSON 스키마로만 응답하세요 (마크다운 없이 순수 JSON):
{{
  "characters": [
    {{
      "name": "화자 이름 또는 호칭 (대본에 등장하는 표기 그대로)",
      "gender": "male, female 중 하나 (판단 불가 시 male)",
      "age_group": "child, young, adult, senior 중 하나"
    }}
  ]
}}"""

    try:
        response_text = await gemini_service.generate_text(
            prompt=prompt,
            temperature=0.1,
            task_type="voice_gender_infer",
            json_mode=True
        )
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        data = json.loads(response_text.strip())
        return {"characters": data.get("characters", [])}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Character gender inference failed: {e}")
