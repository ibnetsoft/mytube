-- =============================================================
-- Migration: Missing Referral System Schema & Helpers
-- Supabase 대시보드 > SQL Editor 에서 실행하세요.
-- =============================================================

-- 1. profiles 테이블에 추천인 필드가 없는 경우 추가
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS my_referral_code TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS referred_by TEXT;

-- 2. 추천 수당 지급 내역 기록 테이블 생성
CREATE TABLE IF NOT EXISTS public.referral_rewards_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    referred_user_id  UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount            NUMERIC NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_referral_rewards_referrer ON public.referral_rewards_log(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referral_rewards_referred ON public.referral_rewards_log(referred_user_id);

-- RLS 활성화
ALTER TABLE public.referral_rewards_log ENABLE ROW LEVEL SECURITY;

-- RLS 정책: 유저는 자신의 추천 보상 내역만 조회 가능
DROP POLICY IF EXISTS "referral_rewards_self_read" ON public.referral_rewards_log;
CREATE POLICY "referral_rewards_self_read" ON public.referral_rewards_log
    FOR SELECT USING (auth.uid() = referrer_id);


-- 3. USDT 잔액 증가용 DB 함수 생성 (RPC)
CREATE OR REPLACE FUNCTION public.increment_usdt_balance(uid UUID, amount_to_add NUMERIC)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE public.profiles
    SET usdt_balance = COALESCE(usdt_balance, 0) + amount_to_add,
        updated_at = NOW()
    WHERE id = uid;
END;
$$;
