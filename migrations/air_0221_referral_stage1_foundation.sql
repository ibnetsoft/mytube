-- =============================================================
-- Migration: AIR-0221 Stage 1 — Referral Consolidation, Additive Schema Foundation
-- Description:
--   Additive-only schema foundation for promoting the live Gen-1
--   referral_commissions engine to the CTO-approved final model
--   (CONSOLIDATION_PLAN.md §10). No existing column/table/row is
--   dropped, renamed, or mutated. No application code reads or
--   writes any of this yet — that's Stage 2/3.
--
--   Pre-flight check performed against production before writing this
--   file (read-only, via PostgREST): referral_commissions currently
--   has 0 rows, so there is no existing data that could violate the
--   new CHECK constraint below. The NOT VALID / VALIDATE CONSTRAINT
--   pattern is still used regardless, so this migration is safe to
--   re-run later against an environment that does have data.
--
--   Safe to run multiple times (every DDL statement is idempotent:
--   IF NOT EXISTS / OR REPLACE / DROP ... IF EXISTS before CREATE).
-- =============================================================


-- ─────────────────────────────────────────────
-- 1. referral_commissions — additive columns only
--    (commission_type, base_tokens, rate_percent, commission_tokens,
--    status, metadata, created_at, paid_at are all left untouched)
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

-- Validate any existing data before the CHECK constraint takes effect
-- (NOT VALID adds the constraint for all new/updated rows immediately,
-- without locking/scanning the table; VALIDATE CONSTRAINT below then
-- checks existing rows separately, and raises a clear error naming
-- this constraint if any row violates it).
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
--    Referral-earnings cash-out ledger. Per CTO decision
--    (CONSOLIDATION_PLAN.md §10.5), this is intended to eventually
--    replace BOTH the retired "negative commission row" withdrawal
--    pattern in referral_commissions AND the Gen-0 general-wallet
--    `withdrawals` table — that cutover is Stage 2/3, not this
--    migration. This table is created empty; nothing reads/writes
--    it yet.
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

-- NOTE on admin policies: the orphaned Gen-2 template this table's shape is
-- based on (migrations/air_0158d_withdrawal_ledger.sql) gates admin access
-- via `profiles.is_superadmin`. That column was verified NOT to exist in
-- production (confirmed via live schema introspection during this Stage —
-- see worknote/AIR-0221-Stage1.md). Live admin authorization actually runs
-- through a hardcoded email check in auth-web/app/api/admin/_auth.ts
-- (SUPER_ADMIN_EMAIL), enforced at the application layer, with all admin
-- routes using the service-role key (which bypasses RLS entirely). So no
-- admin-facing RLS policy is created here — a policy referencing
-- profiles.is_superadmin would fail to even apply, and would be redundant
-- with the real access-control mechanism regardless. Only end-user-facing
-- policies (a user reading/creating their own withdrawal rows) are added.
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
--    admin_audit_logs (Gen 3, air_0201a_admin_treasury.sql) was
--    checked and confirmed NOT present in the live schema, so it is
--    not reused. This table exists as a foundation only — no
--    application code writes to it yet (Stage 2/3 wires it up when
--    the withdrawal approve/reject/complete endpoints are cut over).
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
-- Intentionally no policies: this is an admin/system-only audit trail.
-- Only the service role (which bypasses RLS) may read or write it, matching
-- how every existing admin API route in this codebase already operates.

-- =============================================================
-- End of AIR-0221 Stage 1 migration.
-- Explicitly NOT done here (by design — see worknote/AIR-0221-Stage1.md):
--   - No changes to Gen 2/3 (commissions, withdrawal_requests, worker_jobs,
--     risk_flags, user_activity, user_events, referral_trees, or their RPCs).
--   - No changes to the Gen-0 `withdrawals` table.
--   - No DROP of referral_rewards_log or the $20 instant-reward code path.
--   - No application code (auth-web API routes, desktop app) reads or
--     writes any column/table added by this migration.
-- =============================================================
