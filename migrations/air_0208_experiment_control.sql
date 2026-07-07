-- =============================================================
-- Migration: Experiment Control & Simulation (AIR-0208)
-- =============================================================

-- 1. Add simulation flag
ALTER TABLE public.user_events 
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Update the RPC to filter out simulated data by default
DROP FUNCTION IF EXISTS public.get_analytics_dashboard(boolean);
DROP FUNCTION IF EXISTS public.get_analytics_dashboard();

CREATE OR REPLACE FUNCTION public.get_analytics_dashboard(p_include_simulated BOOLEAN DEFAULT FALSE)
RETURNS JSON
SECURITY DEFINER
AS $$
DECLARE
    v_funnel JSON;
    v_ab_test JSON;
    v_top_referrers JSON;
BEGIN
    -- Funnel logic (Unique users per stage)
    SELECT json_build_object(
        'VIEW_REFERRAL_PAGE', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'VIEW_REFERRAL_PAGE' AND (is_simulated = FALSE OR p_include_simulated = TRUE)),
        'COPY_LINK', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'COPY_LINK' AND (is_simulated = FALSE OR p_include_simulated = TRUE)),
        'REFERRAL_JOIN', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'REFERRAL_JOIN' AND (is_simulated = FALSE OR p_include_simulated = TRUE)),
        'JOB_COMPLETED', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'JOB_COMPLETED' AND (is_simulated = FALSE OR p_include_simulated = TRUE)),
        'COMMISSION_EARNED', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'COMMISSION_EARNED' AND (is_simulated = FALSE OR p_include_simulated = TRUE))
    ) INTO v_funnel;

    -- A/B test logic (Test Referral CTA performance)
    -- Group by test_name and variant if we add test_name to metadata, but for now we rely on the variant key
    WITH variant_stats AS (
        SELECT 
            COALESCE(metadata->>'test_name', 'referral_cta') as test_name,
            COALESCE(metadata->>'variant', 'A') as variant,
            COUNT(DISTINCT CASE WHEN event_type = 'VIEW_REFERRAL_PAGE' THEN user_id END) as viewers,
            COUNT(DISTINCT CASE WHEN event_type = 'COPY_LINK' THEN user_id END) as copiers
        FROM public.user_events
        WHERE event_type IN ('VIEW_REFERRAL_PAGE', 'COPY_LINK')
          AND (is_simulated = FALSE OR p_include_simulated = TRUE)
        GROUP BY 1, 2
    )
    SELECT COALESCE(json_agg(row_to_json(v)), '[]'::json) INTO v_ab_test FROM variant_stats v;

    -- Top Referrers 
    WITH top_refs AS (
        SELECT p.referrer_id, 
               MAX((SELECT display_name FROM public.profiles WHERE id = p.referrer_id)) as username,
               COUNT(*) as total_joins,
               COALESCE((SELECT SUM(amount) FROM public.commissions WHERE beneficiary_user_id = p.referrer_id), 0) as total_revenue
        FROM public.profiles p
        WHERE p.referrer_id IS NOT NULL
        GROUP BY p.referrer_id
        ORDER BY total_joins DESC, total_revenue DESC
        LIMIT 10
    )
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) INTO v_top_referrers FROM top_refs t;

    RETURN json_build_object(
        'funnel', v_funnel,
        'ab_test', v_ab_test,
        'top_referrers', v_top_referrers
    );
END;
$$ LANGUAGE plpgsql;
