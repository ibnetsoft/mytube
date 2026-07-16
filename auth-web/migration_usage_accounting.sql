-- =============================================================
-- [AIR-0225B] 토큰 과금 모델 전환: 잔액 차감(debit) -> 사용량 누적(metering)
-- =============================================================
-- 정책 변경:
--   1) 회원가입/승인 시 토큰을 지급하지 않는다 (스타터 5만·승인 100만 폐지).
--   2) AI 작업 시 잔액을 깎지 않고 누적 사용량(used_tokens)만 쌓는다.
--   3) 토큰이 없다는 이유로 플랫폼 이용이 막히지 않는다 (게이트 없음).
-- 이 마이그레이션은 idempotent 하며, 기존 계정의 token_balance 값은 건드리지
-- 않는다 (관리자가 수동 지급한 잔액은 그대로 보존). 새 가입분만 0으로 시작한다.

-- 1. 누적 사용량 컬럼 추가 (양수로 계속 증가)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS used_tokens BIGINT NOT NULL DEFAULT 0;

-- 2. 신규 가입 시 스타터 토큰 지급 폐지 (기본값 50000 -> 0)
--    * 기존 row 값은 바꾸지 않는다. 컬럼 DEFAULT만 조정해 앞으로의 가입분에 적용.
ALTER TABLE public.profiles
    ALTER COLUMN token_balance SET DEFAULT 0;

-- 3. 사용량 누적 함수 (deduct_tokens 대체). 잔액을 절대 차감하지 않으며,
--    잔액 부족을 이유로 실패하지 않는다 - 항상 success 를 반환한다.
--    token_transactions 원장은 기존과 동일하게 USAGE/음수(amount = -사용량)로
--    적재해 과거 기록과 호환을 유지한다.
CREATE OR REPLACE FUNCTION public.record_token_usage(p_user_id UUID, p_amount BIGINT, p_description TEXT)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_used BIGINT;
BEGIN
    UPDATE public.profiles
    SET used_tokens = COALESCE(used_tokens, 0) + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING used_tokens INTO v_used;

    IF NOT FOUND THEN
        RETURN json_build_object('success', FALSE, 'reason', 'user_not_found');
    END IF;

    INSERT INTO public.token_transactions (user_id, amount, transaction_type, description)
    VALUES (p_user_id, -p_amount, 'USAGE', p_description);

    RETURN json_build_object('success', TRUE, 'used_tokens', v_used);
END;
$$;
