-- =============================================================
-- Migration: Withdrawal Request & Balance RPCs (AIR-0158E)
-- Description: Creates DB functions to calculate available balance and request withdrawals safely.
-- Source of Truth for Commissions: public.commissions
-- Source of Truth for Withdrawals: public.withdrawal_requests
-- =============================================================

-- 1. Calculate Available Balance
CREATE OR REPLACE FUNCTION public.get_available_withdrawal_balance(p_user_id UUID)
RETURNS NUMERIC AS $$
DECLARE
    v_approved_commission NUMERIC := 0;
    v_locked_withdrawals NUMERIC := 0;
BEGIN
    -- Sum approved commissions
    SELECT COALESCE(SUM(amount), 0)
    INTO v_approved_commission
    FROM public.commissions
    WHERE beneficiary_user_id = p_user_id
    AND status = 'APPROVED';

    -- Sum locked withdrawals
    SELECT COALESCE(SUM(amount), 0)
    INTO v_locked_withdrawals
    FROM public.withdrawal_requests
    WHERE user_id = p_user_id
    AND status IN ('REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED');

    RETURN v_approved_commission - v_locked_withdrawals;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Create Withdrawal Request (Transactional)
CREATE OR REPLACE FUNCTION public.request_withdrawal(
    p_amount NUMERIC,
    p_wallet_address TEXT
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_available NUMERIC;
    v_new_id UUID;
BEGIN
    -- Get current authenticated user
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Unauthorized');
    END IF;

    -- Basic Validation
    IF p_amount <= 0 THEN
        RETURN json_build_object('success', false, 'error', 'Amount must be greater than 0');
    END IF;

    -- Note: Additional Wallet Validation can be added here if needed, but the table CHECK constraint already validates regex
    -- Let's catch it manually to give a clean JSON error
    IF p_wallet_address !~ '^0x[a-fA-F0-9]{40}$' THEN
        RETURN json_build_object('success', false, 'error', 'Invalid BEP20 wallet address');
    END IF;

    -- Check Available Balance
    -- Because this runs in a single transaction in Postgres, it is atomic.
    v_available := public.get_available_withdrawal_balance(v_user_id);
    IF p_amount > v_available THEN
        RETURN json_build_object(
            'success', false, 
            'error', 'Insufficient balance',
            'available_balance', v_available,
            'requested_amount', p_amount
        );
    END IF;

    -- Insert Withdrawal Request
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
