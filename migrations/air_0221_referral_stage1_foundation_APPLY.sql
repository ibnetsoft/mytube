-- =============================================================
-- AIR-0221 Stage 1 — SINGLE-PASTE APPLY SCRIPT for Supabase SQL Editor
--
-- This is a convenience wrapper, not a replacement for the reviewed files:
--   - air_0221_referral_stage1_foundation.sql        (the approved migration, unchanged)
--   - air_0221_referral_stage1_foundation_rollback.sql (rollback, unchanged)
--   - air_0221_referral_stage1_foundation_CHECKLIST.md (the approved procedure)
--
-- What this file does: BEGIN -> the exact migration statements -> the
-- checklist's §4 verification checks, rewritten as DO-block assertions ->
-- COMMIT. If ANY assertion fails, it RAISEs an exception, which aborts the
-- transaction. Postgres then treats the trailing COMMIT as a no-op ROLLBACK
-- automatically — you do not need to manually decide COMMIT vs ROLLBACK,
-- and you do not need to keep the SQL Editor tab's connection alive across
-- multiple separate "Run" clicks (which is not guaranteed to preserve an
-- open transaction over a pooled connection anyway).
--
-- HOW TO RUN:
--   1. Supabase Dashboard -> this project -> SQL Editor -> New query.
--   2. Paste this entire file.
--   3. Click Run, once.
--   4. Read the output:
--      - "Success. No rows returned" + a NOTICE reading
--        "AIR-0221 Stage 1: all verification checks passed." => applied and committed.
--      - Any red error message (e.g. "Stage1 check failed: ...") => nothing
--        was committed, the whole migration was automatically rolled back.
--        Copy the exact error text back for diagnosis before retrying.
-- =============================================================

BEGIN;

-- ─────────────────────────────────────────────
-- 1. referral_commissions — additive columns only
-- ─────────────────────────────────────────────

ALTER TABLE public.referral_commissions
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE public.referral_commissions
    ADD COLUMN IF NOT EXISTS commission_level SMALLINT;

ALTER TABLE public.referral_commissions
    ADD COLUMN IF NOT EXISTS source_job_id TEXT;

COMMENT ON COLUMN public.referral_commissions.updated_at IS
    'AIR-0221 Stage 1 (additive). Auto-maintained by trg_referral_commissions_updated_at. No historical meaning before this migration.';
COMMENT ON COLUMN public.referral_commissions.commission_level IS
    'AIR-0221 Stage 1 (additive). Target replacement for the free-text commission_type column: 1 = direct (L1) referral commission, 2 = second-level (L2). Nullable until Stage 2 backfill. commission_type itself is NOT modified or dropped by this migration — both columns coexist until cutover.';
COMMENT ON COLUMN public.referral_commissions.source_job_id IS
    'AIR-0221 Stage 1 (additive). References the job/transaction that generated this commission (Commission Trace "원인 작업"). TEXT rather than a FK because source jobs are not backed by a single canonical table today.';
COMMENT ON COLUMN public.referral_commissions.metadata IS
    'AIR-0221 Stage 1: documented (not enforced) Commission Trace convention for this JSONB column going forward — expected keys: "job_type" (e.g. video_render, image_gen), "job_ref" (human-readable job identifier if source_job_id is opaque), "rate_source" (the global_settings key the applied rate/commission_level came from at generation time). No keys are required or validated at the DB level; this is documentation only.';

ALTER TABLE public.referral_commissions
    DROP CONSTRAINT IF EXISTS referral_commissions_commission_level_check;
ALTER TABLE public.referral_commissions
    ADD CONSTRAINT referral_commissions_commission_level_check
    CHECK (commission_level IS NULL OR commission_level IN (1, 2)) NOT VALID;
ALTER TABLE public.referral_commissions
    VALIDATE CONSTRAINT referral_commissions_commission_level_check;

CREATE INDEX IF NOT EXISTS idx_referral_commissions_commission_level
    ON public.referral_commissions(commission_level);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_source_job_id
    ON public.referral_commissions(source_job_id);

CREATE OR REPLACE FUNCTION public.set_referral_commissions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_referral_commissions_updated_at ON public.referral_commissions;
CREATE TRIGGER trg_referral_commissions_updated_at
    BEFORE UPDATE ON public.referral_commissions
    FOR EACH ROW
    EXECUTE FUNCTION public.set_referral_commissions_updated_at();


