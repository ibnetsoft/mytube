-- =============================================================
-- B2B 테넌트 도입 신청 및 문의 관리 테이블 마이그레이션
-- Supabase SQL Editor에서 실행하세요.
-- =============================================================

CREATE TABLE IF NOT EXISTS public.tenant_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    brand_name TEXT,
    contact_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    channel_count INT NOT NULL DEFAULT 5,
    estimated_setup_fee NUMERIC(10,2) DEFAULT 500,
    estimated_monthly_fee NUMERIC(10,2) DEFAULT 500,
    currency TEXT DEFAULT 'USD',
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'approved' | 'rejected'
    tenant_key TEXT,                       -- 승인 시 생성된 테넌트 키
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_tenant_applications_status ON public.tenant_applications(status);
CREATE INDEX IF NOT EXISTS idx_tenant_applications_created_at ON public.tenant_applications(created_at DESC);

-- RLS 활성화
ALTER TABLE public.tenant_applications ENABLE ROW LEVEL SECURITY;

-- 1. 비로그인/모든 사용자: 신청서 제출(INSERT) 가능
DROP POLICY IF EXISTS "tenant_applications_public_insert" ON public.tenant_applications;
CREATE POLICY "tenant_applications_public_insert" ON public.tenant_applications
    FOR INSERT WITH CHECK (true);

-- 2. 슈퍼어드민: 전체 조회 및 수정(승인/반려) 가능
DROP POLICY IF EXISTS "tenant_applications_admin_all" ON public.tenant_applications;
CREATE POLICY "tenant_applications_admin_all" ON public.tenant_applications
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM auth.users
            WHERE auth.users.id = auth.uid()
            AND auth.users.raw_user_meta_data->>'is_superadmin' = 'true'
        )
    );
