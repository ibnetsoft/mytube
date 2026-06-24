-- =============================================================
-- 지갑 및 출금 관련 테이블 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.
-- =============================================================

-- ─────────────────────────────────────────────
-- 1. profiles 테이블에 지갑 관련 컬럼 추가
-- ─────────────────────────────────────────────
DO $$
BEGIN
    -- wallet_address 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'wallet_address'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN wallet_address TEXT;
    END IF;

    -- usdt_balance 컬럼 추가
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'usdt_balance'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN usdt_balance NUMERIC(18,6) DEFAULT 0;
    END IF;

    -- 컬럼이 추가되었는지 확인
    RAISE NOTICE '지갑 관련 컬럼이 profiles 테이블에 추가되었습니다.';
END $$;

-- ─────────────────────────────────────────────
-- 2. withdrawals 테이블 생성
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.withdrawals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount NUMERIC(18,6) NOT NULL,
    dest_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected' | 'completed'
    tx_hash TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON public.withdrawals(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON public.withdrawals(status, created_at DESC);

-- ─────────────────────────────────────────────
-- 3. RLS (Row Level Security) 정책
-- ─────────────────────────────────────────────
ALTER TABLE public.withdrawals ENABLE ROW LEVEL SECURITY;

-- 본인 출금 내역만 읽기
DROP POLICY IF EXISTS "withdrawals_self_read" ON public.withdrawals;
CREATE POLICY "withdrawals_self_read" ON public.withdrawals
    FOR SELECT USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- 4. 프로젝트 데이터 확인을 위한 쿼리 (테스트용)
-- ─────────────────────────────────────────────

-- ejsh0519@naver.com의 프로필 정보 확인
-- SELECT id, email, wallet_address, usdt_balance, membership_tier
-- FROM public.profiles
-- WHERE email = 'ejsh0519@naver.com';

-- ejsh0519@naver.com의 프로젝트 메타데이터 확인
-- SELECT id, sync_id, name, topic, status, language, created_at
-- FROM public.desktop_project_metadata
-- WHERE employee_email = 'ejsh0519@naver.com'
-- ORDER BY created_at DESC
-- LIMIT 10;

-- ejsh0519@naver.com의 출금 내역 확인
-- SELECT id, amount, dest_address, status, created_at
-- FROM public.withdrawals
-- WHERE user_id = (
--     SELECT id FROM public.profiles WHERE email = 'ejsh0519@naver.com'
-- )
-- ORDER BY created_at DESC;