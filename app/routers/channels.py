from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional
import database as db
from app.models.channel import ChannelCreate, ChannelResponse

router = APIRouter(prefix="/api/channels", tags=["Channels"])

@router.get("", response_model=List[ChannelResponse])
async def list_channels():
    try:
        channels = db.get_channels()
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
