# AIR-0224 — Referral End-to-End Test Environment: Test Plan

**Status: artifacts written, NOT yet executed against production.** This ticket doesn't prohibit DB writes the way AIR-0221's sub-tickets did, but test-account creation touches `auth.users` (a shared system) and one scenario requires a *temporary* change to a live `global_settings` value that affects real user signups — both warrant an explicit go/no-go before running, same discipline as every DDL apply this project has done. See §7 for exactly what needs sign-off and why.

**Constraints honored**: no new referral feature code, no referral logic changes, no Stage 3 cutover, no Settlement Engine implementation, `referral_mode` stays `OFF` throughout. Because there is no live Job-Completed trigger yet (deferred per `AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`), "Job Completed" test data is **simulated via direct data insertion**, not by exercising a real trigger — there is nothing to exercise yet. What *is* real and gets exercised end-to-end: the Stage 2 dual-write withdrawal request/approval code paths (already built, unchanged), and the signup-time referral-attribution logic in `app/routers/auth.py` (already built, unchanged, AIR-0122).

---

## 1. Test Fixture — accounts

Four accounts, plain chain (matches the ticket's diagram exactly):

```
Default Sponsor (DS)
      ↓ (A.referred_by = DS)
   User A
      ↓ (B.referred_by = A)
   User B
      ↓ (C.referred_by = B)
   User C
```

This gives, from every account's own perspective:
- **A**: L1 sponsor = DS. No L2 (DS has no sponsor).
- **B**: L1 sponsor = A. L2 sponsor = DS.
- **C**: L1 sponsor = B. L2 sponsor = A.
- **DS**: root, earns L1 from A's jobs and L2 from B's jobs. Has no sponsor itself.

| Account | Email | Referral Code | Country |
|---|---|---|---|
| Default Sponsor | `e2e-default-sponsor@airqa.test` | `E2ETESTDS` | KR |
| User A | `e2e-user-a@airqa.test` | `E2ETESTA` | KR |
| User B | `e2e-user-b@airqa.test` | `E2ETESTB` | US |
| User C | `e2e-user-c@airqa.test` | `E2ETESTC` | US |

`.test` is an IANA-reserved TLD (RFC 2606) that will never resolve to a real mail server — safe, unambiguous, and every row is `LIKE '%@airqa.test'`-greppable for cleanup.

**Why account creation isn't plain SQL `INSERT INTO profiles`**: `profiles.id REFERENCES auth.users(id) ON DELETE CASCADE` (confirmed in `auth-web/supabase_schema.sql:10`). A profile row cannot exist without a matching `auth.users` row, and `auth.users` has many fields (encrypted password, confirmation tokens, GoTrue-internal columns) that are fragile to hand-craft correctly via raw SQL against a live production auth schema. `REFERRAL_TEST_FIXTURE.sql` therefore creates accounts via the **Supabase Admin API** (`POST /auth/v1/admin/users`), the exact same mechanism `services/web_admin_client.py`'s `create_auth_user()` already uses for real signups — not a new mechanism, just the existing one pointed at test data. The `on_auth_user_created` trigger (`handle_new_user()`, already live, unmodified) then creates the `profiles` row and sets `referred_by` from `raw_user_meta_data.referred_by_id`, exactly as it does for real signups.

`referral_code` is set via a follow-up `UPDATE` after creation (not relied on to be auto-generated with a predictable value) so the fixture is deterministic.

`ON DELETE CASCADE` means teardown is one operation: delete the 4 `auth.users` rows, and `profiles` + every dependent row (via further cascades, where they exist) goes with them. `referral_commissions`/`referral_withdrawals`/`referral_audit_logs` do **not** have `ON DELETE CASCADE` from `profiles` (checked: `beneficiary_id ... ON DELETE CASCADE` on `referral_commissions` actually *does* cascade; `referral_withdrawals.user_id` also cascades per the Stage 1 migration) — so deleting the 4 auth users cleans up everything the fixture created, including commission/withdrawal/audit rows. This is spelled out explicitly in the fixture script's teardown section.

## 2. Test Jobs — simulated "Job Completed" events

Five jobs, amounts per the ticket's example (10/50/100/500/1000), attributed across the chain to exercise both L1-only and L1+L2 combined cases:

| Job ID | Amount (Net Settlement, simulated) | Completed by |
|---|---|---|
| `E2E-JOB-001` | 10 | User A |
| `E2E-JOB-002` | 50 | User B |
| `E2E-JOB-003` | 100 | User C |
| `E2E-JOB-004` | 500 | User C |
| `E2E-JOB-005` | 1000 | User C |

## 3. Expected Commission — the `bigint` finding

**`referral_commissions.commission_tokens` and `base_tokens` are `bigint` in the live schema** (confirmed via PostgREST introspection: `{"format": "bigint", "type": "integer"}`), not a decimal type. `referral_level1_percent`/`referral_level2_percent` are 5%/2% (CTO-finalized, `AIR-0221D`). 5%/2% of amounts like 10 or 50 produce fractional results (0.5, 2.5) that **cannot be stored as-is** in a `bigint` column.

This is a **new finding, surfaced here for the future Settlement Engine Specification, not resolved by this ticket** (Settlement Engine implementation is explicitly out of scope). `auth-web/lib/settlement.ts`'s current rounding (`Math.round(amount * (percent/100) * 100) / 100`) still produces a JS float like `0.5`, which would hit this exact same `bigint` mismatch if it ever ran against a real recharge of that size — meaning this may already be a latent bug in the live settlement worker, independent of AIR-0224. Flagging it, not fixing it (fixing `settlement.ts` would be a referral-logic change, explicitly forbidden here).

For this fixture, every commission value is computed with standard SQL `ROUND()` (round-half-away-from-zero, e.g. `ROUND(2.5) = 3`) and cast to `bigint`, with the exact rounding rule stated so it's auditable — see `REFERRAL_EXPECTED_RESULTS.md` for the full computed table. Whoever writes the Settlement Engine Specification needs to pick a rounding rule (this fixture's choice is a reasonable default, not a mandate).

