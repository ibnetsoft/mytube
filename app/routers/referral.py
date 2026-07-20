"""
Referral Dashboard API — FastAPI router

[AIR-0225B Phase 1] 이 라우터의 모든 데이터 접근은 auth-web의
/api/desktop-referrals 브릿지를 경유한다. 원래는 web_admin_client의
service_role 직접 조회(supabase_get/resolve_user_id)를 썼는데, 그 키가
패키징된 데스크톱 앱에서 제거되어(worknote/AIR-0225B-stage0-service-role-
removal-investigation.md) 세팅 페이지의 조직도/수당 내역/USDT 출금 탭이
전부 "User ID could not be resolved"로 죽어 있었다.

응답 형식은 기존과 동일하게 유지한다 - 프론트(templates/pages/settings.html,
referral.html)는 손대지 않았다. 실제 쿼리/집계/출금 잔액 검증 로직은
auth-web/app/api/desktop-referrals/route.ts로 1:1 이식됐다.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/user", tags=["referral"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bridge(action: str, params: Optional[dict] = None) -> dict:
    """auth-web 브릿지 호출 공통 처리."""
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized: No logged-in user email.")
    session_token = auth_service.get_session_token()
    if not session_token:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    return web_admin_client.desktop_referrals(email, session_token, action, params)


def _bridge_or_raise(action: str, params: Optional[dict] = None) -> dict:
    result = _bridge(action, params)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "추천인 서버 오류")
    return result


# ---------------------------------------------------------------------------
# GET /api/user/referrals/dashboard
# ---------------------------------------------------------------------------
@router.get("/referrals/dashboard")
def get_referral_dashboard():
    return _bridge_or_raise("dashboard")


# ---------------------------------------------------------------------------
# GET /api/user/referrals/tree
# ---------------------------------------------------------------------------
@router.get("/referrals/tree")
def get_referral_tree(
    level: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
):
    _level = level if isinstance(level, int) else None
    result = _bridge_or_raise("tree", {"level": _level})

    nodes = result.get("data") or []
    if status and status != "all" and isinstance(status, str):
        result["data"] = [n for n in nodes if n.get("status") == status]
    return result


# ---------------------------------------------------------------------------
# GET /api/user/commissions/timeline
# ---------------------------------------------------------------------------
@router.get("/commissions/timeline")
def get_commission_timeline(
    page: int = Query(1),
    limit: int = Query(10),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: str = Query('created_at'),
    sort_dir: str = Query('desc'),
):
    return _bridge_or_raise("timeline", {
        "page": page if isinstance(page, int) else 1,
        "limit": limit if isinstance(limit, int) else 10,
        "type": type if isinstance(type, str) else None,
        "status": status if isinstance(status, str) else None,
        "sort_by": sort_by if isinstance(sort_by, str) else "created_at",
        "sort_dir": sort_dir if isinstance(sort_dir, str) else "desc",
    })


# ---------------------------------------------------------------------------
# GET /api/user/referrals/withdrawal-info
# ---------------------------------------------------------------------------
@router.get("/referrals/withdrawal-info")
def get_referral_withdrawal_info():
    return _bridge_or_raise("withdrawal_info")


from pydantic import BaseModel
class ReferralWithdrawalRequest(BaseModel):
    amount: float
    dest_address: str


# ---------------------------------------------------------------------------
# POST /api/user/referrals/withdraw
# ---------------------------------------------------------------------------
@router.post("/referrals/withdraw")
def request_referral_withdrawal(req: ReferralWithdrawalRequest):
    # 잔액/최소금액 검증은 이제 서버(auth-web)가 수행한다 - 변조된 클라이언트가
    # 검증을 건너뛰고 DB에 직접 쓰던 구멍이 이 이전으로 함께 막혔다. 검증 실패
    # 메시지는 success:False 응답으로 그대로 프론트에 전달한다 (기존 UX 유지).
    return _bridge("withdraw", {
        "amount": float(req.amount),
        "dest_address": req.dest_address.strip(),
    })


# ---------------------------------------------------------------------------
# GET /api/user/referrals/withdrawal-history
# ---------------------------------------------------------------------------
@router.get("/referrals/withdrawal-history")
def get_referral_withdrawal_history():
    """출금 내역 (날짜/지갑주소/TXID/USDT/상태) - referral_withdrawals 기준."""
    return _bridge_or_raise("withdrawal_history")


# ---------------------------------------------------------------------------
# POST /api/user/events  (telemetry — fire and forget)
# ---------------------------------------------------------------------------
@router.post("/events")
def track_event(payload: dict):
    return {"success": True}
