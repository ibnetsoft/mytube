-- =============================================================
-- 테넌트 및 수수료 시스템 마이그레이션
-- Supabase SQL Editor에서 실행하세요.
-- =============================================================

-- ─────────────────────────────────────────────
-- 1. tenant_configs: 테넌트별 설정 테이블
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenant_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_key TEXT NOT NULL UNIQUE,  -- 'default' | 'tenant_a' | 'tenant_b'
    tenant_name TEXT NOT NULL,

    -- 브랜딩
    brand_name TEXT,
    logo_url TEXT,
    primary_color TEXT DEFAULT '#3B82F6',
    custom_domain TEXT,

    -- 수수료 설정 (슈퍼어드민 설정 가능)
    -- 수수료는 AIR Studio가 테넌트의 거래에서 가져가는 수수료
    commission_percent NUMERIC(5,2) DEFAULT 10,  -- 기본 10%
    min_commission_usd NUMERIC(10,2) DEFAULT 0,  -- 최소 수수료 (USD)

    -- 라이선스 설정
    license_tier TEXT NOT NULL DEFAULT 'standard',  -- 'starter' | 'standard' | 'business' | 'enterprise'
    monthly_fee_usd NUMERIC(10,2) DEFAULT 0,

    -- 제한 설정
    max_projects_per_month INT DEFAULT 50,
    max_render_minutes_per_month INT DEFAULT 300,
    max_storage_gb NUMERIC(10,2) DEFAULT 10,
    max_api_calls_per_day INT DEFAULT 1000,

    -- 워터마크
    watermark_enabled BOOLEAN DEFAULT TRUE,
    watermark_position TEXT DEFAULT 'bottom-right',  -- 'bottom-right' | 'bottom-left' | 'center'
    watermark_opacity NUMERIC(3,2) DEFAULT 0.3,  -- 0~1
    watermark_url TEXT,

    -- 상태
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'suspended' | 'cancelled'
    trial_until TIMESTAMPTZ,
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id),
    updated_by UUID REFERENCES auth.users(id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_tenant_configs_key ON public.tenant_configs(tenant_key);
CREATE INDEX IF NOT EXISTS idx_tenant_configs_status ON public.tenant_configs(status);

-- ─────────────────────────────────────────────
-- 2. 기본 테넌트 생성 (default)
-- ─────────────────────────────────────────────
INSERT INTO public.tenant_configs (
    tenant_key, tenant_name, brand_name, commission_percent, license_tier
) VALUES (
    'default', 'AIR Studio Default', 'AIR Studio', 10, 'enterprise'
) ON CONFLICT (tenant_key) DO NOTHING;

-- ─────────────────────────────────────────────
-- 3. tenant_users: 테넌트-사용자 매핑
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_key TEXT NOT NULL REFERENCES public.tenant_configs(tenant_key) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',  -- 'owner' | 'admin' | 'member'
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'pending' | 'suspended'

    -- 수수료 개별 설정 (테넌트 기본값 오버라이드)
    -- 해당 사용자의 거래에서 적용되는 수수료
    commission_percent NUMERIC(5,2),  -- NULL이면 테넌트 기본값 사용

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_users_unique ON public.tenant_users(tenant_key, user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_user ON public.tenant_users(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_status ON public.tenant_users(status);

-- ─────────────────────────────────────────────
-- 4. tenant_commission_logs: 수수료 이력
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenant_commission_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_key TEXT NOT NULL REFERENCES public.tenant_configs(tenant_key) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,

    -- 거래 정보
    transaction_type TEXT NOT NULL,  -- 'withdrawal' | 'payout' | 'refund' | 'commission'
    transaction_id TEXT,

    -- 금액
    amount_usd NUMERIC(18,6) NOT NULL,  -- 거래 금액
    commission_percent NUMERIC(5,2) NOT NULL,  -- 적용된 수수료율
    commission_usd NUMERIC(18,6) NOT NULL,  -- 수수료 금액
    net_usd NUMERIC(18,6) NOT NULL,  -- 실제 지급액

    -- 메타데이터
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_commission_logs_tenant ON public.tenant_commission_logs(tenant_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commission_logs_user ON public.tenant_commission_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commission_logs_type ON public.tenant_commission_logs(transaction_type, created_at DESC);

-- ─────────────────────────────────────────────
-- 5. profiles 테이블에 테넌트 키 컬럼 추가
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'tenant_key'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN tenant_key TEXT DEFAULT 'default';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'commission_percent'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN commission_percent NUMERIC(5,2);
    END IF;

    RAISE NOTICE 'tenant 컬럼이 profiles 테이블에 추가되었습니다.';
END $$;

-- 기존 사용자에게 default 테넌트 할당
UPDATE public.profiles
SET tenant_key = 'default'
WHERE tenant_key IS NULL OR tenant_key = '';

-- ─────────────────────────────────────────────
-- 6. RLS (Row Level Security) 정책
-- ─────────────────────────────────────────────

-- tenant_configs: 슈퍼어드민만 전체 읽기/쓰기
ALTER TABLE public.tenant_configs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_configs_public_read" ON public.tenant_configs;
CREATE POLICY "tenant_configs_public_read" ON public.tenant_configs
    FOR SELECT USING (status = 'active');

-- 테넌트별로 자신의 설정만 업데이트
DROP POLICY IF EXISTS "tenant_configs_tenant_update" ON public.tenant_configs;
CREATE POLICY "tenant_configs_tenant_update" ON public.tenant_configs
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM auth.users
            WHERE auth.users.id = auth.uid()
            AND (
                auth.users.raw_user_meta_data->>'is_superadmin' = 'true'
                OR tenant_key = (SELECT tenant_key FROM profiles WHERE id = auth.uid())
            )
        )
    );

-- tenant_users: 본인 매핑만 읽기/쓰기
ALTER TABLE public.tenant_users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_users_self_read" ON public.tenant_users;
CREATE POLICY "tenant_users_self_read" ON public.tenant_users
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "tenant_users_self_write" ON public.tenant_users;
CREATE POLICY "tenant_users_self_write" ON public.tenant_users
    FOR UPDATE USING (user_id = auth.uid());

DROP POLICY IF EXISTS "tenant_users_tenant_admin_write" ON public.tenant_users;
CREATE POLICY "tenant_users_tenant_admin_write" ON public.tenant_users
    FOR INSERT USING (
        EXISTS (
            SELECT 1 FROM tenant_users
            WHERE tenant_users.user_id = auth.uid()
            AND tenant_users.tenant_key = NEW.tenant_key
            AND tenant_users.role IN ('owner', 'admin')
        )
    );

-- tenant_commission_logs: 본인/테넌트 읽기
ALTER TABLE public.tenant_commission_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "commission_logs_self_read" ON public.tenant_commission_logs;
CREATE POLICY "commission_logs_self_read" ON public.tenant_commission_logs
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "commission_logs_tenant_read" ON public.tenant_commission_logs;
CREATE POLICY "commission_logs_tenant_read" ON public.tenant_commission_logs
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM tenant_users
            WHERE tenant_users.user_id = auth.uid()
            AND tenant_users.tenant_key = public.tenant_commission_logs.tenant_key
        )
    );

