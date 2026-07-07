-- =============================================================
-- Migration: Habit Reminder RPC (AIR-0206)
-- Description: Finds users active yesterday but inactive today
-- =============================================================

CREATE OR REPLACE FUNCTION trigger_habit_reminders()
RETURNS VOID
SECURITY DEFINER
AS $$
DECLARE
    r RECORD;
    v_today DATE := CURRENT_DATE;
    v_yesterday DATE := CURRENT_DATE - INTERVAL '1 day';
BEGIN
    -- Find users who:
    -- 1. Had jobs_completed > 0 or referrals_added > 0 yesterday
    -- 2. Have jobs_completed = 0 and referrals_added = 0 today (or no record for today)
    FOR r IN (
        SELECT y.user_id 
        FROM public.user_activity y
        WHERE y.activity_date = v_yesterday
        AND (y.jobs_completed > 0 OR y.referrals_added > 0)
        AND NOT EXISTS (
            SELECT 1 FROM public.user_activity t
            WHERE t.user_id = y.user_id 
            AND t.activity_date = v_today
            AND (t.jobs_completed > 0 OR t.referrals_added > 0)
        )
    )
    LOOP
        -- Insert a SYSTEM_ALERT notification
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (
            r.user_id, 
            'SYSTEM_ALERT', 
            'habit_reminder_' || to_char(v_today, 'YYYY_MM_DD'), 
            'Keep your streak alive!', 
            'You haven’t completed any task today. Complete one now to maintain your streak!'
        ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
