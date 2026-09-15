"""
Stage 1 AIR/USDT wallet API bridge.

All real wallet writes happen in auth-web /api/desktop-wallet with the
service-role key. The local app only forwards the user's email + signed session
token and returns public wallet data to the UI.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/api/user/wallet", tags=["wallet"])


def _bridge(action: str, params: Optional[dict] = None) -> dict:
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized: No logged-in user email.")
    session_token = auth_service.get_session_token()
    if not session_token:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")
    return web_admin_client.desktop_wallet(email, session_token, action, params)


def _bridge_or_raise(action: str, params: Optional[dict] = None) -> dict:
    result = _bridge(action, params)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "지갑 서버 오류")
    return result


class SwapRequest(BaseModel):
    from_asset: str
    amount: str


class WithdrawalRequest(BaseModel):
    asset: str = "USDT"
    amount: str
    to_address: str
    network: Optional[str] = None


@router.get("/me")
def get_wallet_me():
    return _bridge_or_raise("me")


@router.post("/sync-air-deposits")
def sync_air_deposits():
    return _bridge_or_raise("sync_air_deposits")


@router.post("/swap")
def swap_wallet_asset(req: SwapRequest):
    return _bridge("swap", {
        "from_asset": req.from_asset,
        "amount": req.amount,
    })


@router.post("/withdraw")
def request_wallet_withdrawal(req: WithdrawalRequest):
    return _bridge("withdraw", {
        "asset": req.asset,
        "amount": req.amount,
        "to_address": req.to_address,
        "network": req.network,
    })


@router.get("/history")
def get_wallet_history():
    return _bridge_or_raise("history")
