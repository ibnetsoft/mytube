-- Re-engagement RPC
CREATE OR REPLACE FUNCTION trigger_reengagement_notifications()
RETURNS VOID
SECURITY DEFINER
AS $$
DECLARE
    r RECORD;
BEGIN
    -- Find users who:
    -- 1. Have not signed in for > 7 days
    -- 2. Have at least 1 downline member who signed in within 7 days
    FOR r IN (
        SELECT p.id 
        FROM public.profiles p
        WHERE (p.last_sign_in_at IS NULL OR p.last_sign_in_at < NOW() - INTERVAL '7 days')
        AND EXISTS (
            SELECT 1 FROM public.profiles downline
            WHERE downline.referrer_id = p.id 
            AND downline.last_sign_in_at >= NOW() - INTERVAL '7 days'
        )
    )
    LOOP
        -- Insert a SYSTEM_ALERT notification
        INSERT INTO public.user_notifications (user_id, type, reference_id, title, message)
        VALUES (
            r.id, 
            'SYSTEM_ALERT', 
            'reengage_' || to_char(CURRENT_DATE, 'YYYY_MM_DD'), 
            'Your team is active!', 
            'Your referral team is growing and active. Log in to check your commissions!'
        ) ON CONFLICT (user_id, type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
