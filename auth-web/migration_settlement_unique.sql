-- 1. Create unique index to prevent duplicate commissions per transaction and type
CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_commissions_tx 
ON public.referral_commissions((metadata->>'source_tx_id'), commission_type) 
WHERE metadata->>'source_tx_id' IS NOT NULL;