## 4. E2E Scenarios

**Scenario 1 — Happy path (추천가입 → 작업완료 → 추천수당생성 → 출금요청 → 관리자승인 → Completed)**
Fixture creates the account chain (추천가입, via real signup-attribution code) → `E2E-JOB-003/004/005` simulate 작업완료 → 추천수당생성 (direct insert, `status='paid'`, since AIR-0221D's target flow is auto-paid with no pending step) → User B (who accumulates 80 across jobs 3/4/5's L1 share) requests a withdrawal of 30 via the **real** Stage 2 dual-write code path (replicated via REST exactly as `app/routers/referral.py:317-` performs it) → admin approves via the **real** Stage 2 admin dual-write path (replicated exactly as `app/routers/admin_referrals.py`'s `_stage2_dual_write_withdrawal_transition` / the AIR-0223 TypeScript port performs it) → verify final state is `COMPLETED` on both the legacy `referral_commissions` WITHDRAWAL row and the mirrored `referral_withdrawals` row, with 3 `referral_audit_logs` rows (approved/sending/completed).

**Scenario 2 — Level 2**
`E2E-JOB-003` (amount 100) in isolation: verify User C's job produces **both** an L1 row for User B (`commission_level=1`, amount 5) **and** an L2 row for User A (`commission_level=2`, amount 2) — the ticket's own worked example, chosen deliberately so this scenario's expected values are unambiguous.

**Scenario 3 — Default Sponsor**
Tests that a signup with **no** referral code attaches to the configured Default Sponsor. **Requires a temporary write to `global_settings.referral_default_sponsor_uuid`** (set to the test DS account's id, verify one no-code signup attaches correctly, then immediately clear it back) — this is a real, live setting that affects **every real organic signup** while set, so it is called out separately in §7, not bundled into the "safe" fixture execution.

**Scenario 4 — 추천코드 오류 (invalid referral code)**
No account creation needed. `app/routers/auth.py:331-333`'s logic (`if not web_admin_client.validate_referral_code(...): return {"success": False, "error": "..."}`) rejects before any write happens. Verified by: (a) code review (already done, matches AIR-0221D's earlier finding), and (b) a safe **read-only** query confirming a nonsense code (`E2E-NONEXISTENT-CODE`) matches zero `profiles` rows — proving `validate_referral_code()` would correctly return `false` for it, without needing to actually invoke the signup endpoint.

**Scenario 5 — 중복 Job (Idempotency)**
No live trigger exists yet to test idempotency *prevention* — that's Job-Completed-trigger implementation, explicitly deferred. What this scenario tests instead: the **validation script's ability to detect** a duplicate (`source_job_id` + `beneficiary_id` + `commission_level` appearing more than once), standing in for the check a real trigger implementation will need. Run as an isolated, clearly-labeled, immediately-reverted step — not part of the baseline fixture — so the "clean" 9-row baseline used for Dashboard QA (§6) never has a real duplicate sitting in it.

## 5. Validation Script

`REFERRAL_VALIDATE.sql` — a set of assertion-style SQL queries (same style as the Stage 1/AIR-0221C apply checklists), covering:
- Row counts and per-account commission sums match `REFERRAL_EXPECTED_RESULTS.md` exactly.
- `referral_withdrawals` mirror rows match their linked legacy `referral_commissions` WITHDRAWAL row (status, amount) — the same parity check design from `AIR-0221_Stage2_DUAL_WRITE_PLAN.md` §5, now runnable against real (test) data for the first time.
- `referral_audit_logs` has the expected count/shape of rows for every state transition exercised.
- The Scenario 5 duplicate-detection query (`GROUP BY source_job_id, beneficiary_id, commission_level HAVING COUNT(*) > 1`).

## 6. Dashboard QA (AIR-0223, against real fixture data)

Once the fixture is live, re-run the `AIR-0223_AUTH_QA_CHECKLIST.md` click-through — but this time every tab should show **real, predictable rows** instead of empty states: Organization should show the 4-account tree, Commission should list the 9 fixture rows, Withdrawals should show the Scenario 1 request/approval, Audit should show the corresponding entries, Member Detail should show correct L1/L2 lists and balances for each of the 4 test accounts. This is the first real functional test of AIR-0223's UI against non-empty data.

## 7. What requires explicit sign-off before execution

1. **Creating 4 real `auth.users` rows via the Admin API** (`REFERRAL_TEST_FIXTURE.sql` §A) — touches the shared auth system. Low risk (clearly `.test`-tagged, fully reversible via cascade delete) but still a real write to a shared system, not just test-table data.
2. **Scenario 3's temporary `global_settings.referral_default_sponsor_uuid` write** — affects every real organic signup for however long it's set. Must be set and cleared in the same short window, verified cleared afterward.
3. Everything else (job/commission simulation, withdrawal/audit dual-write replication, validation queries) touches only `referral_commissions`/`referral_withdrawals`/`referral_audit_logs`, which have zero real rows today and are fully additive/reversible.

## 8. Bake readiness — final checklist before `referral_mode → NORMAL`

Restated and consolidated from `AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`, now with AIR-0224's E2E results as the evidence base once run:

- [ ] Settlement Engine Specification exists, finalized (defines Net Settlement Amount **and** the rounding rule for the `bigint` commission columns — §3's finding feeds directly into this).
- [ ] Job-Completed trigger implemented, idempotent, exactly-once (informed by Scenario 5's detection query — that query's logic is the exact check the real trigger needs to run before inserting).
- [ ] `referral_level1_percent`/`referral_level2_percent` = 5/2 confirmed set in `global_settings`.
- [ ] `referral_default_sponsor_uuid` set to a real (non-test) account.
- [ ] AIR-0223 Dashboard verified against real fixture data (§6) with no UI/API issues open.
- [ ] E2E Scenarios 1–5 all PASS (this ticket's own completion criteria).
- [ ] Recharge-based trigger (`auth-web/app/api/admin/users/recharge/route.ts:104`) removed, per AIR-0221D.
- [ ] `referral_mode` remains `OFF` until every item above is checked **and** CTO gives separate, explicit activation approval — this ticket does not grant that approval.
