-- =============================================================
-- Migration: Fraud Detection & Risk Monitoring (AIR-0203)
-- Description: Risk flags table, enums, triggers, and RPCs
-- =============================================================

-- 1. Enum Types
DO $$ BEGIN
    CREATE TYPE public.risk_score AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Risk Flags Table
CREATE TABLE IF NOT EXISTS public.risk_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    risk_type TEXT NOT NULL,
    score public.risk_score NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_risk_flags_user ON public.risk_flags(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_flags_score ON public.risk_flags(score);
CREATE INDEX IF NOT EXISTS idx_risk_flags_unresolved ON public.risk_flags(is_resolved) WHERE is_resolved = false;

-- Duplicate Prevention: One type of risk per user per hour
CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_flags_dedup 
ON public.risk_flags (user_id, risk_type, date_trunc('hour', created_at));

-- RLS
ALTER TABLE public.risk_flags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Superadmins can view risk flags"
    ON public.risk_flags
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );

CREATE POLICY "Superadmins can update risk flags"
    ON public.risk_flags
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );


-- =============================================================
-- Lightweight Triggers (Real-Time)
-- =============================================================

-- A. Withdrawal Abuse Trigger
CREATE OR REPLACE FUNCTION public.check_withdrawal_abuse()
RETURNS TRIGGER AS $$
DECLARE
    v_count INT;
    v_score public.risk_score;
BEGIN
    -- Only check new insertions that are requested
    IF NEW.status = 'REQUESTED' THEN
        
        -- Rule 1: High Amount Threshold
        IF NEW.amount > 5000 THEN
            INSERT INTO public.risk_flags (user_id, risk_type, score, details)
            VALUES (NEW.user_id, 'WITHDRAWAL_AMOUNT_CRITICAL', 'CRITICAL', jsonb_build_object('trigger', 'amount_exceeded', 'value', NEW.amount, 'threshold', 5000))
            ON CONFLICT (user_id, risk_type, date_trunc('hour', created_at)) DO NOTHING;
        ELSIF NEW.amount > 1000 THEN
            INSERT INTO public.risk_flags (user_id, risk_type, score, details)
            VALUES (NEW.user_id, 'WITHDRAWAL_AMOUNT_HIGH', 'HIGH', jsonb_build_object('trigger', 'amount_exceeded', 'value', NEW.amount, 'threshold', 1000))
            ON CONFLICT (user_id, risk_type, date_trunc('hour', created_at)) DO NOTHING;
        END IF;

        -- Rule 2: Frequency Check
        SELECT COUNT(*) INTO v_count 
        FROM public.withdrawal_requests 
        WHERE user_id = NEW.user_id 
          AND created_at >= NOW() - INTERVAL '24 hours';
          
        IF v_count > 3 THEN
            INSERT INTO public.risk_flags (user_id, risk_type, score, details)
            VALUES (NEW.user_id, 'WITHDRAWAL_FREQUENCY', 'CRITICAL', jsonb_build_object('trigger', 'frequent_withdrawals', 'value', v_count, 'window', '24h', 'threshold', 3))
            ON CONFLICT (user_id, risk_type, date_trunc('hour', created_at)) DO NOTHING;
        END IF;

    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trigger_check_withdrawal_abuse ON public.withdrawal_requests;
CREATE TRIGGER trigger_check_withdrawal_abuse
AFTER INSERT ON public.withdrawal_requests
FOR EACH ROW
EXECUTE FUNCTION public.check_withdrawal_abuse();


-- B. Job Abuse Trigger
CREATE OR REPLACE FUNCTION public.check_job_abuse()
RETURNS TRIGGER AS $$
DECLARE
    v_count INT;
BEGIN
    -- Count completions in the last hour
    IF NEW.status = 'COMPLETED' THEN
        SELECT COUNT(*) INTO v_count 
        FROM public.worker_jobs 
        WHERE worker_id = NEW.worker_id 
          AND status = 'COMPLETED'
          AND completed_at >= NOW() - INTERVAL '1 hour';
          
        IF v_count > 50 THEN
            INSERT INTO public.risk_flags (user_id, risk_type, score, details)
            VALUES (NEW.worker_id, 'JOB_VELOCITY', 'CRITICAL', jsonb_build_object('trigger', 'high_velocity_jobs', 'value', v_count, 'window', '1h', 'threshold', 50))
            ON CONFLICT (user_id, risk_type, date_trunc('hour', created_at)) DO NOTHING;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trigger_check_job_abuse ON public.worker_jobs;
CREATE TRIGGER trigger_check_job_abuse
AFTER UPDATE OF status ON public.worker_jobs
FOR EACH ROW
WHEN (OLD.status != 'COMPLETED' AND NEW.status = 'COMPLETED')
EXECUTE FUNCTION public.check_job_abuse();


-- =============================================================
-- Heavy RPC Scan (On-Demand)
-- =============================================================

CREATE OR REPLACE FUNCTION admin_scan_referral_trees(p_admin_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_record RECORD;
    v_flags_created INT := 0;
BEGIN
    -- Security check
    IF NOT EXISTS (SELECT 1 FROM public.profiles WHERE id = p_admin_id AND is_superadmin = true) THEN
        RAISE EXCEPTION 'Unauthorized';
    END IF;

    -- Heavy aggregation: Detect abnormal referral spikes (> 50 referrals in a day for a single referrer)
    FOR v_record IN 
        SELECT referrer_id, COUNT(*) as ref_count 
        FROM public.referral_trees 
        WHERE created_at >= NOW() - INTERVAL '24 hours' 
          AND level = 1
        GROUP BY referrer_id 
        HAVING COUNT(*) > 50
    LOOP
        INSERT INTO public.risk_flags (user_id, risk_type, score, details)
        VALUES (v_record.referrer_id, 'REFERRAL_SPIKE', 'HIGH', jsonb_build_object('trigger', 'mass_referrals', 'value', v_record.ref_count, 'window', '24h', 'threshold', 50))
        ON CONFLICT (user_id, risk_type, date_trunc('hour', created_at)) DO NOTHING;
        
        IF FOUND THEN
            v_flags_created := v_flags_created + 1;
        END IF;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'flags_created', v_flags_created);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
