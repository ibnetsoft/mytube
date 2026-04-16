-- =============================================================
-- Piccadilly Token System Migration
-- =============================================================

-- 1. profiles 테이블에 토큰 잔액 필드 추가
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS token_balance BIGINT NOT NULL DEFAULT 50000; -- 기본 5만 토큰 지급

-- 2. 토큰 트랜잭션 기록 테이블 생성
CREATE TABLE IF NOT EXISTS public.token_transactions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount            BIGINT NOT NULL,           -- 충전(+), 차감(-)
    transaction_type  TEXT NOT NULL,             -- 'RECHARGE', 'USAGE', 'REFUND'
    description       TEXT,                      -- 상세 내역
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_token_transactions_user ON public.token_transactions(user_id, created_at DESC);

-- 3. 라이선스 검증 함수 업데이트 (token_balance 포함)
CREATE OR REPLACE FUNCTION public.verify_license(p_license_key TEXT)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_license  public.user_licenses%ROWTYPE;
    v_profile  public.profiles%ROWTYPE;
BEGIN
    SELECT * INTO v_license
    FROM public.user_licenses
    WHERE license_key = p_license_key AND is_active = TRUE
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN json_build_object('valid', FALSE, 'reason', 'invalid_key');
    END IF;

    IF v_license.expires_at IS NOT NULL AND v_license.expires_at < NOW() THEN
        RETURN json_build_object('valid', FALSE, 'reason', 'expired');
    END IF;

    SELECT * INTO v_profile FROM public.profiles WHERE id = v_license.user_id;

    RETURN json_build_object(
        'valid',           TRUE,
        'user_id',         v_license.user_id,
        'membership_tier', v_profile.membership_tier,
        'video_limit',     v_profile.video_limit,
        'current_usage',   v_profile.current_usage,
        'token_balance',   v_profile.token_balance
    );
END;
$$;

-- 4. 토큰 차감 전용 함수 생성 (AI 작업 성공 시 호출)
CREATE OR REPLACE FUNCTION public.deduct_tokens(p_user_id UUID, p_amount BIGINT, p_description TEXT)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_current_balance BIGINT;
BEGIN
    -- 현재 잔액 확인
    SELECT token_balance INTO v_current_balance FROM public.profiles WHERE id = p_user_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', FALSE, 'reason', 'user_not_found');
    END IF;

    -- 잔액 업데이트
    UPDATE public.profiles
    SET token_balance = token_balance - p_amount,
        updated_at = NOW()
    WHERE id = p_user_id;

    -- 트랜잭션 기록
    INSERT INTO public.token_transactions (user_id, amount, transaction_type, description)
    VALUES (p_user_id, -p_amount, 'USAGE', p_description);

    RETURN json_build_object('success', TRUE, 'new_balance', v_current_balance - p_amount);
END;
$$;

-- 5. 관리자용 토큰 충전 함수 생성
CREATE OR REPLACE FUNCTION public.recharge_tokens(p_user_id UUID, p_amount BIGINT, p_description TEXT)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE public.profiles
    SET token_balance = token_balance + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id;

    INSERT INTO public.token_transactions (user_id, amount, transaction_type, description)
    VALUES (p_user_id, p_amount, 'RECHARGE', p_description);

    RETURN json_build_object('success', TRUE);
END;
$$;
