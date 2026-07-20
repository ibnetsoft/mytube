-- =============================================================
-- Rollback: AIR-0221 Stage 1 — Referral Consolidation, Additive Schema Foundation
-- Reverses migrations/air_0221_referral_stage1_foundation.sql exactly.
--
-- Safe by construction: every object this rollback drops was created
-- by the Stage-1 migration and, as of Stage 1, is not read or written
-- by any application code — so there is nothing to lose. If Stage 2/3
-- has since started dual-writing to referral_withdrawals or
-- referral_audit_logs, or backfilling commission_level/source_job_id,
-- DO NOT run this rollback without first checking those tables/columns
-- for data (see the pre-flight queries at the bottom of this file) —
-- this script does not archive anything, it drops it.
-- =============================================================


-- ─────────────────────────────────────────────
-- 3. Drop referral_audit_logs (reverse of §3)
-- ─────────────────────────────────────────────
DROP TABLE IF EXISTS public.referral_audit_logs;


-- ─────────────────────────────────────────────
-- 2. Drop referral_withdrawals (reverse of §2)
-- ─────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_referral_withdrawals_updated_at ON public.referral_withdrawals;
DROP FUNCTION IF EXISTS public.set_referral_withdrawals_updated_at();
DROP TABLE IF EXISTS public.referral_withdrawals;


-- ─────────────────────────────────────────────
-- 1. Revert referral_commissions additive changes (reverse of §1)
-- ─────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_referral_commissions_updated_at ON public.referral_commissions;
DROP FUNCTION IF EXISTS public.set_referral_commissions_updated_at();

DROP INDEX IF EXISTS idx_referral_commissions_commission_level;
DROP INDEX IF EXISTS idx_referral_commissions_source_job_id;

ALTER TABLE public.referral_commissions
    DROP CONSTRAINT IF EXISTS referral_commissions_commission_level_check;

ALTER TABLE public.referral_commissions
    DROP COLUMN IF EXISTS source_job_id;
ALTER TABLE public.referral_commissions
    DROP COLUMN IF EXISTS commission_level;
ALTER TABLE public.referral_commissions
    DROP COLUMN IF EXISTS updated_at;

-- The metadata column itself is NOT dropped (it pre-dates this migration
-- and belongs to Gen 1) — only the COMMENT ON COLUMN this migration added
-- to it is implicitly superseded the next time someone comments on it
-- again; comments are not versioned, so there is nothing further to revert.


-- =============================================================
-- Pre-flight checks — run these BEFORE executing the drops above if
-- Stage 2/3 work may have already started:
--
--   SELECT count(*) FROM public.referral_withdrawals;
--   SELECT count(*) FROM public.referral_audit_logs;
--   SELECT count(*) FROM public.referral_commissions WHERE commission_level IS NOT NULL OR source_job_id IS NOT NULL;
--
-- If any of these return > 0, stop and export/archive the rows first —
-- this rollback does not preserve them.
-- =============================================================
