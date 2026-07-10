"""
Referral Dashboard API — FastAPI router
Uses direct Supabase REST queries with verified column names:

  profiles:
    id, email, full_name, referred_by, my_referral_code, referral_code,
    referral_depth, created_at, ...

  referral_commissions:
    id, beneficiary_id, source_user_id, commission_type,
    base_tokens, rate_percent, commission_tokens,
    status, metadata, created_at, paid_at

Broken Supabase RPCs (get_referral_dashboard_kpi / get_referral_tree /
get_commission_timeline) all reference a non-existent column `referrer_id`.
We skip those and query the tables directly.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/user", tags=["referral"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current_user_id() -> str:
    """Return the desktop app's logged-in user UUID or raise HTTP 401/404."""
    email = auth_service.get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized: No logged-in user email.")
    user_id = web_admin_client.resolve_user_id(email=email)
    if not user_id:
        raise HTTPException(status_code=404, detail="Not Found: User ID could not be resolved.")
    return user_id


def _supabase_get(table: str, **params):
    """Thin wrapper that converts None-values to absent params."""
    clean = {k: v for k, v in params.items() if v is not None}
    resp = web_admin_client.supabase_get(table, params=clean)
    if resp is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured or unreachable.")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase error on '{table}': {resp.text[:300]}"
        )
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/user/referrals/dashboard
# ---------------------------------------------------------------------------
@router.get("/referrals/dashboard")
def get_referral_dashboard():
    user_id = _get_current_user_id()

    # ── 1. My profile (referral code) ────────────────────────────────────
    profiles = _supabase_get(
        'profiles',
        **{
            'id': f'eq.{user_id}',
            'select': 'my_referral_code,referral_code,email',
        }
    )
    my_profile = profiles[0] if profiles else {}
    # referral_code is the sole source of truth (DB-generated at signup,
    # matches web admin, matches validate_referral_code). my_referral_code
    # was a legacy client-generated duplicate that never worked for actual
    # signup validation — no longer written, kept only as a last-resort
    # fallback for any pre-existing rows that never got a referral_code.
    ref_code = (
        my_profile.get('referral_code')
        or my_profile.get('my_referral_code')
        or ''
    )
    ref_link = (
        f"https://mytube-ashy-seven.vercel.app?ref={ref_code}"
        if ref_code else ''
    )

    # ── 2. Level-1 referrals (직접 추천인) ───────────────────────────────
    l1 = _supabase_get(
        'profiles',
        **{'referred_by': f'eq.{user_id}', 'select': 'id'}
    )
    l1_ids = [r['id'] for r in l1]

    # ── 3. Level-2 referrals (간접 추천인) ───────────────────────────────
    l2_count = 0
    if l1_ids:
        # Supabase PostgREST: `in.(id1,id2,...)`
        in_filter = f"in.({','.join(l1_ids)})"
        l2 = _supabase_get(
            'profiles',
            **{'referred_by': in_filter, 'select': 'id'}
        )
        l2_count = len(l2)

    total_referrals = len(l1_ids) + l2_count

    # ── 4. Commission summary via RPC (SQL-Level Aggregation) ───────────────────────
    rpc_res = web_admin_client.call_rpc('get_referral_user_kpi', {'uid': user_id})
    if rpc_res and rpc_res.status_code == 200:
        kpi = rpc_res.json()
        pending = kpi.get('pendingCommission', 0)
        approved = kpi.get('approvedCommission', 0)
    else:
        pending = 0
        approved = 0
        print(f"[Warning] get_referral_user_kpi RPC failed or not deployed.")
        
    total_commission = pending + approved

    result = {
        "referralCode": ref_code,
        "referralLink": ref_link,
        "totalReferrals": total_referrals,
        "level1Count": len(l1_ids),
        "level2Count": l2_count,
        "activeReferrals": len(l1_ids),
        "pendingCommission": pending,
        "approvedCommission": approved,
        "totalCommission": total_commission,
    }
    return {"success": True, "data": result}


