-- =============================================================
-- Migration: Drop Legacy Withdrawal Commission RPC
-- Description: Drops process_withdrawal_commission to prevent Double Payout conflict with Referral Commission Engine.
-- =============================================================

DROP FUNCTION IF EXISTS public.process_withdrawal_commission(UUID);
