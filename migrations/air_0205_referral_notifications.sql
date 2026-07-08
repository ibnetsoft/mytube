-- =============================================================
-- Migration: Referral Growth Loop Notification System (AIR-0205)
-- Description: Creates the user_notifications table and event triggers
-- =============================================================

-- 1. Create Notification Table
CREATE TABLE IF NOT EXISTS public.user_notifications (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('REFERRAL_JOIN', 'COMMISSION_EARNED', 'FIRST_REWARD', 'MILESTONE', 'SYSTEM_ALERT')),
    reference_id TEXT, -- To prevent duplicate notifications for the same event
    title TEXT,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_notifications_dedup 
ON public.user_notifications(user_id, type, reference_id) 
WHERE reference_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_unread 
ON public.user_notifications(user_id) 
WHERE is_read = false;

-- 2. Trigger Function: On New Referral Join & Milestones
CREATE OR REPLACE FUNCTION public.handle_referral_join()
RETURNS TRIGGER
SECURITY DEFINER
AS $$
DECLARE
    v_referral_count INT;
    v_milestone INT;
BEGIN
    -- Only trigger if referrer_id transitions from NULL to a value
    IF NEW.referrer_id IS NOT NULL AND (OLD.referrer_id IS NULL OR OLD.referrer_id != NEW.referrer_id) THEN
        
        -- A. Create 'REFERRAL_JOIN' Notification
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (
            NEW.referrer_id, 
            'REFERRAL_JOIN', 
            NEW.id::text, 
            'New Team Member', 
            'A new member joined your referral team!'
        ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;

        -- B. Check Milestones
        SELECT COUNT(*) INTO v_referral_count FROM public.profiles WHERE referrer_id = NEW.referrer_id;
        
        IF v_referral_count IN (5, 10, 50, 100) THEN
            INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
            VALUES (
                NEW.referrer_id, 
                'MILESTONE', 
                'milestone_' || v_referral_count::text, 
                'Referral Milestone Reached!', 
                'Congratulations! You have reached ' || v_referral_count::text || ' referrals.'
            ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;

    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_referral_join ON public.profiles;
CREATE TRIGGER trigger_referral_join
AFTER UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.handle_referral_join();

-- 3. Trigger Function: On Commission Earned & First Reward
CREATE OR REPLACE FUNCTION public.handle_commission_earned()
RETURNS TRIGGER
SECURITY DEFINER
AS $$
DECLARE
    v_commission_count INT;
BEGIN
    -- Only process approved commissions (or pending if you want immediate feedback)
    -- Assume we notify when amount > 0 and status is APPROVED
    IF NEW.status = 'APPROVED' AND (TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND OLD.status != 'APPROVED')) THEN
        
        -- A. Create 'COMMISSION_EARNED' Notification
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (
            NEW.beneficiary_user_id, 
            'COMMISSION_EARNED', 
            NEW.id::text, 
            'Commission Earned', 
            'You earned +' || NEW.amount::text || ' USDT from referral activity.'
        ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;

        -- B. Check First Reward
        SELECT COUNT(*) INTO v_commission_count FROM public.commissions WHERE beneficiary_user_id = NEW.beneficiary_user_id AND status = 'APPROVED';
        
        IF v_commission_count = 1 THEN
            INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
            VALUES (
                NEW.beneficiary_user_id, 
                'FIRST_REWARD', 
                'first_reward_' || NEW.beneficiary_user_id::text, 
                'First Earning!', 
                '🎉 Congratulations on your first earning!'
            ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;
        
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_commission_earned_insert ON public.commissions;
CREATE TRIGGER trigger_commission_earned_insert
AFTER INSERT ON public.commissions
FOR EACH ROW
EXECUTE FUNCTION public.handle_commission_earned();

DROP TRIGGER IF EXISTS trigger_commission_earned_update ON public.commissions;
CREATE TRIGGER trigger_commission_earned_update
AFTER UPDATE ON public.commissions
FOR EACH ROW
EXECUTE FUNCTION public.handle_commission_earned();

-- 4. Modify get_referral_dashboard_kpi to return notifications
-- We override the existing function to populate v_notifications
CREATE OR REPLACE FUNCTION get_referral_dashboard_kpi(p_user_id UUID)
RETURNS JSONB
SECURITY DEFINER
AS $$
DECLARE
    v_total_referrals INT := 0;
    v_level1_count INT := 0;
    v_level2_count INT := 0;
    v_active_members INT := 0;
    v_inactive_members INT := 0;
    v_today_commission NUMERIC := 0;
    v_month_commission NUMERIC := 0;
    v_pending_commission NUMERIC := 0;
    v_approved_commission NUMERIC := 0;
    v_withdrawable_balance NUMERIC := 0;
    v_withdrawn_total NUMERIC := 0;
    v_locked_withdrawals NUMERIC := 0;
    v_total_downline_jobs INT := 0;
    v_total_downline_commissions NUMERIC := 0;
    v_average_jobs_per_member NUMERIC := 0;
    v_average_commission_per_member NUMERIC := 0;
    v_expected_month_commission NUMERIC := 0;
    v_forecast_next_payout NUMERIC := 0;
    v_organization_health_score INT := 0;
    v_organization_health_grade TEXT := 'Dormant';
    v_notifications JSONB := '[]'::JSONB;
    
    v_today DATE := CURRENT_DATE;
    v_month_start DATE := date_trunc('month', CURRENT_DATE);
    v_days_in_month INT := extract(days from (date_trunc('month', CURRENT_DATE) + interval '1 month - 1 day'));
    v_day_of_month INT := extract(day from CURRENT_DATE);
BEGIN
    -- Security Validation
    IF auth.uid() != p_user_id THEN
        RAISE EXCEPTION 'Unauthorized: p_user_id does not match auth.uid()';
    END IF;

    -- Fetch unread notifications
    SELECT COALESCE(jsonb_agg(row_to_json(n)), '[]'::jsonb)
    INTO v_notifications
    FROM (
        SELECT id, type, title, message, created_at 
        FROM public.user_notifications 
        WHERE user_id = p_user_id AND is_read = false 
        ORDER BY created_at DESC 
        LIMIT 10
    ) n;

    -- CTE to get all descendants up to level 10
    WITH RECURSIVE downline AS (
        SELECT id, referrer_id, 1 AS level, last_sign_in_at
        FROM public.profiles
        WHERE referrer_id = p_user_id
        
        UNION ALL
        
        SELECT p.id, p.referrer_id, d.level + 1, p.last_sign_in_at
        FROM public.profiles p
        INNER JOIN downline d ON p.referrer_id = d.id
        WHERE d.level < 10
    )
    SELECT 
        COUNT(*),
        COUNT(*) FILTER (WHERE level = 1),
        COUNT(*) FILTER (WHERE level = 2),
        COUNT(*) FILTER (WHERE last_sign_in_at >= CURRENT_DATE - INTERVAL '7 days'),
        COUNT(*) FILTER (WHERE last_sign_in_at < CURRENT_DATE - INTERVAL '7 days' OR last_sign_in_at IS NULL)
    INTO 
        v_total_referrals, v_level1_count, v_level2_count, v_active_members, v_inactive_members
    FROM downline;

    -- User's Commission KPIs
    SELECT 
        COALESCE(SUM(amount) FILTER (WHERE created_at >= v_today::timestamp AND status = 'APPROVED'), 0),
        COALESCE(SUM(amount) FILTER (WHERE created_at >= v_month_start::timestamp AND status = 'APPROVED'), 0),
        COALESCE(SUM(amount) FILTER (WHERE status = 'PENDING'), 0),
        COALESCE(SUM(amount) FILTER (WHERE status = 'APPROVED'), 0)
    INTO 
        v_today_commission, v_month_commission, v_pending_commission, v_approved_commission
    FROM public.commissions
    WHERE beneficiary_user_id = p_user_id;

    -- User's Withdrawal KPIs
    SELECT 
        COALESCE(SUM(amount) FILTER (WHERE status IN ('REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED')), 0),
        COALESCE(SUM(amount) FILTER (WHERE status = 'COMPLETED'), 0)
    INTO 
        v_locked_withdrawals, v_withdrawn_total
    FROM public.withdrawal_requests
    WHERE user_id = p_user_id;

    v_withdrawable_balance := v_approved_commission - v_locked_withdrawals;

    -- Downline averages
    SELECT COALESCE(COUNT(*), 0), COALESCE(SUM(amount), 0)
    INTO v_total_downline_jobs, v_total_downline_commissions
    FROM public.commissions c
    WHERE c.beneficiary_user_id IN (SELECT id FROM public.profiles WHERE referrer_id = p_user_id) 
      AND c.created_at >= v_month_start::timestamp;

    IF v_active_members > 0 THEN
        v_average_jobs_per_member := ROUND((v_total_downline_jobs::numeric / v_active_members), 1);
        v_average_commission_per_member := ROUND((v_total_downline_commissions / v_active_members), 2);
    END IF;

    -- Forecasting
    IF v_day_of_month > 0 THEN
        v_expected_month_commission := ROUND((v_month_commission / v_day_of_month) * v_days_in_month, 2);
    END IF;
    v_forecast_next_payout := v_withdrawable_balance + v_pending_commission;

    -- Organization Health Calculation
    IF v_total_referrals > 0 THEN
        v_organization_health_score := ROUND((v_active_members::numeric / v_total_referrals::numeric) * 100);
    ELSE
        v_organization_health_score := 0;
    END IF;

    IF v_organization_health_score >= 90 THEN v_organization_health_grade := 'Excellent';
    ELSIF v_organization_health_score >= 70 THEN v_organization_health_grade := 'Healthy';
    ELSIF v_organization_health_score >= 40 THEN v_organization_health_grade := 'Warning';
    ELSE v_organization_health_grade := 'Critical';
    END IF;

    RETURN jsonb_build_object(
        'total_referrals', v_total_referrals,
        'level1_count', v_level1_count,
        'level2_count', v_level2_count,
        'organization_size', v_total_referrals,
        'active_members', v_active_members,
        'inactive_members', v_inactive_members,
        'today_commission', v_today_commission,
        'month_commission', v_month_commission,
        'pending_commission', v_pending_commission,
        'approved_commission', v_approved_commission,
        'withdrawable_balance', v_withdrawable_balance,
        'withdrawn_total', v_withdrawn_total,
        'expected_month_commission', v_expected_month_commission,
        'forecast_next_payout', v_forecast_next_payout,
        'organization_health_score', v_organization_health_score,
        'organization_health_grade', v_organization_health_grade,
        'notifications', v_notifications
    );
END;
$$ LANGUAGE plpgsql;
