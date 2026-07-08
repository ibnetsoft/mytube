from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body, Path, BackgroundTasks
from pydantic import BaseModel
import datetime

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client
from app.routers.admin_tenant import require_superadmin
from app.services.voice_analyzer import analyze_voice_task

router = APIRouter(prefix="/api/admin/voices", tags=["Admin-Voices"])

def _supabase_get(table: str, **params):
    clean = {k: v for k, v in params.items() if v is not None}
    resp = web_admin_client.supabase_get(table, params=clean)
    if resp is None:
        raise HTTPException(status_code=503, detail="Supabase unreachable.")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase error on '{table}': {resp.text[:300]}"
        )
    return resp.json()

def _supabase_post(table: str, payload: dict):
    resp = web_admin_client.supabase_post(table, payload)
    if resp is None:
        raise HTTPException(status_code=503, detail="Supabase unreachable.")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase post error on '{table}': {resp.text[:300]}"
        )
    # Return JSON if possible, else just success
    try:
        return resp.json()
    except:
        return {"success": True}

def _supabase_patch(table: str, payload: dict, **params):
    resp = web_admin_client.supabase_patch(table, payload, params=params)
    if resp is None:
        raise HTTPException(status_code=503, detail="Supabase unreachable.")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase patch error on '{table}': {resp.text[:300]}"
        )
    try:
        return resp.json()
    except:
        return {"success": True}


@router.get("")
def list_voices(
    provider: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    gender: Optional[str] = Query(None),
    age_group: Optional[str] = Query(None),
    analysis_status: Optional[str] = Query(None),
    include_inactive: bool = Query(False)
):
    require_superadmin()
    
    params = {
        'order': 'created_at.desc'
    }
    
    if not include_inactive:
        params['is_active'] = 'eq.true'
        
    if provider: params['provider'] = f'eq.{provider}'
    if language: params['language'] = f'eq.{language}'
    if gender: params['gender'] = f'eq.{gender}'
    if age_group: params['age_group'] = f'eq.{age_group}'
    if analysis_status: params['analysis_status'] = f'eq.{analysis_status}'
        
    voices = _supabase_get('voice_profiles', **params)
    return {"success": True, "data": voices}


@router.get("/{id}")
def get_voice(id: str):
    require_superadmin()
    voices = _supabase_get('voice_profiles', id=f'eq.{id}')
    if not voices:
        raise HTTPException(404, "Voice not found")
    return {"success": True, "data": voices[0]}


class VoiceCreatePayload(BaseModel):
    provider: str = "elevenlabs"
    provider_voice_id: str
    voice_name: str
    language: str
    gender: Optional[str] = None
    age_group: Optional[str] = None
    tone: Optional[str] = None
    pitch: Optional[str] = None
    speed: Optional[str] = None
    energy: Optional[str] = None
    warmth: Optional[int] = None
    clarity: Optional[int] = None
    emotion_range: Optional[int] = None
    recommended_genres: Optional[list] = None
    avoid_genres: Optional[list] = None
    sample_audio_url: Optional[str] = ""
    sample_duration: Optional[float] = None
    sample_language: Optional[str] = None
    sample_hash: Optional[str] = None
    voice_traits: Optional[dict] = None
    description: Optional[str] = ""
    analysis_status: str = "manual"

@router.post("")
def create_voice(payload: VoiceCreatePayload, background_tasks: BackgroundTasks):
    require_superadmin()
    
    data = payload.dict(exclude_unset=True)
    data['is_active'] = True
    
    result = _supabase_post('voice_profiles', data)
    
    # Check if we need to trigger analyzer
    created_voice = result.get('data', result) if isinstance(result, dict) else result
    if isinstance(created_voice, list) and created_voice:
        created_voice = created_voice[0]
        
    if isinstance(created_voice, dict):
        vid = created_voice.get('id')
        status = created_voice.get('analysis_status')
        audio_url = created_voice.get('sample_audio_url')
        
        if vid and audio_url and status == 'pending':
            background_tasks.add_task(analyze_voice_task, vid, audio_url)

    return {"success": True, "data": result}


class VoiceUpdatePayload(BaseModel):
    provider: Optional[str] = None
    provider_voice_id: Optional[str] = None
    voice_name: Optional[str] = None
    language: Optional[str] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    tone: Optional[str] = None
    pitch: Optional[str] = None
    speed: Optional[str] = None
    energy: Optional[str] = None
    warmth: Optional[int] = None
    clarity: Optional[int] = None
    emotion_range: Optional[int] = None
    recommended_genres: Optional[list] = None
    avoid_genres: Optional[list] = None
    sample_audio_url: Optional[str] = None
    sample_duration: Optional[float] = None
    sample_language: Optional[str] = None
    sample_hash: Optional[str] = None
    voice_traits: Optional[dict] = None
    description: Optional[str] = None
    analysis_status: Optional[str] = None
    is_active: Optional[bool] = None

@router.patch("/{id}")
def update_voice(id: str, payload: VoiceUpdatePayload, background_tasks: BackgroundTasks):
    require_superadmin()
    
    data = payload.dict(exclude_unset=True)
    if not data:
        return {"success": True, "message": "No fields to update"}
        
    data['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    result = _supabase_patch('voice_profiles', data, id=f'eq.{id}')
    
    # Check if we need to trigger analyzer
    updated_voice = result.get('data', result) if isinstance(result, dict) else result
    if isinstance(updated_voice, list) and updated_voice:
        updated_voice = updated_voice[0]
        
    if isinstance(updated_voice, dict):
        status = updated_voice.get('analysis_status')
        audio_url = updated_voice.get('sample_audio_url')
        
        if audio_url and status == 'pending':
            background_tasks.add_task(analyze_voice_task, id, audio_url)

    return {"success": True, "data": result}


@router.delete("/{id}")
def delete_voice(id: str):
    require_superadmin()
    
    # Soft delete
    data = {
        'is_active': False,
        'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    result = _supabase_patch('voice_profiles', data, id=f'eq.{id}')
    return {"success": True, "data": result}
