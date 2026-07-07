-- =============================================================
-- Migration: Withdrawal RPC Row Lock Hotfix (AIR-0158G)
-- Description: Adds a Row Lock (FOR UPDATE) to prevent Race Conditions (Double Spend).
-- =============================================================

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
BEGIN
    -- 1. Get current authenticated user
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Unauthorized');
    END IF;

    -- 2. Basic Validation
    IF p_amount <= 0 THEN
        RETURN json_build_object('success', false, 'error', 'Amount must be greater than 0');
    END IF;

    IF p_wallet_address !~ '^0x[a-fA-F0-9]{40}$' THEN
        RETURN json_build_object('success', false, 'error', 'Invalid BEP20 wallet address');
    END IF;

    -- 3. ACQUIRE ROW LOCK TO PREVENT RACE CONDITIONS (Double Spend)
    -- This ensures concurrent requests from the same user run sequentially
    SELECT TRUE INTO v_profile_exists 
    FROM public.profiles 
    WHERE id = v_user_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'User profile not found');
    END IF;

    -- 4. Check Available Balance
    -- Because of the FOR UPDATE lock above, this balance calculation is 100% safe from concurrent modifications by the same user.
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