# ---------------------------------------------------------------------------
# GET /api/user/referrals/tree
# ---------------------------------------------------------------------------
@router.get("/referrals/tree")
def get_referral_tree(
    level: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
):
    user_id = _get_current_user_id()
    # Guard: when called directly (not via HTTP), level may be a Query object
    _level = None if not isinstance(level, int) else level
    max_level = _level if _level is not None else 2  # default: 2단계

    nodes = []

    # ── Level 1 ──────────────────────────────────────────────────────────
    l1 = _supabase_get(
        'profiles',
        **{
            'referred_by': f'eq.{user_id}',
            'select': 'id,email,full_name,created_at,referred_by,referral_country,country_code',
        }
    )
    for row in l1:
        nodes.append({
            "id": row['id'],
            "referrer_id": row.get('referred_by'),
            "display_name": (
                row.get('full_name')
                or (row.get('email') or '').split('@')[0]
                or 'User'
            ),
            "email": row.get('email'),
            "country": row.get('referral_country') or row.get('country_code'),
            "created_at": row.get('created_at'),
            "total_commission_generated": 0,
            "level": 1,
        })

    # ── Level 2 (Safe Chunking logic to avoid URL limit) ──────────────────────────────────────────────────────────
    if max_level >= 2 and l1:
        l1_ids = [r['id'] for r in l1]
        chunk_size = 300
        for i in range(0, len(l1_ids), chunk_size):
            chunk = l1_ids[i:i+chunk_size]
            in_filter = f"in.({','.join(chunk)})"
            l2 = _supabase_get(
                'profiles',
                **{
                    'referred_by': in_filter,
                    'select': 'id,email,full_name,created_at,referred_by,referral_country,country_code',
                }
            )
            for row in l2:
                nodes.append({
                    "id": row['id'],
                    "referrer_id": row.get('referred_by'),
                    "display_name": (
                        row.get('full_name')
                        or (row.get('email') or '').split('@')[0]
                        or 'User'
                    ),
                    "email": row.get('email'),
                    "country": row.get('referral_country') or row.get('country_code'),
                    "created_at": row.get('created_at'),
                    "total_commission_generated": 0,
                    "level": 2,
                })

    # ── Commission earned FROM each node's activity (beneficiary = me) ─────
    # AIR-0225: total_commission_generated was hardcoded to 0 - never
    # actually queried. referral_commissions.source_user_id is whoever's
    # usage generated the row; beneficiary_id is who gets paid (me, here).
    if nodes:
        node_ids = [n['id'] for n in nodes]
        chunk_size = 300
        commission_by_source = {}
        for i in range(0, len(node_ids), chunk_size):
            chunk = node_ids[i:i + chunk_size]
            rows = _supabase_get(
                'referral_commissions',
                **{
                    'beneficiary_id': f'eq.{user_id}',
                    'source_user_id': f'in.({",".join(chunk)})',
                    'commission_type': 'neq.WITHDRAWAL',
                    'select': 'source_user_id,commission_tokens',
                }
            )
            for row in rows:
                sid = row.get('source_user_id')
                amount = float(row.get('commission_tokens') or 0)
                commission_by_source[sid] = commission_by_source.get(sid, 0.0) + amount

        for n in nodes:
            n['total_commission_generated'] = round(commission_by_source.get(n['id'], 0.0), 4)
            n['is_active'] = n['id'] in commission_by_source

    if status and status != 'all':
        nodes = [n for n in nodes if n.get('status') == status]

    return {"success": True, "data": nodes}


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
    user_id = _get_current_user_id()
    # Guard: FastAPI Query objects when called directly
    page = page if isinstance(page, int) else 1
    limit = limit if isinstance(limit, int) else 10
    sort_by = sort_by if isinstance(sort_by, str) and not sort_by.startswith('annotation=') else 'created_at'
    sort_dir = sort_dir if isinstance(sort_dir, str) and sort_dir in ('asc', 'desc') else 'desc'
    offset = (page - 1) * limit

    params = {
        'beneficiary_id': f'eq.{user_id}',
        'select': 'id,commission_type,commission_tokens,status,created_at,paid_at,metadata',
        'order': f"{sort_by}.{sort_dir}",
        'limit': str(limit),
        'offset': str(offset),
    }
    if status:
        params['status'] = f'eq.{status}'
    if type:
        params['commission_type'] = f'eq.{type}'

    items = _supabase_get('referral_commissions', **params)

    # Normalise to the shape the template expects
    normalised = []
    for item in items:
        normalised.append({
            "id": item.get('id'),
            "description": item.get('commission_type', '수익 발생'),
            "amount": item.get('commission_tokens', 0) or 0,
            "status": (item.get('status') or 'PENDING').upper(),
            "created_at": item.get('created_at'),
            "paid_at": item.get('paid_at'),
        })

    has_next = len(items) == limit
    return {
        "success": True,
        "items": normalised,
        "data": normalised,
        "has_next": has_next,
        "pagination": {
            "current_page": page,
            "has_next": has_next,
            "total_records": len(normalised),
        },
    }


# ---------------------------------------------------------------------------
# GET /api/user/referrals/withdrawal-info
# ---------------------------------------------------------------------------
@router.get("/referrals/withdrawal-info")
def get_referral_withdrawal_info():
    user_id = _get_current_user_id()
    
    # Fetch all referral commissions for the user
    commissions = _supabase_get(
        'referral_commissions',
        **{
            'beneficiary_id': f'eq.{user_id}',
            'select': 'commission_tokens,status,commission_type',
        }
    )

    total_earned = 0.0
    total_withdrawn = 0.0
    pending_withdrawal = 0.0

    for c in commissions:
        amount = float(c.get('commission_tokens', 0) or 0)
        status = (c.get('status') or '').upper()
        ctype = (c.get('commission_type') or '').upper()

        if ctype == 'WITHDRAWAL':
            if status == 'PENDING':
                pending_withdrawal += abs(amount)
            elif status in ('APPROVED', 'COMPLETED', 'PAID'):
                total_withdrawn += abs(amount)
        else:
            if status in ('APPROVED', 'COMPLETED', 'PAID'):
                total_earned += amount

    available = total_earned - total_withdrawn - pending_withdrawal
    if available < 0:
        available = 0.0

    return {
        "success": True,
        "data": {
            "totalEarned": total_earned,
            "totalWithdrawn": total_withdrawn,
            "pendingWithdrawal": pending_withdrawal,
            "availableBalance": available,
        }
    }


