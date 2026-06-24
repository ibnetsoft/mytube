-- =============================================================
-- 출금 수수료 연동 마이그레이션
-- Supabase SQL Editor에서 실행하세요.
-- =============================================================

-- ─────────────────────────────────────────────
-- 1. withdrawals 테이블에 수수료 컬럼 추가
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'withdrawals' AND column_name = 'commission_percent'
    ) THEN
        ALTER TABLE public.withdrawals ADD COLUMN commission_percent NUMERIC(5,2);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'withdrawals' AND column_name = 'commission_usd'
    ) THEN
        ALTER TABLE public.withdrawals ADD COLUMN commission_usd NUMERIC(18,6) DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'withdrawals' AND column_name = 'net_usd'
    ) THEN
        ALTER TABLE public.withdrawals ADD COLUMN net_usd NUMERIC(18,6);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'withdrawals' AND column_name = 'tenant_key'
    ) THEN
        ALTER TABLE public.withdrawals ADD COLUMN tenant_key TEXT;
    END IF;

    RAISE NOTICE '수수료 컬럼이 withdrawals 테이블에 추가되었습니다.';
END $$;

-- ─────────────────────────────────────────────
-- 2. 출금 승인/완료 시 수수료 자동 계산 함수
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.process_withdrawal_commission(
    p_withdrawal_id UUID
)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_withdrawal public.withdrawals%ROWTYPE;
    v_commission_result JSON;
    v_log_id UUID;
    v_user_id UUID;
    v_amount NUMERIC;
    v_commission_percent NUMERIC(5,2);
    v_commission_usd NUMERIC(18,6);
    v_net_usd NUMERIC(18,6);
BEGIN
    -- 출금 정보 조회
    SELECT * INTO v_withdrawal FROM public.withdrawals WHERE id = p_withdrawal_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'withdrawal_not_found');
    END IF;

    v_user_id := v_withdrawal.user_id;
    v_amount := v_withdrawal.amount;

    -- 수수료 계산
    SELECT * INTO v_commission_result
    FROM public.calculate_commission(v_user_id, v_amount);

    IF v_commission_result->>'success' != 'true' THEN
        RETURN v_commission_result;
    END IF;

    v_commission_percent := (v_commission_result->>'commission_percent')::NUMERIC(5,2);
    v_commission_usd := (v_commission_result->>'commission_usd')::NUMERIC(18,6);
    v_net_usd := (v_commission_result->>'net_usd')::NUMERIC(18,6);

    -- 출금 정보 업데이트
    UPDATE public.withdrawals
    SET
        commission_percent = v_commission_percent,
        commission_usd = v_commission_usd,
        net_usd = v_net_usd,
        tenant_key = v_commission_result->>'tenant_key'
    WHERE id = p_withdrawal_id;

    -- 수수료 로깅 (pending 상태일 때는 로깅, completed 상태일 때는 확정)
    IF v_withdrawal.status = 'pending' THEN
        INSERT INTO public.tenant_commission_logs (
            tenant_key, user_id, transaction_type,
            amount_usd, commission_percent, commission_usd, net_usd,
            transaction_id, metadata
        ) VALUES (
            v_commission_result->>'tenant_key',
            v_user_id,
            'commission',
            v_amount,
            v_commission_percent,
            v_commission_usd,
            v_net_usd,
            p_withdrawal_id::TEXT,
            json_build_object('withdrawal_id', p_withdrawal_id, 'pending', true)
        ) RETURNING id INTO v_log_id;
    ELSIF v_withdrawal.status = 'completed' THEN
        -- 완료 시 확정 로그
        INSERT INTO public.tenant_commission_logs (
            tenant_key, user_id, transaction_type,
            amount_usd, commission_percent, commission_usd, net_usd,
            transaction_id, metadata
        ) VALUES (
            v_commission_result->>'tenant_key',
            v_user_id,
            'commission',
            v_amount,
            v_commission_percent,
            v_commission_usd,
            v_net_usd,
            p_withdrawal_id::TEXT,
            json_build_object('withdrawal_id', p_withdrawal_id, 'completed', true)
        );
    END IF;

    RETURN json_build_object(
        'success', true,
        'commission_percent', v_commission_percent,
        'commission_usd', v_commission_usd,
        'net_usd', v_net_usd,
        'log_id', v_log_id
    );
END;
$$;

-- ─────────────────────────────────────────────
-- 3. profiles에 is_superadmin 컬럼 추가 (슈퍼어드민 설정용)
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'is_superadmin'
    ) THEN
        ALTER TABLE public.profiles ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE;
    END IF;

    RAISE NOTICE 'is_superadmin 컬럼이 profiles 테이블에 추가되었습니다.';
END $$;

-- 기존 최고 관리자 이메일에 슈퍼어드민 권한 부여
UPDATE public.profiles
SET is_superadmin = TRUE
WHERE email IN ('ejsh0519@naver.com', 'admin@airstudio.com');

-- ─────────────────────────────────────────────
-- 4. RLS 정책 업데이트 (슈퍼어드민만 출금 승인 가능)
-- ─────────────────────────────────────────────
DROP POLICY IF EXISTS "withdrawals_admin_update" ON public.withdrawals;
CREATE POLICY "withdrawals_admin_update" ON public.withdrawals
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );

DROP POLICY IF EXISTS "withdrawals_admin_insert" ON public.withdrawals;
CREATE POLICY "withdrawals_admin_insert" ON public.withdrawals
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );