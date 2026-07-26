-- =============================================================
-- AIR-0224 — Referral E2E Test Fixture
--
-- PREREQUISITE: run REFERRAL_TEST_ACCOUNTS.sh first (creates the 4 test
-- auth.users/profiles rows — cannot be done in plain SQL, see that script's
-- header comment for why). This file assumes those 4 profiles already exist,
-- looked up by email (not hardcoded UUIDs, so it doesn't matter what ids
-- the Admin API actually assigned).
--
-- Every row this file inserts is tagged metadata.air_0224_fixture = true,
-- for unambiguous identification and cleanup (see Part H).
--
-- NOT EXECUTED as part of writing this file — see
-- REFERRAL_E2E_TEST_PLAN.md §7 for what needs sign-off before running.
--
-- Rates: referral_level1_percent=5, referral_level2_percent=2 (CTO-final).
-- Rounding: ROUND() (Postgres numeric = round-half-away-from-zero), see
-- REFERRAL_EXPECTED_RESULTS.md for the full worked table this matches.
-- =============================================================

BEGIN;

-- ─────────────────────────────────────────────
-- Part A — sanity check the 4 accounts exist before doing anything else
-- ─────────────────────────────────────────────
DO $$
DECLARE
    v_count INT;
BEGIN
    SELECT count(*) INTO v_count FROM public.profiles
    WHERE email IN (
        'e2e-default-sponsor@airqa.test',
        'e2e-user-a@airqa.test',
        'e2e-user-b@airqa.test',
        'e2e-user-c@airqa.test'
    );
    IF v_count <> 4 THEN
        RAISE EXCEPTION 'AIR-0224 fixture check FAILED: expected 4 test profiles, found %. Run REFERRAL_TEST_ACCOUNTS.sh first.', v_count;
    END IF;

    -- Verify the referred_by chain is exactly as expected (catches a
    -- misconfigured Admin API call before any commission data is inserted).
    IF (SELECT referred_by FROM public.profiles WHERE email = 'e2e-user-a@airqa.test')
        <> (SELECT id FROM public.profiles WHERE email = 'e2e-default-sponsor@airqa.test') THEN
        RAISE EXCEPTION 'AIR-0224 fixture check FAILED: User A.referred_by does not point to Default Sponsor';
    END IF;
    IF (SELECT referred_by FROM public.profiles WHERE email = 'e2e-user-b@airqa.test')
        <> (SELECT id FROM public.profiles WHERE email = 'e2e-user-a@airqa.test') THEN
        RAISE EXCEPTION 'AIR-0224 fixture check FAILED: User B.referred_by does not point to User A';
    END IF;
    IF (SELECT referred_by FROM public.profiles WHERE email = 'e2e-user-c@airqa.test')
        <> (SELECT id FROM public.profiles WHERE email = 'e2e-user-b@airqa.test') THEN
        RAISE EXCEPTION 'AIR-0224 fixture check FAILED: User C.referred_by does not point to User B';
    END IF;

    RAISE NOTICE 'Part A: account chain verified.';
END $$;

