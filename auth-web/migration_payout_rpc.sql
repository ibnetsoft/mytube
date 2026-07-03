-- migration_payout_rpc.sql
-- Create RPC function to process referral payouts atomically

CREATE OR REPLACE FUNCTION public.process_referral_payout(p_commission_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_commission RECORD;
    v_updated_rows INT;
BEGIN
    -- 1. Find the pending commission and lock it
    SELECT * INTO v_commission 
    FROM public.referral_commissions 
    WHERE id = p_commission_id AND status = 'pending'
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Commission not found or not in pending status');
    END IF;

    -- 2. Update the commission status to paid
    UPDATE public.referral_commissions 
    SET status = 'paid', paid_at = NOW(), updated_at = NOW()
    WHERE id = p_commission_id;

    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    IF v_updated_rows = 0 THEN
        RETURN jsonb_build_object('success', false, 'error', 'Failed to update commission status');
    END IF;

    -- 3. Increase beneficiary usdt_balance
    UPDATE public.profiles
    SET usdt_balance = COALESCE(usdt_balance, 0) + v_commission.commission_tokens,
        updated_at = NOW()
    WHERE id = v_commission.beneficiary_id;

    RETURN jsonb_build_object(
        'success', true, 
        'commission_id', p_commission_id, 
        'amount_paid', v_commission.commission_tokens,
        'beneficiary_id', v_commission.beneficiary_id
    );
EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$$;
