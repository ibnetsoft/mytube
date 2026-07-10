-- =============================================================
-- Migration: AIR-0225 — referral_commissions.commission_tokens BIGINT -> NUMERIC
--
-- ROOT CAUSE: commission_tokens was defined as BIGINT (integer-only),
-- but the calculation that produces it (auth-web/lib/settlement.ts:
-- Math.round(amount * (levelPercent / 100) * 100) / 100) routinely
-- produces fractional values - e.g. 4 tokens used * 10% rate = 0.4.
-- Every real-usage commission insert has been failing with:
--   22P02 invalid input syntax for type bigint: "0.4"
-- Confirmed live via a synthetic test insert before writing this fix.
--
-- referral_commissions has 0 rows in production (re-confirmed
-- immediately before this migration), so this is a pure, safe type
-- widening with no data to migrate.
--
-- Safe to re-run: ALTER COLUMN ... TYPE is idempotent in effect (a
-- second run against an already-NUMERIC column is a no-op change).
-- =============================================================

BEGIN;

ALTER TABLE public.referral_commissions
    ALTER COLUMN commission_tokens TYPE NUMERIC(18,4);

DO $$
DECLARE
    v_data_type TEXT;
BEGIN
    SELECT data_type INTO v_data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'referral_commissions' AND column_name = 'commission_tokens';

    IF v_data_type <> 'numeric' THEN
        RAISE EXCEPTION 'AIR-0225 check FAILED: commission_tokens is still % (expected numeric)', v_data_type;
    END IF;

    RAISE NOTICE 'AIR-0225: commission_tokens is now NUMERIC(18,4).';
END $$;

COMMIT;
