-- =============================================================
-- Migration: AIR-0221C — referral_audit_logs.action: add 'sending'
-- Description:
--   Stage 1 (air_0221_referral_stage1_foundation.sql) created
--   referral_audit_logs with:
--     action TEXT NOT NULL CHECK (action IN
--       ('generated','requested','approved','rejected','completed','reversed'))
--   The Stage 2 dual-write plan (AIR-0221_Stage2_DUAL_WRITE_PLAN.md §5)
--   surfaced that this list has no 'sending' value, needed for the
--   withdrawal state machine's REQUESTED -> APPROVED -> SENDING ->
--   COMPLETED/REJECTED transitions (referral_withdrawals.status already
--   includes 'SENDING' from Stage 1 — this migration only brings the
--   audit-log action vocabulary into parity with it).
--
--   Scope: this migration touches ONLY
--   referral_audit_logs.action's CHECK constraint. No other column,
--   no other table (referral_commissions, referral_withdrawals
--   themselves are untouched), no Gen 2/3 object, no application code.
--
--   Pre-flight: referral_audit_logs has 0 rows in production (confirmed
--   at Stage 1 apply and unchanged since — nothing writes to this table
--   yet, Stage 2 dual-write implementation hasn't started). The
--   NOT VALID / VALIDATE CONSTRAINT pattern is used anyway, matching
--   Stage 1's style, so this migration stays safe to re-run later
--   against an environment that does have rows.
--
--   Safe to run multiple times (DROP CONSTRAINT IF EXISTS before ADD).
-- =============================================================

-- Validate any existing data before the new CHECK constraint takes effect
-- (NOT VALID adds the constraint for all new/updated rows immediately,
-- without locking/scanning the table; VALIDATE CONSTRAINT below then
-- checks existing rows separately).
ALTER TABLE public.referral_audit_logs
    DROP CONSTRAINT IF EXISTS referral_audit_logs_action_check;

ALTER TABLE public.referral_audit_logs
    ADD CONSTRAINT referral_audit_logs_action_check
    CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'sending', 'completed', 'reversed'))
    NOT VALID;

ALTER TABLE public.referral_audit_logs
    VALIDATE CONSTRAINT referral_audit_logs_action_check;

COMMENT ON COLUMN public.referral_audit_logs.action IS
    'AIR-0221C: allowed values are generated | requested | approved | rejected | sending | completed | reversed. ''sending'' added to match referral_withdrawals.status''s SENDING state (Stage 1) — originally missing from the Stage-1-authored CHECK constraint, found during Stage 2 dual-write planning before any Stage 2 code was written.';

-- =============================================================
-- End of AIR-0221C migration.
-- Explicitly NOT done here:
--   - No Stage 2 dual-write application code.
--   - No changes to referral_commissions or referral_withdrawals.
--   - No changes to Gen 2/3.
-- =============================================================
