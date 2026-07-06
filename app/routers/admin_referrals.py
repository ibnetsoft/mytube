from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
import datetime

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client
from app.routers.admin_tenant import require_superadmin

router = APIRouter(prefix="/admin/referrals", tags=["Admin-Referral"])


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

def _supabase_patch(table: str, payload: dict, **params):
    resp = web_admin_client.supabase_patch(table, payload, params=params)
    if resp is None:
        raise HTTPException(status_code=503, detail="Supabase unreachable.")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase patch error on '{table}': {resp.text[:300]}"
        )
    return resp.json()

# ---------------------------------------------------------------------------
# GET /api/admin/referrals/members
# ---------------------------------------------------------------------------
@router.get("/members")
def search_members(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1),
    limit: int = Query(50)
):
    require_superadmin()
    
    offset = (page - 1) * limit
    
    # We will search profiles. PostgREST `or` filter.
    # q can match email, full_name, referral_code, my_referral_code, id, contact
    params = {
        'select': 'id,email,full_name,contact,referral_code,my_referral_code,created_at',
        'order': 'created_at.desc',
        'limit': str(limit),
        'offset': str(offset)
    }
    
    if q:
        q_clean = q.strip()
        # To avoid UUID parsing errors, we only include `id.eq` if it looks like a uuid (or we just use ilike for everything)
        import re
        is_uuid = re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', q_clean, re.I)
        
        or_conds = [
            f"email.ilike.*{q_clean}*",
            f"full_name.ilike.*{q_clean}*",
            f"my_referral_code.ilike.*{q_clean}*",
            f"referral_code.ilike.*{q_clean}*",
            f"contact.ilike.*{q_clean}*"
        ]
        if is_uuid:
            or_conds.append(f"id.eq.{q_clean}")
            
        params['or'] = f"({','.join(or_conds)})"
        
    profiles = _supabase_get('profiles', **params)
    
    return {"success": True, "data": profiles, "page": page, "limit": limit}

# ---------------------------------------------------------------------------
# GET /api/admin/referrals/tree/{user_id}
# ---------------------------------------------------------------------------
@router.get("/tree/{user_id}")
def get_admin_tree(user_id: str):
    require_superadmin()
    
    nodes = []
    
    # L1
    l1 = _supabase_get(
        'profiles',
        **{'referred_by': f'eq.{user_id}', 'select': 'id,email,full_name,created_at,referred_by'}
    )
    l1_ids = []
    for row in l1:
        l1_ids.append(row['id'])
        nodes.append({
            "id": row['id'],
            "referrer_id": row.get('referred_by'),
            "display_name": row.get('full_name') or (row.get('email') or '').split('@')[0] or 'User',
            "created_at": row.get('created_at'),
            "level": 1,
        })
        
    # L2
    l2_count = 0
    if l1_ids:
        # Safe chunking for L1 > 500
        chunk_size = 300
        for i in range(0, len(l1_ids), chunk_size):
            chunk = l1_ids[i:i + chunk_size]
            in_filter = f"in.({','.join(chunk)})"
            l2 = _supabase_get(
                'profiles',
                **{'referred_by': in_filter, 'select': 'id,email,full_name,created_at,referred_by'}
            )
            l2_count += len(l2)
            for row in l2:
                nodes.append({
                    "id": row['id'],
                    "referrer_id": row.get('referred_by'),
                    "display_name": row.get('full_name') or (row.get('email') or '').split('@')[0] or 'User',
                    "created_at": row.get('created_at'),
                    "level": 2,
                })
                
    # Get commissions summary for the tree owner using SQL aggregation if possible
    # We will use the REST API logic: Fetch pending/approved/paid via group by? No, PostgREST doesn't support GROUP BY easily without RPC.
    # For now, we fetch select=commission_tokens,status to minimize data transfer instead of all fields.
    commissions = _supabase_get(
        'referral_commissions',
        **{'beneficiary_id': f'eq.{user_id}', 'select': 'commission_tokens,status,commission_type'}
    )
    
    pending = 0
    approved = 0
    withdrawn = 0
    
    for c in commissions:
        status = (c.get('status') or '').upper()
        tokens = c.get('commission_tokens', 0) or 0
        ctype = (c.get('commission_type') or '').upper()
        
        if ctype == 'WITHDRAWAL':
            if status in ('APPROVED', 'COMPLETED', 'PAID'):
                withdrawn += abs(tokens)
            # if pending withdrawal, it doesn't count as withdrawn yet
        else:
            if status in ('PENDING', 'WAITING'):
                pending += tokens
            elif status in ('APPROVED', 'COMPLETED', 'PAID'):
                approved += tokens
                
    summary = {
        "totalMembers": len(l1) + l2_count,
        "level1Members": len(l1),
        "level2Members": l2_count,
        "pendingCommission": pending,
        "approvedCommission": approved,
        "totalWithdrawn": withdrawn
    }

    return {"success": True, "data": {"tree": nodes, "summary": summary}}

