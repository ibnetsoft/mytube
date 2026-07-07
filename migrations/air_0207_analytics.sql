-- =============================================================
-- Migration: Analytics and A/B Testing Engine (AIR-0207)
-- =============================================================

-- 1. Create user_events table
CREATE TABLE IF NOT EXISTS public.user_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('VIEW_REFERRAL_PAGE', 'COPY_LINK', 'REFERRAL_JOIN', 'JOB_COMPLETED', 'COMMISSION_EARNED')),
    reference_id TEXT, -- Optional, used for deduplication of backend events
    metadata JSONB DEFAULT '{}'::jsonb, -- Used for A/B testing variants (e.g., {"variant": "A"})
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Performance & Consistency Indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_events_dedup 
ON public.user_events(user_id, event_type, reference_id) 
WHERE reference_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_events_created_at ON public.user_events(created_at);
CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON public.user_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_event_type ON public.user_events(event_type);

-- 3. Trigger Function for Backend Analytics Events
CREATE OR REPLACE FUNCTION public.handle_backend_analytics()
RETURNS TRIGGER
SECURITY DEFINER
AS $$
BEGIN
    IF TG_TABLE_NAME = 'profiles' THEN
        -- REFERRAL_JOIN
        IF NEW.referrer_id IS NOT NULL AND (OLD.referrer_id IS NULL OR OLD.referrer_id != NEW.referrer_id) THEN
            INSERT INTO public.user_events (user_id, event_type, reference_id, metadata)
            VALUES (NEW.referrer_id, 'REFERRAL_JOIN', NEW.id::text, '{}'::jsonb)
            ON CONFLICT (user_id, event_type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;
    ELSIF TG_TABLE_NAME = 'worker_jobs' THEN
        -- JOB_COMPLETED
        IF NEW.status = 'COMPLETED' AND (OLD.status IS NULL OR OLD.status != 'COMPLETED') AND NEW.user_id IS NOT NULL THEN
            INSERT INTO public.user_events (user_id, event_type, reference_id, metadata)
            VALUES (NEW.user_id, 'JOB_COMPLETED', NEW.id::text, '{}'::jsonb)
            ON CONFLICT (user_id, event_type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;
    ELSIF TG_TABLE_NAME = 'commissions' THEN
        -- COMMISSION_EARNED
        -- Use the commission's ID as the reference_id to ensure deduplication if status hops around
        IF NEW.status IN ('APPROVED', 'PAID') AND (OLD.status IS NULL OR OLD.status NOT IN ('APPROVED', 'PAID')) THEN
            INSERT INTO public.user_events (user_id, event_type, reference_id, metadata)
            VALUES (NEW.beneficiary_user_id, 'COMMISSION_EARNED', NEW.id::text, '{}'::jsonb)
            ON CONFLICT (user_id, event_type, reference_id) WHERE reference_id IS NOT NULL DO NOTHING;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4. Attach Triggers
DROP TRIGGER IF EXISTS trigger_analytics_referral_join ON public.profiles;
CREATE TRIGGER trigger_analytics_referral_join
AFTER UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.handle_backend_analytics();

DROP TRIGGER IF EXISTS trigger_analytics_job_completed ON public.worker_jobs;
CREATE TRIGGER trigger_analytics_job_completed
AFTER UPDATE ON public.worker_jobs
FOR EACH ROW
EXECUTE FUNCTION public.handle_backend_analytics();

DROP TRIGGER IF EXISTS trigger_analytics_commission ON public.commissions;
CREATE TRIGGER trigger_analytics_commission
AFTER UPDATE ON public.commissions
FOR EACH ROW
EXECUTE FUNCTION public.handle_backend_analytics();

-- 5. RPC for Analytics Dashboard (Funnel & A/B Testing)
DROP FUNCTION IF EXISTS public.get_analytics_dashboard();
CREATE OR REPLACE FUNCTION public.get_analytics_dashboard()
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
        'VIEW_REFERRAL_PAGE', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'VIEW_REFERRAL_PAGE'),
        'COPY_LINK', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'COPY_LINK'),
        'REFERRAL_JOIN', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'REFERRAL_JOIN'),
        'JOB_COMPLETED', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'JOB_COMPLETED'),
        'COMMISSION_EARNED', (SELECT COUNT(DISTINCT user_id) FROM public.user_events WHERE event_type = 'COMMISSION_EARNED')
    ) INTO v_funnel;

    -- A/B test logic (Test Referral CTA performance)
    WITH variant_stats AS (
        SELECT 
            COALESCE(metadata->>'variant', 'A') as variant,
            COUNT(DISTINCT CASE WHEN event_type = 'VIEW_REFERRAL_PAGE' THEN user_id END) as viewers,
            COUNT(DISTINCT CASE WHEN event_type = 'COPY_LINK' THEN user_id END) as copiers
        FROM public.user_events
        WHERE event_type IN ('VIEW_REFERRAL_PAGE', 'COPY_LINK')
        GROUP BY 1
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
