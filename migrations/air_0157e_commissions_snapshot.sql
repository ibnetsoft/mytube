-- Migration: Add metadata snapshot to commissions table
-- AIR-0157E Commission Engine Implementation

ALTER TABLE public.commissions
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Comment on column
COMMENT ON COLUMN public.commissions.metadata IS 'Snapshot data for commission calculation including applied_rate, base_reward_amount, source_event, etc.';
