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
@router.get("/login-by-info")
@router.post("/login-by-info")
async def login_by_info_api(
    name: Optional[str] = Query(None), 
    id: Optional[str] = Query(None),
    data: Optional[dict] = Body(None)
):
    """채널 정보를 받아 인증 프로세스 시작 (GET/POST 모두 지원)"""
    try:
        from services.youtube_upload_service import youtube_upload_service
        import os
        from config import config
        
        # GET 쿼리 혹은 POST 바디에서 데이터 추출
        channel_name = name or (data.get("name") if data else None)
        channel_id_val = id or (data.get("id") if data else None)
        
        if not channel_name or not channel_id_val:
            return {"status": "error", "error": "채널 이름과 ID가 누락되었습니다."}

        # 1. 로컬 DB 동기화
        existing_channels = db.get_all_channels()
        target_channel = next((c for c in existing_channels if c['handle'] == channel_id_val), None)
        
        if target_channel:
            local_id = target_channel['id']
            db.update_channel(local_id, channel_name, channel_id_val, f"Managed by Admin ({channel_name})")
        else:
            local_id = db.create_channel(channel_name, channel_id_val, f"Managed by Admin ({channel_name})")
            
        print(f"[Auth] Remote Trigger -> Google OAuth for: {channel_name}")

        # 2. 토큰 경로 준비
        token_filename = f"token_{local_id}.pickle"
        abs_token_path = os.path.join(config.BASE_DIR, "tokens", token_filename)
        
        # 3. 인증 실행 (브라우저는 서버가 돌고 있는 로컬 PC에서 열림)
        youtube_upload_service.get_authenticated_service(token_path=abs_token_path, interactive=True)
        
        # 4. 성공 시 경로 저장
        db.update_channel_credentials(local_id, os.path.join("tokens", token_filename))
        
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=f"""
            <html>
                <head>
                    <title>인증 요청 성공</title>
                    <style>
                        body {{ background: #000; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }}
                        .card {{ border: 1px solid #333; padding: 40px; border-radius: 20px; background: #050505; }}
                        h2 {{ color: #4285F4; }}
                        p {{ color: #888; font-size: 14px; line-height: 1.6; }}
                        .btn {{ display: inline-block; margin-top: 20px; padding: 10px 20px; background: #333; color: #fff; text-decoration: none; border-radius: 10px; font-size: 12px; }}
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h2>✅ 인증 요청 완료</h2>
                        <p><b>{channel_name}</b> 채널의 구글 인증창이<br/>서버(PC) 브라우저에서 열렸습니다.</p>
                        <p>PC로 돌아가 로그인을 완료해주세요.</p>
                        <a href="#" onclick="window.close()" class="btn">창 닫기</a>
                    </div>
                </body>
            </html>
        """)
        
    except Exception as e:
        print(f"Login API Error: {e}")
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=f"<html><body style='background:#000;color:red;padding:20px;'><h2>❌ 오류 발생</h2><p>{str(e)}</p></body></html>", status_code=500)

