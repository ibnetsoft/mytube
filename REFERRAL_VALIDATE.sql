-- =============================================================
-- AIR-0224 — Validation Script
-- Run after REFERRAL_TEST_FIXTURE.sql's Parts A-C. Self-verifying (same
-- pattern as migrations/air_0221_referral_stage1_foundation_APPLY.sql) —
-- any RAISE EXCEPTION means a check failed; read the message to see which.
-- Read-only except for the Scenario 5 block at the bottom, which is
-- self-reverting (inserts a duplicate, checks detection, deletes it).
-- =============================================================

DO $$
DECLARE
    v_count INT;
    v_ds_id UUID;
    v_a_id UUID;
    v_b_id UUID;
    v_c_id UUID;
    v_ds_total NUMERIC;
    v_a_total NUMERIC;
    v_b_total NUMERIC;
    v_c_total NUMERIC;
BEGIN
    SELECT id INTO v_ds_id FROM public.profiles WHERE email = 'e2e-default-sponsor@airqa.test';
    SELECT id INTO v_a_id  FROM public.profiles WHERE email = 'e2e-user-a@airqa.test';
    SELECT id INTO v_b_id  FROM public.profiles WHERE email = 'e2e-user-b@airqa.test';
    SELECT id INTO v_c_id  FROM public.profiles WHERE email = 'e2e-user-c@airqa.test';

    IF v_ds_id IS NULL OR v_a_id IS NULL OR v_b_id IS NULL OR v_c_id IS NULL THEN
        RAISE EXCEPTION 'VALIDATE FAILED: one or more test accounts missing. Run REFERRAL_TEST_ACCOUNTS.sh first.';
    END IF;

    -- 1. Referral chain
    IF (SELECT referred_by FROM public.profiles WHERE id = v_a_id) <> v_ds_id THEN
        RAISE EXCEPTION 'VALIDATE FAILED (1): User A not referred by Default Sponsor';
    END IF;
    IF (SELECT referred_by FROM public.profiles WHERE id = v_b_id) <> v_a_id THEN
        RAISE EXCEPTION 'VALIDATE FAILED (1): User B not referred by User A';
    END IF;
    IF (SELECT referred_by FROM public.profiles WHERE id = v_c_id) <> v_b_id THEN
        RAISE EXCEPTION 'VALIDATE FAILED (1): User C not referred by User B';
    END IF;
    RAISE NOTICE 'CHECK 1 PASS: referral chain DS <- A <- B <- C confirmed.';

    -- 2. Baseline row count
    SELECT count(*) INTO v_count FROM public.referral_commissions
    WHERE metadata->>'air_0224_fixture' = 'true' AND commission_type != 'WITHDRAWAL';
    IF v_count <> 9 THEN
        RAISE EXCEPTION 'VALIDATE FAILED (2): expected 9 baseline commission rows, found %', v_count;
    END IF;
    RAISE NOTICE 'CHECK 2 PASS: 9 baseline commission rows present.';

    -- 3. Per-account totals match REFERRAL_EXPECTED_RESULTS.md exactly
    SELECT coalesce(sum(commission_tokens),0) INTO v_ds_total FROM public.referral_commissions
        WHERE beneficiary_id = v_ds_id AND status='paid' AND commission_type != 'WITHDRAWAL';
    SELECT coalesce(sum(commission_tokens),0) INTO v_a_total FROM public.referral_commissions
        WHERE beneficiary_id = v_a_id AND status='paid' AND commission_type != 'WITHDRAWAL';
    SELECT coalesce(sum(commission_tokens),0) INTO v_b_total FROM public.referral_commissions
        WHERE beneficiary_id = v_b_id AND status='paid' AND commission_type != 'WITHDRAWAL';
    SELECT coalesce(sum(commission_tokens),0) INTO v_c_total FROM public.referral_commissions
        WHERE beneficiary_id = v_c_id AND status='paid' AND commission_type != 'WITHDRAWAL';

    IF v_ds_total <> 2 THEN RAISE EXCEPTION 'VALIDATE FAILED (3): Default Sponsor total = % (expected 2)', v_ds_total; END IF;
    IF v_a_total  <> 35 THEN RAISE EXCEPTION 'VALIDATE FAILED (3): User A total = % (expected 35)', v_a_total; END IF;
    IF v_b_total  <> 80 THEN RAISE EXCEPTION 'VALIDATE FAILED (3): User B total = % (expected 80)', v_b_total; END IF;
    IF v_c_total  <> 0  THEN RAISE EXCEPTION 'VALIDATE FAILED (3): User C total = % (expected 0)', v_c_total; END IF;
    RAISE NOTICE 'CHECK 3 PASS: per-account totals match (DS=2, A=35, B=80, C=0).';

    -- 4. Scenario 2 — Job 3 produced exactly one L1 (User B, 5) and one L2 (User A, 2)
    IF NOT EXISTS (
        SELECT 1 FROM public.referral_commissions
        WHERE source_job_id = 'E2E-JOB-003' AND beneficiary_id = v_b_id AND commission_level = 1 AND commission_tokens = 5
    ) THEN
        RAISE EXCEPTION 'VALIDATE FAILED (4): Job 3 L1 row for User B missing or wrong amount';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.referral_commissions
        WHERE source_job_id = 'E2E-JOB-003' AND beneficiary_id = v_a_id AND commission_level = 2 AND commission_tokens = 2
    ) THEN
        RAISE EXCEPTION 'VALIDATE FAILED (4): Job 3 L2 row for User A missing or wrong amount';
    END IF;
    RAISE NOTICE 'CHECK 4 PASS: Scenario 2 (Level 2) rows correct.';

    -- 5. Scenario 1 — withdrawal + mirror + audit parity
    IF NOT EXISTS (
        SELECT 1 FROM public.referral_commissions
        WHERE metadata->>'scenario' = 'scenario1_withdrawal' AND commission_type = 'WITHDRAWAL'
          AND status = 'COMPLETED' AND commission_tokens = -30
    ) THEN
        RAISE EXCEPTION 'VALIDATE FAILED (5): legacy withdrawal row not COMPLETED / -30 as expected';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.referral_withdrawals
        WHERE metadata->>'scenario' = 'scenario1_withdrawal' AND status = 'COMPLETED' AND amount = 30
          AND approved_at IS NOT NULL AND sent_at IS NOT NULL AND completed_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'VALIDATE FAILED (5): mirrored referral_withdrawals row not COMPLETED / timestamps missing';
    END IF;
    SELECT count(*) INTO v_count FROM public.referral_audit_logs WHERE metadata->>'scenario' = 'scenario1_withdrawal';
    IF v_count <> 4 THEN
        RAISE EXCEPTION 'VALIDATE FAILED (5): expected 4 audit rows (requested+approved+sending+completed), found %', v_count;
    END IF;
    RAISE NOTICE 'CHECK 5 PASS: Scenario 1 withdrawal legacy/mirror/audit all consistent.';

    -- 6. User B available balance after withdrawal = 80 - 30 = 50
    IF v_b_total - 30 <> 50 THEN
        RAISE EXCEPTION 'VALIDATE FAILED (6): User B post-withdrawal balance math wrong (% - 30 != 50)', v_b_total;
    END IF;
    RAISE NOTICE 'CHECK 6 PASS: User B available balance after withdrawal = 50.';

    -- 7. Scenario 5 baseline state: no duplicates in the CLEAN fixture
    IF EXISTS (
        SELECT 1 FROM public.referral_commissions
        WHERE commission_type != 'WITHDRAWAL' AND metadata->>'air_0224_fixture' = 'true'
        GROUP BY source_job_id, beneficiary_id, commission_level
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'VALIDATE FAILED (7): duplicate commission row(s) found in the baseline fixture (should be clean — did Scenario 5''s temporary insert not get cleaned up?)';
    END IF;
    RAISE NOTICE 'CHECK 7 PASS: no duplicate rows in baseline fixture (Scenario 5 clean state confirmed).';

    -- 8. Scenario 4 — invalid referral code matches nothing
    SELECT count(*) INTO v_count FROM public.profiles WHERE referral_code = 'E2E-NONEXISTENT-CODE';
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'VALIDATE FAILED (8): E2E-NONEXISTENT-CODE unexpectedly matched % profile(s)', v_count;
    END IF;
    RAISE NOTICE 'CHECK 8 PASS: invalid referral code matches zero profiles, as expected.';

    RAISE NOTICE '=== ALL CHECKS PASSED ===';
END $$;

-- =============================================================
-- Scenario 5 — idempotency DETECTION test (self-reverting: insert duplicate,
-- verify detection, delete it). Run this block separately from the DO block
-- above (it intentionally creates a transient duplicate, so it must not run
-- inside the same read-only validation pass).
-- =============================================================
-- BEGIN;
-- INSERT INTO public.referral_commissions
--     (beneficiary_id, source_user_id, commission_type, commission_level, source_job_id,
--      base_tokens, rate_percent, commission_tokens, status, metadata, created_at, paid_at)
-- SELECT beneficiary_id, source_user_id, commission_type, commission_level, source_job_id,
--        base_tokens, rate_percent, commission_tokens, status,
--        '{"air_0224_fixture": true, "scenario": "scenario5_duplicate_TEMPORARY"}'::jsonb, now(), now()
-- FROM public.referral_commissions
-- WHERE source_job_id = 'E2E-JOB-003' AND commission_level = 1 LIMIT 1;
--
-- DO $$
-- DECLARE v_dupe_count INT;
-- BEGIN
--     SELECT count(*) INTO v_dupe_count FROM (
--         SELECT source_job_id, beneficiary_id, commission_level, count(*) c
--         FROM public.referral_commissions
--         WHERE commission_type != 'WITHDRAWAL' AND metadata->>'air_0224_fixture' = 'true'
--         GROUP BY source_job_id, beneficiary_id, commission_level
--         HAVING count(*) > 1
--     ) dupes;
--     IF v_dupe_count <> 1 THEN
--         RAISE EXCEPTION 'Scenario 5 FAILED: expected exactly 1 duplicated (source_job_id,beneficiary,level) group, found %', v_dupe_count;
--     END IF;
--     RAISE NOTICE 'Scenario 5 PASS: duplicate correctly detected.';
-- END $$;
--
-- DELETE FROM public.referral_commissions WHERE metadata->>'scenario' = 'scenario5_duplicate_TEMPORARY';
-- COMMIT;
