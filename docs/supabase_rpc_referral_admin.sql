-- docs/supabase_rpc_referral_admin.sql
-- Run this in Supabase SQL Editor to enable database-side aggregation for Referrals

-- 1. Get KPI for a specific user (Dashboard & Admin Tree)
CREATE OR REPLACE FUNCTION get_referral_user_kpi(uid UUID)
RETURNS JSON AS $$
DECLARE
    pending_comm NUMERIC := 0;
    approved_comm NUMERIC := 0;
    total_withdrawn NUMERIC := 0;
    this_month_comm NUMERIC := 0;
BEGIN
    SELECT 
        COALESCE(SUM(CASE WHEN status IN ('PENDING', 'WAITING') AND commission_type != 'WITHDRAWAL' THEN commission_tokens ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status IN ('APPROVED', 'COMPLETED', 'PAID') AND commission_type != 'WITHDRAWAL' THEN commission_tokens ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status IN ('APPROVED', 'COMPLETED', 'PAID') AND commission_type = 'WITHDRAWAL' THEN ABS(commission_tokens) ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status IN ('APPROVED', 'COMPLETED', 'PAID') AND commission_type != 'WITHDRAWAL' AND created_at >= date_trunc('month', current_date) THEN commission_tokens ELSE 0 END), 0)
    INTO pending_comm, approved_comm, total_withdrawn, this_month_comm
    FROM referral_commissions
    WHERE beneficiary_id = uid;

    RETURN json_build_object(
        'pendingCommission', pending_comm,
        'approvedCommission', approved_comm,
        'totalWithdrawn', total_withdrawn,
        'thisMonthCommission', this_month_comm
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 2. Get Global Admin Stats
CREATE OR REPLACE FUNCTION get_admin_global_referral_stats()
RETURNS JSON AS $$
DECLARE
    pending_withdraw NUMERIC := 0;
    today_withdraw NUMERIC := 0;
    total_paid NUMERIC := 0;
    pending_comm NUMERIC := 0;
    approved_comm NUMERIC := 0;
    total_members INT := 0;
    l1_members INT := 0;
    l2_members INT := 0;
BEGIN
    -- Commission Stats
    SELECT 
        COALESCE(SUM(CASE WHEN commission_type = 'WITHDRAWAL' AND status = 'PENDING' THEN ABS(commission_tokens) ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN commission_type = 'WITHDRAWAL' AND created_at >= current_date THEN ABS(commission_tokens) ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN commission_type = 'WITHDRAWAL' AND status IN ('APPROVED', 'COMPLETED', 'PAID') THEN ABS(commission_tokens) ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN commission_type != 'WITHDRAWAL' AND status IN ('PENDING', 'WAITING') THEN commission_tokens ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN commission_type != 'WITHDRAWAL' AND status IN ('APPROVED', 'COMPLETED', 'PAID') THEN commission_tokens ELSE 0 END), 0)
    INTO pending_withdraw, today_withdraw, total_paid, pending_comm, approved_comm
    FROM referral_commissions;

    -- Member Stats (Approximate count for speed if very large, but exact here)
    SELECT count(*) INTO total_members FROM profiles;
    SELECT count(*) INTO l1_members FROM profiles WHERE referred_by IS NOT NULL;
    
    -- Level 2 calculation can be heavy globally, so we estimate or count if indexed
    -- For simplicity, we just return the counts
    
    RETURN json_build_object(
        'pendingWithdrawals', pending_withdraw,
        'todayWithdrawals', today_withdraw,
        'totalPaid', total_paid,
        'pendingCommission', pending_comm,
        'approvedCommission', approved_comm,
        'totalMembers', total_members,
        'level1Members', l1_members,
        'level2Members', 0
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
