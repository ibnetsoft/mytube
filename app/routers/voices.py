from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from services.web_admin_client import web_admin_client

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
