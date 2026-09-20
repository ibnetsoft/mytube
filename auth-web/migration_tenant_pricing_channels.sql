-- =============================================================
-- 테넌트 세팅비 및 채널별 구독 요금제 마이그레이션
-- Supabase SQL Editor에서 실행하세요.
-- =============================================================

-- 1. tenant_configs 테이블에 세팅비, 채널당 단가, 최대 채널 수 컬럼 추가
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenant_configs' AND column_name = 'setup_fee_usd'
    ) THEN
        ALTER TABLE public.tenant_configs ADD COLUMN setup_fee_usd NUMERIC(10,2) DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenant_configs' AND column_name = 'price_per_channel_usd'
    ) THEN
        ALTER TABLE public.tenant_configs ADD COLUMN price_per_channel_usd NUMERIC(10,2) DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenant_configs' AND column_name = 'max_channels'
    ) THEN
        ALTER TABLE public.tenant_configs ADD COLUMN max_channels INT DEFAULT 5;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenant_configs' AND column_name = 'currency'
    ) THEN
        ALTER TABLE public.tenant_configs ADD COLUMN currency TEXT DEFAULT 'USD';
    END IF;

    RAISE NOTICE '테넌트 요금 및 채널 한도 컬럼이 추가되었습니다.';
END $$;