# ---------------------------------------------------------------------------
# GET /api/admin/referrals/commissions/{user_id}
# ---------------------------------------------------------------------------
@router.get("/commissions/{user_id}")
def get_admin_commissions(
    user_id: str,
    page: int = Query(1),
    limit: int = Query(50)
):
    require_superadmin()
    
    offset = (page - 1) * limit
    params = {
        'beneficiary_id': f'eq.{user_id}',
        'order': 'created_at.desc',
        'limit': str(limit),
        'offset': str(offset)
    }
    
    items = _supabase_get('referral_commissions', **params)
    return {"success": True, "data": items, "page": page, "limit": limit}

# ---------------------------------------------------------------------------
# GET /api/admin/referrals/withdrawals
# ---------------------------------------------------------------------------
@router.get("/withdrawals")
def get_admin_withdrawals(
    status: Optional[str] = Query(None),
    page: int = Query(1),
    limit: int = Query(50)
):
    require_superadmin()
    
    offset = (page - 1) * limit
    params = {
        'commission_type': 'eq.WITHDRAWAL',
        'order': 'created_at.desc',
        'limit': str(limit),
        'offset': str(offset),
        'select': '*, beneficiary:profiles!referral_commissions_beneficiary_id_fkey(id,email,full_name)'
    }
    if status and status != 'ALL':
        params['status'] = f'eq.{status}'
        
    items = _supabase_get('referral_commissions', **params)
    
    # Extract embedded profile info for easier frontend consumption
    for i in items:
        if 'beneficiary' in i and i['beneficiary']:
            i['user_email'] = i['beneficiary'].get('email')
            i['user_name'] = i['beneficiary'].get('full_name')
        else:
            i['user_email'] = 'Unknown'
            i['user_name'] = 'Unknown'
            
    return {"success": True, "data": items, "page": page, "limit": limit}

# ---------------------------------------------------------------------------
# POST /api/admin/referrals/withdrawals/{withdrawal_id}/approve
# ---------------------------------------------------------------------------
class ReasonPayload(BaseModel):
    reason: Optional[str] = None

@router.post("/withdrawals/{withdrawal_id}/approve")
def approve_withdrawal(withdrawal_id: str, payload: ReasonPayload = Body(default_factory=ReasonPayload)):
    require_superadmin()
    admin_email = auth_service.get_user_email()
    
    # 1. Fetch the withdrawal
    items = _supabase_get('referral_commissions', **{'id': f'eq.{withdrawal_id}'})
    if not items:
        raise HTTPException(404, "Withdrawal not found")
        
    item = items[0]
    if item.get('commission_type') != 'WITHDRAWAL':
        raise HTTPException(400, "Item is not a withdrawal")
        
    old_status = (item.get('status') or '').upper()
    if old_status in ('COMPLETED', 'PAID', 'APPROVED'):
        raise HTTPException(400, "Withdrawal is already completed/approved")
        
    new_status = 'COMPLETED'
    
    # 2. Add Audit Log to metadata
    meta = item.get('metadata') or {}
    audit = meta.get('audit_trail', [])
    audit.append({
        "admin": admin_email,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "old_status": old_status,
        "new_status": new_status,
        "reason": payload.reason or "Approved by Admin"
    })
    meta['audit_trail'] = audit
    
    # 3. Update
    _supabase_patch(
        'referral_commissions',
        {'status': new_status, 'metadata': meta},
        **{'id': f'eq.{withdrawal_id}'}
    )
    
    return {"success": True, "message": "Withdrawal approved."}

