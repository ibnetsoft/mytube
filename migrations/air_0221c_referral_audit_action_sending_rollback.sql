-- =============================================================
-- Rollback: AIR-0221C — referral_audit_logs.action: remove 'sending'
-- Reverses migrations/air_0221c_referral_audit_action_sending.sql exactly,
-- restoring the original Stage-1 CHECK constraint.
--
-- Safe as long as no row with action = 'sending' exists yet (true today —
-- Stage 2 dual-write hasn't been implemented, so nothing writes to
-- referral_audit_logs at all). If Stage 2 has since started writing
-- 'sending' rows, this rollback will FAIL LOUDLY at the VALIDATE
-- CONSTRAINT step below (Postgres refuses to validate a CHECK constraint
-- that existing rows violate) rather than silently corrupting/orphaning
-- that data — check first with the query at the bottom of this file.
-- =============================================================

ALTER TABLE public.referral_audit_logs
    DROP CONSTRAINT IF EXISTS referral_audit_logs_action_check;

ALTER TABLE public.referral_audit_logs
    ADD CONSTRAINT referral_audit_logs_action_check
    CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'completed', 'reversed'))
    NOT VALID;

ALTER TABLE public.referral_audit_logs
    VALIDATE CONSTRAINT referral_audit_logs_action_check;

COMMENT ON COLUMN public.referral_audit_logs.action IS
    'AIR-0221 Stage 1 (additive). admin_audit_logs (Gen 3) does not exist in production and is not reused. Records commission-generation and withdrawal-approve/reject/complete events for the Audit Log dashboard tab (CONSOLIDATION_PLAN.md §10.4). actor_id is NULL for system-generated commission events (no human actor) and set for admin withdrawal actions. Not yet written to by any application code.';

-- =============================================================
-- Pre-flight check — run BEFORE executing the drop/re-add above if
-- Stage 2 dual-write may have already started:
--
--   SELECT count(*) FROM public.referral_audit_logs WHERE action = 'sending';
--
-- If this returns > 0, do not run this rollback as-is — either update
-- those rows to a different action value first, or keep 'sending' in
-- the constraint until those rows are dealt with.
-- =============================================================
