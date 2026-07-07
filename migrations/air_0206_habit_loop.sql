-- =============================================================
-- Migration: Retention & Habit Loop System (AIR-0206)
-- Description: Tracks daily user activities, calculates streaks, and triggers notifications.
-- =============================================================

-- 1. Create Table
CREATE TABLE IF NOT EXISTS public.user_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    activity_date DATE NOT NULL DEFAULT CURRENT_DATE,
    jobs_completed INT NOT NULL DEFAULT 0,
    referrals_added INT NOT NULL DEFAULT 0,
    current_streak INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique constraint for UPSERT
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_activity_user_date 
ON public.user_activity(user_id, activity_date);

-- 2. Trigger Function for Activity & Streak UPSERT
CREATE OR REPLACE FUNCTION public.handle_user_activity()
RETURNS TRIGGER
SECURITY DEFINER
AS $$
DECLARE
    v_today DATE := CURRENT_DATE;
    v_yesterday DATE := CURRENT_DATE - INTERVAL '1 day';
    v_streak INT := 1;
    v_yesterday_streak INT := 0;
    v_old_jobs INT := 0;
    v_old_referrals INT := 0;
    v_new_jobs INT := 0;
    v_new_referrals INT := 0;
    v_target_user_id UUID;
    v_is_job BOOLEAN := false;
    v_is_referral BOOLEAN := false;
