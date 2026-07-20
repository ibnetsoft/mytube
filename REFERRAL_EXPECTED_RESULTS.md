# AIR-0224 — Expected Results (computed, auditable)

Rate basis: `referral_level1_percent = 5`, `referral_level2_percent = 2` (CTO-finalized, `AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`).
Rounding rule: Postgres `ROUND(numeric)`, round-half-away-from-zero, cast to `bigint` (matches the column type — see `REFERRAL_E2E_TEST_PLAN.md` §3's finding that `commission_tokens`/`base_tokens` are `bigint`, not decimal).

Chain: `Default Sponsor (DS) ← User A ← User B ← User C` (each `←` = `referred_by`).

## Per-job expected commission rows

| Job ID | Amount | Completed by | L1 beneficiary | L1 = ROUND(amount × 0.05) | L2 beneficiary | L2 = ROUND(amount × 0.02) |
|---|---:|---|---|---:|---|---:|
| `E2E-JOB-001` | 10 | User A | Default Sponsor | ROUND(0.5) = **1** | *(none — DS has no sponsor)* | — |
| `E2E-JOB-002` | 50 | User B | User A | ROUND(2.5) = **3** | Default Sponsor | ROUND(1.0) = **1** |
| `E2E-JOB-003` | 100 | User C | User B | ROUND(5.0) = **5** | User A | ROUND(2.0) = **2** |
| `E2E-JOB-004` | 500 | User C | User B | ROUND(25.0) = **25** | User A | ROUND(10.0) = **10** |
| `E2E-JOB-005` | 1000 | User C | User B | ROUND(50.0) = **50** | User A | ROUND(20.0) = **20** |

**9 total `referral_commissions` rows** (Job 1 produces only 1 row — no L2 possible for the root account; Jobs 2–5 each produce 2).

## Per-account expected totals (`status='paid'`, `commission_type != 'WITHDRAWAL'`)

| Account | Source rows | Total commission |
|---|---|---:|
| Default Sponsor | Job1 L1 (1) + Job2 L2 (1) | **2** |
| User A | Job2 L1 (3) + Job3 L2 (2) + Job4 L2 (10) + Job5 L2 (20) | **35** |
| User B | Job3 L1 (5) + Job4 L1 (25) + Job5 L1 (50) | **80** |
| User C | *(none — no one referred by C in this fixture)* | **0** |

**Grand total across all 9 rows**: 1 + 3 + 1 + 5 + 2 + 25 + 10 + 50 + 20 = **117**

## Scenario 1 — withdrawal expected state

1. User B has 80 available (per above, `referral_withdrawals`/legacy withdrawal-row math: `paid earned − completed/in-flight withdrawals`, 0 prior withdrawals).
2. User B requests withdrawal of **30** → legacy `referral_commissions` row: `commission_type='WITHDRAWAL'`, `commission_tokens=-30`, `status='PENDING'`. Mirrored `referral_withdrawals` row: `status='REQUESTED'`, `amount=30`, `metadata.legacy_commission_id` = the legacy row's id.
3. Admin approves → legacy row `status='COMPLETED'`. Mirrored row: `status` transitions `APPROVED → SENDING → COMPLETED` (3 timestamps set). 3 `referral_audit_logs` rows: `approved`, `sending`, `completed`, all `entity_type='withdrawal'`, `entity_id` = the mirrored row's id.
4. User B's available balance after: 80 − 30 = **50**.

## Scenario 2 — Level 2, isolated check

`E2E-JOB-003` alone: one row with `commission_level=1`, `beneficiary_id=User B`, `commission_tokens=5`; one row with `commission_level=2`, `beneficiary_id=User A`, `commission_tokens=2`. Both share `source_job_id='E2E-JOB-003'`, `source_user_id=User C`, `base_tokens=100`.

## Scenario 3 — Default Sponsor, expected state

Before: test signup account (`E2E-User-D`, no referral code) has `referred_by = NULL`.
During (temporary `referral_default_sponsor_uuid` = DS's id): new signup → `referred_by = DS's id`.
After (`referral_default_sponsor_uuid` cleared): confirm the setting is empty again; the already-created test signup keeps `referred_by = DS` (attribution is permanent at signup time, clearing the setting afterward doesn't retroactively change it — expected and correct).

## Scenario 4 — invalid referral code, expected state

Querying `profiles` for `referral_code = 'E2E-NONEXISTENT-CODE'` → **0 rows**. This is what `validate_referral_code()` checks; zero rows means it returns `false`, which means `app/routers/auth.py`'s signup handler returns `{"success": false, "error": "유효하지 않은 추천코드입니다."}` **without creating any auth user or profile row**. No account should exist afterward with that code attempted.

## Scenario 5 — idempotency detection, expected state

A deliberate duplicate insert (same `source_job_id='E2E-JOB-003'`, same `beneficiary_id`, same `commission_level`) must be caught by:
```sql
SELECT source_job_id, beneficiary_id, commission_level, count(*)
FROM public.referral_commissions
WHERE commission_type != 'WITHDRAWAL'
GROUP BY source_job_id, beneficiary_id, commission_level
HAVING count(*) > 1;
```
Expected: **0 rows** in the clean baseline fixture; **1 row returned with count=2** during the deliberate duplicate-insert step (immediately reverted afterward — see `REFERRAL_TEST_FIXTURE.sql`'s Scenario 5 block).
