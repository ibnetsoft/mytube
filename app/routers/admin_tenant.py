"""
테넌트 관리 API (관리자 전용)
슈퍼어드민만 접근 가능
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Optional
from pydantic import BaseModel, Field
import database as db
from services.web_admin_client import web_admin_client
from services.auth_service import auth_service

router = APIRouter(prefix="/api/admin/tenant", tags=["Admin-Tenant"])


# ─────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────

class TenantUpdateRequest(BaseModel):
    """테넌트 설정 업데이트 요청"""
    tenant_key: str = Field(..., description="테넌트 키")
    commission_percent: float = Field(..., ge=0, le=100, description="수수료율 (%)")
    min_commission_usd: float = Field(default=0, ge=0, description="최소 수수료 (USD)")


class TenantCreateRequest(BaseModel):
    """새 테넌트 생성 요청"""
    tenant_key: str = Field(..., description="테넌트 키 (영문소문자, 숫자, 하이픈)")
    tenant_name: str = Field(..., description="테넌트 이름")
    brand_name: Optional[str] = Field(None, description="브랜드 이름")
    commission_percent: float = Field(default=10, ge=0, le=100, description="수수료율 (%)")
    min_commission_usd: float = Field(default=0, ge=0, description="최소 수수료 (USD)")
    license_tier: str = Field(default="standard", description="라이선스 티어")


class UserTenantUpdateRequest(BaseModel):
    """사용자 테넌트 업데이트 요청"""
    user_id: str = Field(..., description="사용자 ID")
    tenant_key: str = Field(..., description="할당할 테넌트 키")
    commission_percent: Optional[float] = Field(None, ge=0, le=100, description="개별 수수료율 (미지정 시 테넌트 기본값)")


class CommissionCalculateRequest(BaseModel):
    """수수료 계산 요청"""
    user_id: str = Field(..., description="사용자 ID")
    amount_usd: float = Field(..., gt=0, description="거래 금액 (USD)")


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────

def check_superadmin():
    """슈퍼어드민 권한 확인"""
    # TODO: 실제 구현에서는 profiles 테이블에 is_superadmin 컬럼을 추가하여 확인
    # 현재는 임시로 이메일로 확인
    email = auth_service.get_user_email() or ""
    superadmin_emails = ["admin@airstudio.com", "ibnetsoft@gmail.com"]  # 설정에서 관리
    return email.lower() in [e.lower() for e in superadmin_emails]


def require_superadmin():
    """슈퍼어드민 권한이 있으면 통과, 없으면 예외"""
    if not check_superadmin():
        raise HTTPException(403, "관리자 권한이 필요합니다.")


# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@router.get("/list")
async def get_all_tenants():
    """모든 테넌트 목록 조회 (관리자 전용)"""
    require_superadmin()

    tenants = web_admin_client.get_all_tenants()
    return {
        "status": "success",
        "tenants": tenants,
        "total": len(tenants)
    }


@router.get("/{tenant_key}")
async def get_tenant(tenant_key: str):
    """특정 테넌트 정보 조회 (관리자 전용)"""
    require_superadmin()

    tenant = web_admin_client.get_tenant_by_key(tenant_key)
    if not tenant:
        raise HTTPException(404, "테넌트를 찾을 수 없습니다.")

    # 테넌트 소속 사용자 수
    users = web_admin_client.get_tenant_users(tenant_key)
    user_count = len(users)

    return {
        "status": "success",
        "tenant": tenant,
        "user_count": user_count
    }


@router.post("/commission")
async def update_tenant_commission(req: TenantUpdateRequest):
    """테넌트 수수료 설정 업데이트 (관리자 전용)"""
    require_superadmin()

    result = web_admin_client.update_tenant_commission(
        tenant_key=req.tenant_key,
        commission_percent=req.commission_percent,
        min_commission_usd=req.min_commission_usd
    )

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "업데이트 실패"))

    return {
        "status": "success",
        "message": f"{req.tenant_key}의 수수료가 {req.commission_percent}%로 업데이트되었습니다.",
        "data": result
    }


@router.post("/create")
async def create_tenant(req: TenantCreateRequest):
    """새 테넌트 생성 (관리자 전용)"""
    require_superadmin()

    # 중복 체크
    existing = web_admin_client.get_tenant_by_key(req.tenant_key)
    if existing:
        raise HTTPException(400, "이미 존재하는 테넌트 키입니다.")

    # 테넌트 생성
    body = {
        "tenant_key": req.tenant_key,
        "tenant_name": req.tenant_name,
        "brand_name": req.brand_name or req.tenant_name,
        "commission_percent": req.commission_percent,
        "min_commission_usd": req.min_commission_usd,
        "license_tier": req.license_tier,
        "status": "active"
    }

    response = web_admin_client.supabase_post("tenant_configs", body)

    if response is None or response.status_code not in (200, 201):
        raise HTTPException(500, "테넌트 생성 실패")

    return {
        "status": "success",
        "message": f"{req.tenant_name} 테넌트가 생성되었습니다.",
        "tenant_key": req.tenant_key
    }


@router.get("/{tenant_key}/users")
async def get_tenant_users(tenant_key: str):
    """테넌트 소속 사용자 목록 (관리자 전용)"""
    require_superadmin()

    users = web_admin_client.get_tenant_users(tenant_key)

    return {
        "status": "success",
        "tenant_key": tenant_key,
        "users": users,
        "total": len(users)
    }


@router.post("/user/assign")
async def assign_user_tenant(req: UserTenantUpdateRequest):
    """사용자 테넌트 할당 (관리자 전용)"""
    require_superadmin()

    # 테넌트 존재 확인
    tenant = web_admin_client.get_tenant_by_key(req.tenant_key)
    if not tenant:
        raise HTTPException(404, "테넌트를 찾을 수 없습니다.")

    # 사용자 테넌트 업데이트
    success = web_admin_client.update_user_tenant(
        user_id=req.user_id,
        tenant_key=req.tenant_key,
        commission_percent=req.commission_percent
    )

    if not success:
        raise HTTPException(500, "사용자 테넌트 할당 실패")

    return {
        "status": "success",
        "message": f"사용자가 {req.tenant_key} 테넌트에 할당되었습니다.",
        "user_id": req.user_id,
        "tenant_key": req.tenant_key
    }


@router.post("/commission/calculate")
async def calculate_commission(req: CommissionCalculateRequest):
    """수수료 계산 (테스트용)"""
    require_superadmin()

    result = web_admin_client.calculate_user_commission(
        user_id=req.user_id,
        amount_usd=req.amount_usd
    )

    if "error" in result:
        raise HTTPException(400, result.get("error"))

    return {
        "status": "success",
        "calculation": result
    }


@router.get("/watermark/{user_id}")
async def get_user_watermark_config(user_id: str):
    """사용자 워터마크 설정 조회 (관리자 전용)"""
    require_superadmin()

    watermark = web_admin_client.get_user_watermark(user_id)

    return {
        "status": "success",
        "user_id": user_id,
        "watermark": watermark
    }


@router.get("/stats/overview")
async def get_tenant_stats():
    """테넌트 통계 개요 (관리자 전용)"""
    require_superadmin()

    tenants = web_admin_client.get_all_tenants()

    active_tenants = [t for t in tenants if t.get("status") == "active"]
    suspended_tenants = [t for t in tenants if t.get("status") == "suspended"]

    # 평균 수수료율 계산
    avg_commission = 0
    if active_tenants:
        commissions = [float(t.get("commission_percent", 0)) for t in active_tenants]
        avg_commission = sum(commissions) / len(commissions)

    return {
        "status": "success",
        "stats": {
            "total_tenants": len(tenants),
            "active_tenants": len(active_tenants),
            "suspended_tenants": len(suspended_tenants),
            "avg_commission_percent": round(avg_commission, 2)
        },
        "tenants_by_tier": {
            "starter": len([t for t in tenants if t.get("license_tier") == "starter"]),
            "standard": len([t for t in tenants if t.get("license_tier") == "standard"]),
            "business": len([t for t in tenants if t.get("license_tier") == "business"]),
            "enterprise": len([t for t in tenants if t.get("license_tier") == "enterprise"]),
        }
    }