-- ─────────────────────────────────────────────
-- 2. referral_withdrawals — new table
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.referral_withdrawals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount          NUMERIC(18,6) NOT NULL CHECK (amount > 0),
    wallet_address  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'REQUESTED'
                        CHECK (status IN ('REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED', 'REJECTED')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    rejected_at     TIMESTAMPTZ,
    tx_hash         TEXT,
    admin_id        UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reason          TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.referral_withdrawals IS
    'AIR-0221 Stage 1 (new, additive). Referral-earnings cash-out ledger. Not yet wired to any API. sent_at was added beyond the literal Stage-1 ticket field list to give the SENDING status a matching timestamp, consistent with every other status in this state machine having one — flagged here for CTO review, easy to drop if unwanted.';

CREATE INDEX IF NOT EXISTS idx_referral_withdrawals_user_id ON public.referral_withdrawals(user_id);
CREATE INDEX IF NOT EXISTS idx_referral_withdrawals_status ON public.referral_withdrawals(status);
CREATE INDEX IF NOT EXISTS idx_referral_withdrawals_created_at ON public.referral_withdrawals(created_at);

CREATE OR REPLACE FUNCTION public.set_referral_withdrawals_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_referral_withdrawals_updated_at ON public.referral_withdrawals;
CREATE TRIGGER trg_referral_withdrawals_updated_at
    BEFORE UPDATE ON public.referral_withdrawals
    FOR EACH ROW
    EXECUTE FUNCTION public.set_referral_withdrawals_updated_at();

ALTER TABLE public.referral_withdrawals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own referral withdrawals" ON public.referral_withdrawals;
CREATE POLICY "Users can view own referral withdrawals"
    ON public.referral_withdrawals
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own referral withdrawals" ON public.referral_withdrawals;
CREATE POLICY "Users can insert own referral withdrawals"
    ON public.referral_withdrawals
    FOR INSERT
    WITH CHECK (auth.uid() = user_id AND status = 'REQUESTED');


-- ─────────────────────────────────────────────
-- 3. referral_audit_logs — new table (audit foundation)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.referral_audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('commission', 'withdrawal')),
    entity_id   UUID NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'completed', 'reversed')),
    actor_id    UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reason      TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.referral_audit_logs IS
    'AIR-0221 Stage 1 (new, additive). admin_audit_logs (Gen 3) does not exist in production and is not reused. Records commission-generation and withdrawal-approve/reject/complete events for the Audit Log dashboard tab (CONSOLIDATION_PLAN.md §10.4). actor_id is NULL for system-generated commission events (no human actor) and set for admin withdrawal actions. Not yet written to by any application code.';

CREATE INDEX IF NOT EXISTS idx_referral_audit_logs_entity ON public.referral_audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_referral_audit_logs_created_at ON public.referral_audit_logs(created_at);

ALTER TABLE public.referral_audit_logs ENABLE ROW LEVEL SECURITY;
-- Intentionally no policies: service-role only (see migration file comments).


-- ─────────────────────────────────────────────
-- 4. Self-verification — checklist §4, as automatic assertions.
--    Any RAISE EXCEPTION here aborts the whole transaction; the COMMIT
--    below then becomes a no-op rollback. Nothing partial is ever left committed.
-- ─────────────────────────────────────────────

DO $$
DECLARE
    v_count INT;
BEGIN
    -- 4a. New referral_commissions columns exist
    SELECT count(*) INTO v_count FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'referral_commissions'
      AND column_name IN ('updated_at', 'commission_level', 'source_job_id');
    IF v_count <> 3 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4a): expected 3 new referral_commissions columns, found %', v_count;
    END IF;

    -- 4b. CHECK constraint exists and is validated
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.referral_commissions'::regclass
          AND conname = 'referral_commissions_commission_level_check'
          AND convalidated = true
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4b): referral_commissions_commission_level_check missing or not validated';
    END IF;

    -- 4c. Trigger on referral_commissions exists and is enabled
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.referral_commissions'::regclass
          AND tgname = 'trg_referral_commissions_updated_at'
          AND tgenabled <> 'D'
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4c): trg_referral_commissions_updated_at missing or disabled';
    END IF;

    -- 4e. New tables exist with RLS enabled
    IF to_regclass('public.referral_withdrawals') IS NULL THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4e): referral_withdrawals table missing';
    END IF;
    IF to_regclass('public.referral_audit_logs') IS NULL THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4e): referral_audit_logs table missing';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.referral_withdrawals'::regclass) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4e): RLS not enabled on referral_withdrawals';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.referral_audit_logs'::regclass) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4e): RLS not enabled on referral_audit_logs';
    END IF;

    -- 4f. Policy counts match design (2 on withdrawals, 0 on audit_logs)
    SELECT count(*) INTO v_count FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'referral_withdrawals';
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4f): expected 2 policies on referral_withdrawals, found %', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'referral_audit_logs';
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4f): expected 0 policies on referral_audit_logs, found %', v_count;
    END IF;

    -- 4g. Trigger on referral_withdrawals exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.referral_withdrawals'::regclass
          AND tgname = 'trg_referral_withdrawals_updated_at'
          AND tgenabled <> 'D'
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4g): trg_referral_withdrawals_updated_at missing or disabled';
    END IF;

    -- 4h. All 7 indexes exist
    SELECT count(*) INTO v_count FROM pg_indexes
    WHERE schemaname = 'public' AND indexname IN (
        'idx_referral_commissions_commission_level',
        'idx_referral_commissions_source_job_id',
        'idx_referral_withdrawals_user_id',
        'idx_referral_withdrawals_status',
        'idx_referral_withdrawals_created_at',
        'idx_referral_audit_logs_entity',
        'idx_referral_audit_logs_created_at'
    );
    IF v_count <> 7 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4h): expected 7 indexes, found %', v_count;
    END IF;

    -- 4i. New tables are genuinely empty
    SELECT count(*) INTO v_count FROM public.referral_withdrawals;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4i): referral_withdrawals should be empty, has % rows', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM public.referral_audit_logs;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (4i): referral_audit_logs should be empty, has % rows', v_count;
    END IF;

    -- 4d equivalent: referral_commissions row count sanity (not deleting/mutating rows)
    -- No fixed expected count is asserted here (this script doesn't know the
    -- pre-migration count) — if you need to confirm 0 rows were touched,
    -- compare this NOTICE's value against the pre-apply count you captured.
    SELECT count(*) INTO v_count FROM public.referral_commissions;
    RAISE NOTICE 'referral_commissions row count after migration: % (compare against your pre-apply count)', v_count;

    RAISE NOTICE 'AIR-0221 Stage 1: all verification checks passed.';
END $$;

COMMIT;
