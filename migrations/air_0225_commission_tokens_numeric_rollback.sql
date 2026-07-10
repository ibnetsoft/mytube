-- Rollback for air_0225_commission_tokens_numeric.sql
-- Restores commission_tokens to BIGINT. Only safe if no fractional
-- values have been written since the forward migration ran (a
-- fractional value truncates on cast back to BIGINT).

BEGIN;

ALTER TABLE public.referral_commissions
    ALTER COLUMN commission_tokens TYPE BIGINT USING ROUND(commission_tokens)::BIGINT;

COMMIT;
