from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional
import database as db
from app.models.channel import ChannelCreate, ChannelResponse

router = APIRouter(prefix="/api/channels", tags=["Channels"])

@router.get("", response_model=List[ChannelResponse])
async def list_channels():
    try:
        channels = db.get_all_channels()
        return channels
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("", response_model=int)
async def create_channel(data: ChannelCreate):
    try:
        channel_id = db.create_channel(data.name, data.handle, data.description)
        return channel_id
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/{channel_id}")
async def delete_channel_api(channel_id: int):
    try:
        db.delete_channel(channel_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{channel_id}/authenticate")
async def save_credentials(channel_id: int, credentials: dict = Body(...)):
    """[NEW] Authenticate channel and save credentials path"""
    try:
        # credentials는 json string으로 오거나 dict로 올 수 있음
        import json
        creds_json = json.dumps(credentials)
        # 실제로는 여기서 토큰을 검증하거나 파일로 저장하는 로직이 들어갈 수 있음
        # 현재는 DB에 정보만 저장하는 것으로 가정 (실제 구현에 맞게 조정 필요)
        db.update_channel_credentials(channel_id, "path/to/credentials.json")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{channel_id}/login")
async def login_channel_api(channel_id: int):
    """실제 브라우저를 띄워 채널 인증 (OAuth Flow)"""
    try:
        from services.youtube_upload_service import youtube_upload_service
        import database as db
        import os
        
        channel = db.get_channel(channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
            
        # 토큰 파일 경로 결정 (tokens/token_1.pickle 등)
        from config import config
        token_dir = "tokens"  # 상대 경로 사용
        abs_token_dir = os.path.join(config.BASE_DIR, token_dir)
        os.makedirs(abs_token_dir, exist_ok=True)
        
        # 파일명 일관성 유지 (token_{id}.pickle)
        token_filename = f"token_{channel_id}.pickle"
        abs_token_path = os.path.join(abs_token_dir, token_filename)
        rel_token_path = os.path.join(token_dir, token_filename)
        
        # 1. 인증 프로세스 실행 (interactive=True 이므로 브라우저 오픈)
        youtube_upload_service.get_authenticated_service(token_path=abs_token_path, interactive=True)
        
        # 2. 성공 시 DB에 상대 경로 저장 (폴더 이동에 유연하게 대응)
        db.update_channel_credentials(channel_id, rel_token_path)
        
        return {"status": "ok", "message": f"'{channel['name']}' 채널 인증이 성공적으로 완료되었습니다."}
    except Exception as e:
        print(f"Login Error: {e}")
        return {"status": "error", "error": str(e)}