-- ─────────────────────────────────────────────
-- Part B — baseline commission rows (Test Jobs 1-5, simulated Job Completed)
-- All status='paid' (AIR-0221D's target auto-paid flow), commission_type='direct'/'level2'
-- matching settlement.ts's existing free-text convention.
-- ─────────────────────────────────────────────
INSERT INTO public.referral_commissions
    (beneficiary_id, source_user_id, commission_type, commission_level, source_job_id,
     base_tokens, rate_percent, commission_tokens, status, metadata, created_at, paid_at)
VALUES
    -- JOB-001: amount=10, by User A -> L1 to Default Sponsor only (root has no L2)
    ((SELECT id FROM public.profiles WHERE email='e2e-default-sponsor@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-a@airqa.test'),
     'direct', 1, 'E2E-JOB-001', 10, 5.00, 1, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),

    -- JOB-002: amount=50, by User B -> L1 to User A, L2 to Default Sponsor
    ((SELECT id FROM public.profiles WHERE email='e2e-user-a@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
     'direct', 1, 'E2E-JOB-002', 50, 5.00, 3, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),
    ((SELECT id FROM public.profiles WHERE email='e2e-default-sponsor@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
     'level2', 2, 'E2E-JOB-002', 50, 2.00, 1, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),

    -- JOB-003: amount=100, by User C -> L1 to User B, L2 to User A (ticket's own worked example: 100 -> 5 / 2)
    ((SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'direct', 1, 'E2E-JOB-003', 100, 5.00, 5, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline_and_scenario2"}'::jsonb, now(), now()),
    ((SELECT id FROM public.profiles WHERE email='e2e-user-a@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'level2', 2, 'E2E-JOB-003', 100, 2.00, 2, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline_and_scenario2"}'::jsonb, now(), now()),

    -- JOB-004: amount=500, by User C -> L1 to User B, L2 to User A
    ((SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'direct', 1, 'E2E-JOB-004', 500, 5.00, 25, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),
    ((SELECT id FROM public.profiles WHERE email='e2e-user-a@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'level2', 2, 'E2E-JOB-004', 500, 2.00, 10, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),

    -- JOB-005: amount=1000, by User C -> L1 to User B, L2 to User A
    ((SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'direct', 1, 'E2E-JOB-005', 1000, 5.00, 50, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now()),
    ((SELECT id FROM public.profiles WHERE email='e2e-user-a@airqa.test'),
     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
     'level2', 2, 'E2E-JOB-005', 1000, 2.00, 20, 'paid',
     '{"air_0224_fixture": true, "scenario": "baseline"}'::jsonb, now(), now());

DO $$
DECLARE v_count INT;
BEGIN
    SELECT count(*) INTO v_count FROM public.referral_commissions
    WHERE metadata->>'air_0224_fixture' = 'true';
    IF v_count <> 9 THEN
        RAISE EXCEPTION 'Part B FAILED: expected 9 fixture commission rows, found %', v_count;
    END IF;
    RAISE NOTICE 'Part B: 9 baseline commission rows inserted and counted correctly.';
END $$;

-- ─────────────────────────────────────────────
-- Part C — Scenario 1: withdrawal request + admin approval (replicates the
-- real Stage 2 dual-write code paths exactly, see
-- app/routers/referral.py:317- and app/routers/admin_referrals.py's
-- _stage2_dual_write_withdrawal_transition / the AIR-0223 TS port).
-- User B requests 30 (has 80 available per REFERRAL_EXPECTED_RESULTS.md).
-- ─────────────────────────────────────────────
INSERT INTO public.referral_commissions
    (beneficiary_id, source_user_id, commission_type, commission_tokens, status, metadata, created_at)
VALUES (
    (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
    (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
    'WITHDRAWAL', -30, 'PENDING',
    '{"air_0224_fixture": true, "scenario": "scenario1_withdrawal", "dest_address": "0xE2ETESTFIXTURE"}'::jsonb,
    now()
);

INSERT INTO public.referral_withdrawals
    (user_id, amount, wallet_address, status, metadata, requested_at)
VALUES (
    (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
    30, '0xE2ETESTFIXTURE', 'REQUESTED',
    jsonb_build_object(
        'air_0224_fixture', true,
        'legacy_source', 'referral_negative_commission',
        'legacy_commission_id', (
            SELECT id FROM public.referral_commissions
            WHERE metadata->>'scenario' = 'scenario1_withdrawal' LIMIT 1
        )
    ),
    now()
);

INSERT INTO public.referral_audit_logs (entity_type, entity_id, action, actor_id, reason, metadata, created_at)
VALUES (
    'withdrawal',
    (SELECT id FROM public.referral_withdrawals WHERE metadata->>'scenario' = 'scenario1_withdrawal'),
    'requested', NULL, 'E2E fixture withdrawal request',
    '{"air_0224_fixture": true, "scenario": "scenario1_withdrawal"}'::jsonb, now()
);

-- Admin approval: legacy row -> COMPLETED, mirror -> APPROVED -> SENDING -> COMPLETED,
-- 3 audit rows. (In the real endpoints this is 3 separate UPDATEs with 3
-- separate timestamps; collapsed to "now()" three times here since this is a
-- fixture, not a timing test.)
UPDATE public.referral_commissions
SET status = 'COMPLETED',
    metadata = metadata || jsonb_build_object(
        'audit_trail', jsonb_build_array(jsonb_build_object(
            'admin', 'e2e-fixture-script', 'time', now()::text,
            'old_status', 'PENDING', 'new_status', 'COMPLETED',
            'reason', 'AIR-0224 E2E fixture approval', 'source', 'fixture_script'
        ))
    )
WHERE metadata->>'scenario' = 'scenario1_withdrawal' AND commission_type = 'WITHDRAWAL';

UPDATE public.referral_withdrawals
SET status = 'COMPLETED', approved_at = now(), sent_at = now(), completed_at = now(), reason = 'AIR-0224 E2E fixture approval'
WHERE metadata->>'scenario' = 'scenario1_withdrawal';

INSERT INTO public.referral_audit_logs (entity_type, entity_id, action, actor_id, reason, metadata, created_at)
SELECT 'withdrawal', id, action, NULL, 'AIR-0224 E2E fixture approval',
       '{"air_0224_fixture": true, "scenario": "scenario1_withdrawal"}'::jsonb, now()
FROM public.referral_withdrawals, unnest(ARRAY['approved', 'sending', 'completed']) AS action
WHERE metadata->>'scenario' = 'scenario1_withdrawal';

DO $$
DECLARE v_count INT;
BEGIN
    SELECT count(*) INTO v_count FROM public.referral_audit_logs WHERE metadata->>'scenario' = 'scenario1_withdrawal';
    IF v_count <> 4 THEN -- 1 requested + 3 approval-sequence
        RAISE EXCEPTION 'Part C FAILED: expected 4 audit rows for scenario1_withdrawal, found %', v_count;
    END IF;
    RAISE NOTICE 'Part C: Scenario 1 withdrawal request+approval simulated, audit trail correct.';
END $$;

COMMIT;

-- =============================================================
-- Part D — Scenario 3: Default Sponsor (SEPARATE TRANSACTION, GATED —
-- do not run without separate sign-off, see REFERRAL_E2E_TEST_PLAN.md §7.
-- This temporarily changes a LIVE global_settings value that affects every
-- real organic signup while set. Run this block, verify, then run the
-- restore block immediately after — do not leave it set.
-- =============================================================
-- BEGIN;
-- -- Save whatever was there before (should be NULL/absent today per Stage 2
-- -- bake-watch baseline, but check first regardless):
-- SELECT value FROM public.global_settings WHERE key = 'referral_default_sponsor_uuid';
--
-- INSERT INTO public.global_settings (key, value) VALUES
--     ('referral_default_sponsor_uuid', (SELECT id::text FROM public.profiles WHERE email='e2e-default-sponsor@airqa.test'))
-- ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
--
-- -- Now perform ONE no-referral-code signup through the real app/routers/auth.py
-- -- endpoint (not simulated here — this must go through the real code path to
-- -- actually test it) using a throwaway email, e.g. e2e-user-d@airqa.test.
-- -- Then verify:
-- -- SELECT referred_by FROM public.profiles WHERE email = 'e2e-user-d@airqa.test';
-- -- Expect it to equal the Default Sponsor's id.
--
-- -- IMMEDIATELY RESTORE (do not leave this set):
-- DELETE FROM public.global_settings WHERE key = 'referral_default_sponsor_uuid';
-- -- (or UPDATE back to the prior value if the SELECT above returned a real row)
-- COMMIT;

-- =============================================================
-- Part E — Scenario 4: invalid referral code (read-only, safe to run anytime)
-- =============================================================
-- SELECT count(*) FROM public.profiles WHERE referral_code = 'E2E-NONEXISTENT-CODE';
-- -- Expect 0. Confirms validate_referral_code() would return false for it,
-- -- meaning app/routers/auth.py's signup handler rejects before any write.

-- =============================================================
-- Part F — Scenario 5: idempotency detection (SEPARATE, gated, self-reverting —
-- run only to demonstrate the detection query catches a duplicate, then
-- immediately delete the duplicate so the baseline stays clean for §6
-- Dashboard QA).
-- =============================================================
-- BEGIN;
-- INSERT INTO public.referral_commissions
--     (beneficiary_id, source_user_id, commission_type, commission_level, source_job_id,
--      base_tokens, rate_percent, commission_tokens, status, metadata, created_at, paid_at)
-- VALUES (
--     (SELECT id FROM public.profiles WHERE email='e2e-user-b@airqa.test'),
--     (SELECT id FROM public.profiles WHERE email='e2e-user-c@airqa.test'),
--     'direct', 1, 'E2E-JOB-003', 100, 5.00, 5, 'paid',
--     '{"air_0224_fixture": true, "scenario": "scenario5_duplicate_TEMPORARY"}'::jsonb, now(), now()
-- );
--
-- -- Run the detection query (see REFERRAL_VALIDATE.sql) — expect it to now
-- -- return 1 row: source_job_id='E2E-JOB-003', beneficiary=User B, level=1, count=2.
--
-- DELETE FROM public.referral_commissions WHERE metadata->>'scenario' = 'scenario5_duplicate_TEMPORARY';
-- COMMIT;

-- =============================================================
-- Part H — Full teardown (run when finished with E2E testing; run this
-- BEFORE deleting the auth.users rows via REFERRAL_TEST_ACCOUNTS.sh's
-- teardown snippet, since referral_audit_logs doesn't cascade-delete)
-- =============================================================
-- BEGIN;
-- DELETE FROM public.referral_audit_logs WHERE metadata->>'air_0224_fixture' = 'true';
-- DELETE FROM public.referral_withdrawals WHERE metadata->>'air_0224_fixture' = 'true';
-- DELETE FROM public.referral_commissions WHERE metadata->>'air_0224_fixture' = 'true';
-- -- Then run REFERRAL_TEST_ACCOUNTS.sh's teardown snippet to delete the 4 auth.users rows.
-- COMMIT;
