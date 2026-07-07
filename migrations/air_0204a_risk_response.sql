-- =============================================================
-- Migration: Automated Risk Response System (AIR-0204)
-- Description: State tracking, response automation, and guards
-- =============================================================

-- 1. Create Risk State Table
CREATE TABLE IF NOT EXISTS public.user_risk_state (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    risk_level public.risk_score NOT NULL DEFAULT 'LOW',
    is_under_review BOOLEAN NOT NULL DEFAULT false,
    withdrawal_blocked BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE public.user_risk_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Superadmins can manage risk state"
    ON public.user_risk_state
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );

-- Users can read their own state
CREATE POLICY "Users can view own risk state"
    ON public.user_risk_state
    FOR SELECT
    USING (user_id = auth.uid());


-- 2. Trigger on Risk Flags Insert
CREATE OR REPLACE FUNCTION public.handle_new_risk_flag()
RETURNS TRIGGER AS $$
DECLARE
    v_existing public.user_risk_state;
    v_new_level public.risk_score;
    v_under_review BOOLEAN;
    v_blocked BOOLEAN;
BEGIN
    -- Determine impact based on new flag's score
    v_under_review := (NEW.score IN ('HIGH', 'CRITICAL'));
    v_blocked := (NEW.score = 'CRITICAL');

    -- Get or lock existing state
    SELECT * INTO v_existing FROM public.user_risk_state WHERE user_id = NEW.user_id FOR UPDATE;

    IF v_existing.user_id IS NULL THEN
        -- Insert new state
        INSERT INTO public.user_risk_state (user_id, risk_level, is_under_review, withdrawal_blocked)
        VALUES (NEW.user_id, NEW.score, v_under_review, v_blocked);
    ELSE
        -- Postgres ENUMs can be compared if defined in ascending order (LOW, MEDIUM, HIGH, CRITICAL).
        -- GREATEST works reliably here.
        SELECT GREATEST(v_existing.risk_level, NEW.score) INTO v_new_level;
        
        UPDATE public.user_risk_state 
        SET 
            risk_level = v_new_level,
            -- Only escalate restrictions, don't clear existing ones automatically
            is_under_review = v_existing.is_under_review OR v_under_review,
            withdrawal_blocked = v_existing.withdrawal_blocked OR v_blocked,
            updated_at = now()
        WHERE user_id = NEW.user_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trigger_new_risk_flag ON public.risk_flags;
CREATE TRIGGER trigger_new_risk_flag
AFTER INSERT ON public.risk_flags
FOR EACH ROW
EXECUTE FUNCTION public.handle_new_risk_flag();


-- 3. Update request_withdrawal RPC to inject the guard
CREATE OR REPLACE FUNCTION public.request_withdrawal(
    p_amount NUMERIC,
    p_wallet_address TEXT
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_available NUMERIC;
    v_new_id UUID;
    v_profile_exists BOOLEAN;
    v_risk_state public.user_risk_state;
BEGIN
    -- 1. Get current authenticated user
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Unauthorized');
    END IF;

    -- [NEW] RISK GUARD
    SELECT * INTO v_risk_state FROM public.user_risk_state WHERE user_id = v_user_id;
    -- COALESCE handles the case where the user_risk_state row does not exist (null bypass prevention)
    IF COALESCE(v_risk_state.withdrawal_blocked, false) = true THEN
        RETURN json_build_object('success', false, 'error', 'Account under review');
    END IF;

    -- 2. Basic Validation
    IF p_amount <= 0 THEN
        RETURN json_build_object('success', false, 'error', 'Amount must be greater than 0');
    END IF;

    IF p_wallet_address !~ '^0x[a-fA-F0-9]{40}$' THEN
        RETURN json_build_object('success', false, 'error', 'Invalid BEP20 wallet address');
    END IF;

    -- 3. ACQUIRE ROW LOCK TO PREVENT RACE CONDITIONS (Double Spend)
    SELECT TRUE INTO v_profile_exists 
    FROM public.profiles 
    WHERE id = v_user_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'User profile not found');
    END IF;

    -- 4. Check Available Balance
    v_available := public.get_available_withdrawal_balance(v_user_id);
    IF p_amount > v_available THEN
        RETURN json_build_object(
            'success', false, 
            'error', 'Insufficient balance',
            'available_balance', v_available,
            'requested_amount', p_amount
        );
    END IF;

    -- 5. Insert Withdrawal Request
    INSERT INTO public.withdrawal_requests (
        user_id, amount, currency, network, wallet_address, status
    ) VALUES (
        v_user_id, p_amount, 'USDT', 'BEP20', p_wallet_address, 'REQUESTED'
    ) RETURNING id INTO v_new_id;

    RETURN json_build_object(
        'success', true,
        'withdrawal_id', v_new_id,
        'amount', p_amount,
        'status', 'REQUESTED',
        'remaining_balance', v_available - p_amount
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 4. Admin Override RPC
CREATE OR REPLACE FUNCTION admin_override_user_risk(
    p_admin_id UUID, 
    p_target_user_id UUID, 
    p_reason TEXT
)
RETURNS JSONB AS $$
DECLARE
    v_existing public.user_risk_state;
BEGIN
    -- Auth verification
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN
        RAISE EXCEPTION 'Unauthorized';
    END IF;

    SELECT * INTO v_existing FROM public.user_risk_state WHERE user_id = p_target_user_id FOR UPDATE;

    IF v_existing.user_id IS NULL THEN
        RAISE EXCEPTION 'User risk state not found';
    END IF;

    -- Update state (Keep risk_level unchanged)
    UPDATE public.user_risk_state 
    SET 
        is_under_review = false, 
        withdrawal_blocked = false, 
        updated_at = now()
    WHERE user_id = p_target_user_id;

    -- Audit
    INSERT INTO public.admin_audit_logs (
        admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason
    ) VALUES (
        p_admin_id,
        'OVERRIDE_RISK_STATE',
        'USER',
        p_target_user_id,
        jsonb_build_object(
            'override_type', 'MANUAL_RELEASE',
            'is_under_review', v_existing.is_under_review, 
            'withdrawal_blocked', v_existing.withdrawal_blocked, 
            'risk_level', v_existing.risk_level
        ),
        jsonb_build_object(
            'override_type', 'MANUAL_RELEASE',
            'is_under_review', false, 
            'withdrawal_blocked', false, 
            'risk_level', v_existing.risk_level
        ),
        p_reason
    );

    RETURN jsonb_build_object('success', true, 'user_id', p_target_user_id, 'status', 'RESTRICTIONS_CLEARED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