-- ─────────────────────────────────────────────
-- 7. 수수료 계산 함수
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.calculate_commission(
    p_user_id UUID,
    p_amount_usd NUMERIC
)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_profile public.profiles%ROWTYPE;
    v_tenant public.tenant_configs%ROWTYPE;
    v_commission_percent NUMERIC(5,2);
    v_commission_usd NUMERIC(18,6);
    v_min_commission NUMERIC(10,2);
    v_tenant_key TEXT;
BEGIN
    -- 프로필 정보 조회
    SELECT * INTO v_profile FROM public.profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN json_build_object('error', 'user_not_found');
    END IF;

    -- 테넌트 설정 조회
    v_tenant_key := COALESCE(v_profile.tenant_key, 'default');
    SELECT * INTO v_tenant FROM public.tenant_configs WHERE tenant_key = v_tenant_key AND status = 'active';

    IF NOT FOUND THEN
        -- 기본 테넌트 사용
        SELECT * INTO v_tenant FROM public.tenant_configs WHERE tenant_key = 'default';
    END IF;

    IF NOT FOUND THEN
        RETURN json_build_object('error', 'tenant_not_found');
    END IF;

    -- 수수료율 결정: 개별 설정 > 테넌트 설정 > 기본값
    v_commission_percent := COALESCE(
        v_profile.commission_percent,
        v_tenant.commission_percent,
        10.0
    );

    -- 최소 수수료
    v_min_commission := COALESCE(v_tenant.min_commission_usd, 0);

    -- 수수료 계산
    v_commission_usd := (p_amount_usd * v_commission_percent / 100);

    -- 최소 수수료 적용
    IF v_commission_usd < v_min_commission THEN
        v_commission_usd := v_min_commission;
    END IF;

    RETURN json_build_object(
        'success', true,
        'tenant_key', v_tenant_key,
        'tenant_name', v_tenant.brand_name,
        'amount_usd', p_amount_usd,
        'commission_percent', v_commission_percent,
        'commission_usd', v_commission_usd,
        'net_usd', p_amount_usd - v_commission_usd,
        'min_commission_usd', v_min_commission
    );
END;
$$;

-- ─────────────────────────────────────────────
-- 8. 수수료 로그 기록 함수
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.log_commission(
    p_user_id UUID,
    p_transaction_type TEXT,
    p_amount_usd NUMERIC,
    p_commission_percent NUMERIC,
    p_commission_usd NUMERIC,
    p_metadata JSONB DEFAULT '{}'
)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_tenant_key TEXT;
    v_log_id UUID;
BEGIN
    -- 테넌트 키 조회
    SELECT tenant_key INTO v_tenant_key
    FROM public.profiles
    WHERE id = p_user_id;

    IF v_tenant_key IS NULL THEN
        v_tenant_key := 'default';
    END IF;

    -- 로그 기록
    INSERT INTO public.tenant_commission_logs (
        tenant_key, user_id, transaction_type,
        amount_usd, commission_percent, commission_usd, net_usd,
        metadata
    ) VALUES (
        v_tenant_key, p_user_id, p_transaction_type,
        p_amount_usd, p_commission_percent, p_commission_usd,
        p_amount_usd - p_commission_usd, p_metadata
    )
    RETURNING id INTO v_log_id;

    RETURN v_log_id;
END;
$$;

-- ─────────────────────────────────────────────
-- 9. 워터마크 관리 함수
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.get_tenant_watermark(p_user_id UUID)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_tenant public.tenant_configs%ROWTYPE;
    v_tenant_key TEXT;
BEGIN
    -- 테넌트 키 조회
    SELECT tenant_key INTO v_tenant_key
    FROM public.profiles
    WHERE id = p_user_id;

    IF v_tenant_key IS NULL THEN
        v_tenant_key := 'default';
    END IF;

    -- 테넌트 설정 조회
    SELECT * INTO v_tenant FROM public.tenant_configs
    WHERE tenant_key = v_tenant_key AND status = 'active';

    IF NOT FOUND THEN
        SELECT * INTO v_tenant FROM public.tenant_configs WHERE tenant_key = 'default';
    END IF;

    IF NOT FOUND OR v_tenant.watermark_enabled = false THEN
        RETURN json_build_object('enabled', false);
    END IF;

    RETURN json_build_object(
        'enabled', true,
        'position', v_tenant.watermark_position,
        'opacity', v_tenant.watermark_opacity,
        'url', v_tenant.watermark_url,
        'brand_name', v_tenant.brand_name
    );
END;
$$;

-- ─────────────────────────────────────────────
-- 10. 관리자용: 테넌트 수수료 설정 함수
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.admin_update_tenant_commission(
    p_tenant_key TEXT,
    p_commission_percent NUMERIC,
    p_min_commission NUMERIC DEFAULT 0
)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_is_admin BOOLEAN;
BEGIN
    -- 슈퍼어드민 권한 확인
    SELECT (raw_user_meta_data->>'is_superadmin')::boolean INTO v_is_admin
    FROM auth.users
    WHERE id = auth.uid();

    IF v_is_admin IS NULL OR v_is_admin = false THEN
        RETURN json_build_object('success', false, 'error', 'unauthorized');
    END IF;

    -- 테넌트 업데이트
    UPDATE public.tenant_configs
    SET
        commission_percent = p_commission_percent,
        min_commission_usd = p_min_commission,
        updated_at = NOW()
    WHERE tenant_key = p_tenant_key;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'tenant_not_found');
    END IF;

    RETURN json_build_object('success', true);
END;
$$;