"""
User -> Web Admin Support Messages API — FastAPI router

유저(데스크톱 앱)가 웹어드민에 문의를 보내고, 답장을 조회하는 라우터.
referral.py와 동일하게 이 라우터는 실제 데이터 접근을 전혀 하지 않고
auth-web의 /api/desktop-support 브릿지를 경유한다 - 문의/답장 데이터는
Supabase에만 있고, session_token(HMAC) 검증도 서버 측에서 이뤄진다.

AI 1차 초안은 auth-web이 문의 저장 직후 생성하지만, 이 라우터가 받는
list 응답에는 절대 포함되지 않는다 - 사용자에게는 어드민이 확정 발송한
답장만 보인다.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/user/support", tags=["support"])


def _bridge(action: str, params: Optional[dict] = None) -> dict:
    """auth-web 브릿지 호출 공통 처리."""
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized: No logged-in user email.")
    session_token = auth_service.get_session_token()
    if not session_token:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    return web_admin_client.desktop_support(email, session_token, action, params)


def _bridge_or_raise(action: str, params: Optional[dict] = None) -> dict:
    result = _bridge(action, params)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "문의 서버 오류")
    return result


class SupportMessageRequest(BaseModel):
    subject: str = ""
    body: str


# ---------------------------------------------------------------------------
# POST /api/user/support/send
# ---------------------------------------------------------------------------
@router.post("/send")
def send_support_message(req: SupportMessageRequest):
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="문의 내용을 입력해주세요.")
    return _bridge_or_raise("send", {
        "subject": req.subject.strip()[:200],
        "body": req.body.strip(),
    })


# ---------------------------------------------------------------------------
# GET /api/user/support/list
# ---------------------------------------------------------------------------
@router.get("/list")
def list_support_messages():
    return _bridge_or_raise("list")
