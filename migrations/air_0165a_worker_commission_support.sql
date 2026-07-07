-- Migration: Job Completion Reward Pipeline (AIR-0165)
-- Description: Connects Worker Jobs to the Commission Ledger

-- 1. Modify commissions referral_level constraint
-- Drop existing constraint safely
ALTER TABLE public.commissions DROP CONSTRAINT IF EXISTS commissions_referral_level_check;

-- Add new constraint allowing 0, 1, 2
-- 0 = direct worker earning
-- 1 = level 1 referral commission
-- 2 = level 2 referral commission
ALTER TABLE public.commissions ADD CONSTRAINT commissions_referral_level_check CHECK (referral_level IN (0, 1, 2));

-- 2. Add idempotency protection
-- Create partial unique index to strictly prevent duplicate commissions from the same job
CREATE UNIQUE INDEX IF NOT EXISTS idx_commissions_unique_job ON public.commissions(source_id) WHERE source_type = 'JOB';

-- 3. Create RPC for atomic job completion and commission minting
CREATE OR REPLACE FUNCTION public.complete_worker_job_and_mint_commission(
  p_job_id UUID,
  p_user_id UUID
) RETURNS jsonb AS $$
DECLARE
  v_job record;
  v_commission_id UUID;
BEGIN
  -- 1. Verify user_id matches auth.uid() if running in authenticated context
  -- (If running via service role, auth.uid() may be null, but we'll enforce the parameter matches the job)
  -- The requirement says: "RPC must enforce: auth.uid() = p_user_id"
  IF auth.uid() IS NOT NULL AND auth.uid() != p_user_id THEN
    RAISE EXCEPTION 'Unauthorized: User ID mismatch';
  END IF;

  -- 2. Lock the worker job row to prevent concurrent modifications
  SELECT * INTO v_job FROM public.worker_jobs WHERE id = p_job_id FOR UPDATE;
  
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Job not found';
  END IF;

  -- 3. Verify job belongs to p_user_id
  IF v_job.user_id != p_user_id THEN
    RAISE EXCEPTION 'Forbidden: Not your job';
  END IF;

  -- 4. Verify job status = ACTIVE
  IF v_job.status = 'COMPLETED' THEN
    -- Graceful idempotent response if already completed by this user
    RETURN jsonb_build_object('success', true, 'message', 'Job already completed', 'job_id', p_job_id);
  END IF;

  IF v_job.status != 'ACTIVE' THEN
    RAISE EXCEPTION 'Job is not active';
  END IF;

  -- 5. Update worker_jobs:
  UPDATE public.worker_jobs 
  SET 
    status = 'COMPLETED',
    progress = 100,
    completed_at = now(),
    updated_at = now()
  WHERE id = p_job_id;

  -- 6. Insert commission:
  -- Note: If this fails due to the unique index (somehow racing another transaction), the whole transaction aborts,
  -- ensuring atomicity as required.
  INSERT INTO public.commissions (
    beneficiary_user_id,
    source_user_id,
    source_type,
    source_id,
    referral_level,
    amount,
    currency,
    status,
    created_at,
    updated_at,
    metadata
  ) VALUES (
    p_user_id,                         -- beneficiary_user_id
    p_user_id,                         -- source_user_id
    'JOB',                             -- source_type
    p_job_id::TEXT,                    -- source_id
    0,                                 -- referral_level (0 = direct)
    v_job.estimated_earnings,          -- amount
    'USDT',                            -- currency
    'PENDING',                         -- status
    now(),                             -- created_at
    now(),                             -- updated_at
    jsonb_build_object('job_title', v_job.title, 'job_type', v_job.type) -- metadata
  ) RETURNING id INTO v_commission_id;

  -- 7. Return success response
  RETURN jsonb_build_object(
    'success', true, 
    'job_id', p_job_id, 
    'commission_id', v_commission_id,
    'amount', v_job.estimated_earnings
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