from pydantic import BaseModel
class ReferralWithdrawalRequest(BaseModel):
    amount: float
    dest_address: str


# ---------------------------------------------------------------------------
# POST /api/user/referrals/withdraw
# ---------------------------------------------------------------------------
@router.post("/referrals/withdraw")
def request_referral_withdrawal(req: ReferralWithdrawalRequest):
    user_id = _get_current_user_id()
    
    # 1. Validate balance
    info = get_referral_withdrawal_info()
    available = info["data"]["availableBalance"]
    
    amount = float(req.amount)
    if amount <= 0:
        return {"success": False, "error": "출금 금액은 0보다 커야 합니다."}
        
    if amount > available:
        return {"success": False, "error": "출금 가능 금액을 초과했습니다."}
        
    import database as db
    min_withdrawal = float(db.get_global_setting("min_withdrawal_usdt", "10"))
    if amount < min_withdrawal:
        return {"success": False, "error": f"최소 출금 가능 금액은 {min_withdrawal} USDT 입니다."}

    # 2. Insert into referral_commissions as a WITHDRAWAL type with negative amount
    #    (legacy pattern — remains the system of record through AIR-0221 Stage 2)
    payload = {
        "beneficiary_id": user_id,
        "source_user_id": user_id,  # Self
        "commission_type": "WITHDRAWAL",
        "commission_tokens": -amount,
        "status": "PENDING",
        "metadata": {"dest_address": req.dest_address.strip()}
    }

    res = web_admin_client.supabase_post("referral_commissions", payload, return_representation=True)
    if not res or res.status_code not in (201, 204):
        return {"success": False, "error": "출금 요청 중 오류가 발생했습니다."}

    legacy_commission_id = None
    try:
        body = res.json()
        if isinstance(body, list) and body:
            legacy_commission_id = body[0].get("id")
    except Exception:
        legacy_commission_id = None

    # 3. AIR-0221 Stage 2 dual-write into referral_withdrawals — additive,
    #    best-effort only. The legacy insert above already succeeded and is
    #    the system of record; a failure here must never surface to the user
    #    or undo the legacy write.
    try:
        dual_write_payload = {
            "user_id": user_id,
            "amount": amount,
            "wallet_address": req.dest_address.strip(),
            "status": "REQUESTED",
            "metadata": {
                "legacy_source": "referral_negative_commission",
                "legacy_commission_id": legacy_commission_id,
            },
        }
        dw_res = web_admin_client.supabase_post("referral_withdrawals", dual_write_payload)
        if not dw_res or dw_res.status_code not in (201, 204):
            print(
                f"[Stage2 dual-write] referral_withdrawals insert failed: "
                f"{getattr(dw_res, 'status_code', 'no-response')} {getattr(dw_res, 'text', '')[:300]}"
            )
    except Exception as e:
        print(f"[Stage2 dual-write] referral_withdrawals insert error: {e}")

    return {"success": True, "message": "출금 신청이 완료되었습니다."}


# ---------------------------------------------------------------------------
# GET /api/user/referrals/withdrawal-history
# ---------------------------------------------------------------------------
@router.get("/referrals/withdrawal-history")
def get_referral_withdrawal_history():
    """출금 내역 (날짜/지갑주소/TXID/USDT/상태).

    referral_withdrawals(AIR-0221 Stage 2 dual-write 대상)에서 조회한다 -
    legacy referral_commissions(WITHDRAWAL type)에는 tx_hash가 없어서 TXID를
    보여줄 방법이 없다. dual-write는 best-effort라 아주 드물게 누락될 수 있지만,
    TXID를 표시할 수 있는 유일한 소스다.
    """
    user_id = _get_current_user_id()

    rows = _supabase_get(
        'referral_withdrawals',
        **{
            'user_id': f'eq.{user_id}',
            'select': 'id,amount,wallet_address,status,tx_hash,created_at',
            'order': 'created_at.desc',
            'limit': '100',
        }
    )

    history = [
        {
            "id": r.get("id"),
            "created_at": r.get("created_at"),
            "wallet_address": r.get("wallet_address"),
            "tx_hash": r.get("tx_hash"),
            "amount": r.get("amount"),
            "status": r.get("status"),
        }
        for r in (rows or [])
    ]

    return {"success": True, "data": history}


# ---------------------------------------------------------------------------
# POST /api/user/events  (telemetry — fire and forget)
# ---------------------------------------------------------------------------
@router.post("/events")
def track_event(payload: dict):
    return {"success": True}

