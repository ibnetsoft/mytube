"""
Announcements Board API — FastAPI router

웹어드민이 전체 유저에게 발행한 공지사항 게시판을 조회하는 라우터.
쪽지(1:1)가 아니라 게시판(1:N)이라 개인화된 데이터가 없다 - 로그인
직원이면 누구나 같은 목록을 본다. support.py와 동일하게 실제 데이터
접근은 전혀 하지 않고 auth-web의 /api/desktop-announcements를 경유한다.
"""
from fastapi import APIRouter, HTTPException

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/user/announcements", tags=["announcements"])


# ---------------------------------------------------------------------------
# GET /api/user/announcements/list
# ---------------------------------------------------------------------------
@router.get("/list")
def list_announcements():
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized: No logged-in user email.")
    session_token = auth_service.get_session_token()
    if not session_token:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    result = web_admin_client.desktop_announcements(email, session_token)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "공지사항 서버 오류")
    return result