BEGIN
    -- Determine the target user and event type
    IF TG_TABLE_NAME = 'worker_jobs' THEN
        -- Job Completed
        IF NEW.status = 'COMPLETED' AND (OLD.status IS NULL OR OLD.status != 'COMPLETED') AND NEW.user_id IS NOT NULL THEN
            v_target_user_id := NEW.user_id;
            v_is_job := true;
        ELSE
            RETURN NEW;
        END IF;
    ELSIF TG_TABLE_NAME = 'profiles' THEN
        -- Referral Added
        IF NEW.referrer_id IS NOT NULL AND (OLD.referrer_id IS NULL OR OLD.referrer_id != NEW.referrer_id) THEN
            v_target_user_id := NEW.referrer_id;
            v_is_referral := true;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    -- Look up yesterday's streak
    SELECT current_streak INTO v_yesterday_streak 
    FROM public.user_activity 
    WHERE user_id = v_target_user_id AND activity_date = v_yesterday;

    IF FOUND THEN
        v_streak := v_yesterday_streak + 1;
    ELSE
        v_streak := 1;
    END IF;

    -- Perform Upsert (Atomically lock row if exists)
    INSERT INTO public.user_activity (user_id, activity_date, jobs_completed, referrals_added, current_streak)
    VALUES (
        v_target_user_id, 
        v_today, 
        CASE WHEN v_is_job THEN 1 ELSE 0 END, 
        CASE WHEN v_is_referral THEN 1 ELSE 0 END, 
        v_streak
    )
    ON CONFLICT (user_id, activity_date) DO UPDATE 
    SET 
        jobs_completed = user_activity.jobs_completed + CASE WHEN v_is_job THEN 1 ELSE 0 END,
        referrals_added = user_activity.referrals_added + CASE WHEN v_is_referral THEN 1 ELSE 0 END,
        updated_at = NOW()
    RETURNING jobs_completed - CASE WHEN v_is_job THEN 1 ELSE 0 END, -- OLD jobs
              referrals_added - CASE WHEN v_is_referral THEN 1 ELSE 0 END, -- OLD referrals
              jobs_completed, -- NEW jobs
              referrals_added, -- NEW referrals
              current_streak
    INTO v_old_jobs, v_old_referrals, v_new_jobs, v_new_referrals, v_streak;

    -- Check Notifications
    
    -- 1. First Job of the day
    IF v_is_job AND v_old_jobs = 0 AND v_new_jobs = 1 THEN
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (v_target_user_id, 'FIRST_REWARD', 'first_job_' || v_today::text, 'First Job Completed!', 'Great start! You completed your first job of the day.')
        ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
    END IF;

    -- 2. First Referral of the day
    IF v_is_referral AND v_old_referrals = 0 AND v_new_referrals = 1 THEN
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (v_target_user_id, 'FIRST_REWARD', 'first_ref_' || v_today::text, 'First Referral Added!', 'Awesome! You brought in a new member today.')
        ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
    END IF;

    -- 3. Streak Milestones (Only if it's the first activity of the day setting the streak)
    -- This happens when v_old_jobs = 0 AND v_old_referrals = 0
    IF (v_old_jobs = 0 AND v_old_referrals = 0) THEN
        IF v_streak = 3 THEN
            INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
            VALUES (v_target_user_id, 'MILESTONE', 'streak_3_' || v_today::text, '3-Day Streak! 🔥', 'You are on fire! 3 days of consecutive activity.')
            ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        ELSIF v_streak = 7 THEN
            INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
            VALUES (v_target_user_id, 'MILESTONE', 'streak_7_' || v_today::text, '1 Week Streak! 🔥', 'Amazing! You have been active for a full week.')
            ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        ELSIF v_streak = 30 THEN
            INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
            VALUES (v_target_user_id, 'MILESTONE', 'streak_30_' || v_today::text, '30-Day Streak! 🌟', 'Incredible dedication! A 30-day streak!')
            ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Attach Triggers

DROP TRIGGER IF EXISTS trigger_user_activity_job ON public.worker_jobs;
CREATE TRIGGER trigger_user_activity_job
AFTER UPDATE ON public.worker_jobs
FOR EACH ROW
EXECUTE FUNCTION public.handle_user_activity();

DROP TRIGGER IF EXISTS trigger_user_activity_referral ON public.profiles;
CREATE TRIGGER trigger_user_activity_referral
AFTER UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.handle_user_activity();

-- 4. Update get_referral_dashboard_kpi RPC to include Activity Data
DROP FUNCTION IF EXISTS public.get_referral_dashboard_kpi(p_user_id UUID);
CREATE OR REPLACE FUNCTION public.get_referral_dashboard_kpi(p_user_id UUID)
RETURNS JSON
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    v_total_referrals INT;
    v_level1_count INT;
    v_level2_count INT;
    v_org_size INT;
    v_active_members INT;
    v_inactive_members INT;
    v_today_comm NUMERIC;
    v_month_comm NUMERIC;
    v_withdrawable NUMERIC;
    v_withdrawn NUMERIC;
    v_pending_comm NUMERIC := 0;
    v_approved_comm NUMERIC := 0;
    v_forecast NUMERIC := 0;
    v_health_score NUMERIC := 0;
    v_health_grade TEXT := 'Dormant';
    v_notifications JSON;
    v_activity JSON;
BEGIN
    -- [Previous Logic omitted for brevity, keeping it identical and just adding activity]
    -- We will query activity at the end.
    
    -- Level 1
    SELECT COUNT(*) INTO v_level1_count FROM public.profiles WHERE referrer_id = p_user_id;
    
    -- Level 2
    SELECT COUNT(*) INTO v_level2_count 
    FROM public.profiles p2 
    JOIN public.profiles p1 ON p2.referrer_id = p1.id 
    WHERE p1.referrer_id = p_user_id;

    v_total_referrals := v_level1_count;
    v_org_size := v_level1_count + v_level2_count;

    -- Active/Inactive (Level 1 + 2)
    WITH all_downline AS (
        SELECT id, last_sign_in_at FROM public.profiles WHERE referrer_id = p_user_id
        UNION ALL
        SELECT p2.id, p2.last_sign_in_at FROM public.profiles p2 JOIN public.profiles p1 ON p2.referrer_id = p1.id WHERE p1.referrer_id = p_user_id
    )
    SELECT 
        COUNT(CASE WHEN last_sign_in_at >= NOW() - INTERVAL '7 days' THEN 1 END),
        COUNT(CASE WHEN last_sign_in_at < NOW() - INTERVAL '7 days' OR last_sign_in_at IS NULL THEN 1 END)
    INTO v_active_members, v_inactive_members
    FROM all_downline;

    -- Commissions (Simple calculation for dashboard)
    SELECT 
        COALESCE(SUM(CASE WHEN created_at >= CURRENT_DATE THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE) THEN amount ELSE 0 END), 0)
    INTO v_today_comm, v_month_comm
    FROM public.commissions
    WHERE beneficiary_user_id = p_user_id;

    -- Balances
    SELECT 
        COALESCE(SUM(CASE WHEN status IN ('WITHDRAWABLE', 'APPROVED', 'PAID') THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END), 0)
    INTO v_withdrawable, v_withdrawn, v_pending_comm
    FROM public.commissions
    WHERE beneficiary_user_id = p_user_id;
    
    v_withdrawable := v_withdrawable - v_withdrawn;
    v_approved_comm := v_withdrawable;

    -- Health Score
    IF v_org_size > 0 THEN
        v_health_score := LEAST(100, (v_active_members::NUMERIC / v_org_size) * 100);
    END IF;
    IF v_health_score >= 80 THEN v_health_grade := 'Excellent';
    ELSIF v_health_score >= 50 THEN v_health_grade := 'Good';
    ELSIF v_health_score >= 20 THEN v_health_grade := 'Fair';
    ELSE v_health_grade := 'Dormant';
    END IF;

    -- Get Unread Notifications
    SELECT COALESCE(json_agg(row_to_json(n)), '[]'::json) INTO v_notifications
    FROM (
        SELECT id, type, title, message, is_read, created_at 
        FROM public.user_notifications 
        WHERE user_id = p_user_id 
        ORDER BY created_at DESC 
        LIMIT 50
    ) n;

    -- Get Today's Activity
    SELECT COALESCE(row_to_json(a), '{"jobs_completed": 0, "referrals_added": 0, "current_streak": 0}'::json) INTO v_activity
    FROM (
        SELECT jobs_completed, referrals_added, current_streak
        FROM public.user_activity
        WHERE user_id = p_user_id AND activity_date = CURRENT_DATE
    ) a;

    result := json_build_object(
        'total_referrals', v_total_referrals,
        'level1_count', v_level1_count,
        'level2_count', v_level2_count,
        'organization_size', v_org_size,
        'active_members', COALESCE(v_active_members, 0),
        'inactive_members', COALESCE(v_inactive_members, 0),
        'today_commission', v_today_comm,
        'month_commission', v_month_comm,
        'pending_commission', v_pending_comm,
        'approved_commission', v_approved_comm,
        'withdrawable_balance', v_withdrawable,
        'withdrawn_total', v_withdrawn,
        'expected_month_commission', v_month_comm * 2,
        'forecast_next_payout', v_withdrawable,
        'organization_health_score', ROUND(v_health_score, 1),
        'organization_health_grade', v_health_grade,
        'notifications', v_notifications,
        'activity', v_activity
    );

    RETURN result;
END;
$$ LANGUAGE plpgsql;