# ---------------------------------------------------------------------------
# POST /api/admin/referrals/withdrawals/{withdrawal_id}/reject
# ---------------------------------------------------------------------------
@router.post("/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(withdrawal_id: str, payload: ReasonPayload = Body(default_factory=ReasonPayload)):
    require_superadmin()
    admin_email = auth_service.get_user_email()
    
    # 1. Fetch
    items = _supabase_get('referral_commissions', **{'id': f'eq.{withdrawal_id}'})
    if not items:
        raise HTTPException(404, "Withdrawal not found")
        
    item = items[0]
    if item.get('commission_type') != 'WITHDRAWAL':
        raise HTTPException(400, "Item is not a withdrawal")
        
    old_status = (item.get('status') or '').upper()
    if old_status in ('COMPLETED', 'PAID', 'APPROVED'):
        raise HTTPException(400, "Cannot reject an already completed withdrawal")
    if old_status in ('REJECTED', 'CANCELLED'):
        raise HTTPException(400, "Already rejected")
        
    new_status = 'REJECTED'
    
    # 2. Add Audit Log
    meta = item.get('metadata') or {}
    audit = meta.get('audit_trail', [])
    audit.append({
        "admin": admin_email,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "old_status": old_status,
        "new_status": new_status,
        "reason": payload.reason or "Rejected by Admin"
    })
    meta['audit_trail'] = audit
    
    # 3. Update
    _supabase_patch(
        'referral_commissions',
        {'status': new_status, 'metadata': meta},
        **{'id': f'eq.{withdrawal_id}'}
    )
    
    return {"success": True, "message": "Withdrawal rejected."}

# ---------------------------------------------------------------------------
# GET /api/admin/referrals/stats
# ---------------------------------------------------------------------------
@router.get("/stats")
def get_admin_stats():
    require_superadmin()
    
    # Fetch global stats
    # For performance on a very large table, this would normally be a SQL view.
    # To keep it lightweight and fast here, we fetch with minimal select where status in pending/approved
    items = _supabase_get('referral_commissions', **{'select': 'commission_tokens,status,commission_type'})
    
    pending_withdraw = 0
    today_withdraw = 0
    total_paid = 0
    pending_commission = 0
    approved_commission = 0
    
    # Simple Python aggregation. OK for moderate sizes. SQL-level aggregation is better if size > 50K.
    for c in items:
        status = (c.get('status') or '').upper()
        tokens = c.get('commission_tokens', 0) or 0
        ctype = (c.get('commission_type') or '').upper()
        
        if ctype == 'WITHDRAWAL':
            if status == 'PENDING':
                pending_withdraw += abs(tokens)
            elif status in ('COMPLETED', 'PAID', 'APPROVED'):
                total_paid += abs(tokens)
        else:
            if status in ('PENDING', 'WAITING'):
                pending_commission += tokens
            elif status in ('APPROVED', 'COMPLETED', 'PAID'):
                approved_commission += tokens
                
    # Get total members
    profiles = _supabase_get('profiles', **{'select': 'id', 'limit': '1', 'count': 'exact'})
    # Supabase PostgREST might not return count easily via python requests wrapper if we don't pass headers,
    # but we can fallback or skip. Actually `web_admin_client` doesn't pass Prefer: count=exact, so profiles is just rows.
    # Wait, the frontend card needs member count, we might just leave it blank or approximate if we can't query count directly.
    # I'll just not query profile count here to avoid fetching all profiles.
    
    return {
        "success": True,
        "data": {
            "pendingWithdrawals": pending_withdraw,
            "totalPaid": total_paid,
            "pendingCommission": pending_commission,
            "approvedCommission": approved_commission
        }
    }
