# Schema Impact Note — AIR-0221 Stage 1

Migration: `air_0221_referral_stage1_foundation.sql`
Rollback: `air_0221_referral_stage1_foundation_rollback.sql`

## Pre-flight check (read-only, against production, before writing the migration)

Row counts confirmed via PostgREST (`Prefer: count=exact`), 2026-07-09:

| Table | Row count |
|---|---|
| `referral_commissions` | **0** |
| `withdrawals` | 0 |
| `commissions` (Gen 2) | 0 |
| `tenant_commission_logs` | 0 |
| `referral_rewards_log` | 0 |

**The entire referral/commission/withdrawal money path currently has zero rows in production.** This is a pre-launch database — there is no real financial data anywhere in this schema yet. This does not change how the migration was written (still additive-only, still validates before constraining, per the standing "no data loss" mandate for whenever real data does exist), but it does mean the risk of this specific Stage-1 migration is at its practical floor: there is nothing it could lose even in the worst case.

Also discovered during pre-flight (relevant to RLS design, see below): `profiles.is_superadmin` **does not exist** in production, despite being referenced by the orphaned `withdrawal_requests` RLS policies (`air_0158d_withdrawal_ledger.sql`) and by `migration_withdrawal_commission.sql`'s own step 4. Live admin authorization actually runs through a hardcoded email check in `auth-web/app/api/admin/_auth.ts` (`SUPER_ADMIN_EMAIL`), enforced at the application layer — all admin API routes use the service-role key, which bypasses RLS entirely. This means `migration_withdrawal_commission.sql` was very likely never actually applied to production either (its step 3 would have created the column), consistent with the broader pattern already documented in `CONSOLIDATION_PLAN.md` of SQL files in this repo that were written but never deployed. Flagging as a finding, not fixing it here — out of scope for Stage 1.

## Files changed

| File | Type |
|---|---|
| `migrations/air_0221_referral_stage1_foundation.sql` | new — forward migration |
| `migrations/air_0221_referral_stage1_foundation_rollback.sql` | new — rollback |
| `migrations/air_0221_referral_stage1_foundation_IMPACT.md` | new — this note |
| `worknote/AIR-0221-Stage1.md` | new — worknote |
| `CONSOLIDATION_PLAN.md` | updated — §5/§10 progress note |

No application code (`auth-web/app/**`, `app/routers/**`, `services/**`) is touched by this migration. No web admin UI is touched. No Gen 2/3 object is touched.

## Columns/tables added

### `referral_commissions` (existing table, ALTER only)
| Column | Type | Nullable | Notes |
|---|---|---|---|
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | new, trigger-maintained |
| `commission_level` | `SMALLINT` | nullable | new; `CHECK (commission_level IS NULL OR commission_level IN (1,2))`, added `NOT VALID` then `VALIDATE CONSTRAINT`d so it can never lock/fail against unexpected existing data even in a future non-empty environment |
| `source_job_id` | `TEXT` | nullable | new |

Untouched: `id, beneficiary_id, source_user_id, commission_type, base_tokens, rate_percent, commission_tokens, status, metadata, created_at, paid_at`. `commission_type` (free-text) and `commission_level` (typed) coexist — no data migrated between them in this stage; that's Stage 2 backfill.

### `referral_withdrawals` (new table)
`id, user_id, amount, wallet_address, status (REQUESTED|APPROVED|SENDING|COMPLETED|REJECTED), requested_at, approved_at, sent_at, completed_at, rejected_at, tx_hash, admin_id, reason, metadata, created_at, updated_at`.

`sent_at` is the one field added beyond the ticket's literal list — every other status in the state machine (`REQUESTED`→`requested_at`, `APPROVED`→`approved_at`, `COMPLETED`→`completed_at`, `REJECTED`→`rejected_at`) has a matching timestamp; `SENDING` had none. Purely additive, zero risk, easy to drop via the rollback script if the CTO would rather it not exist yet.

RLS: enabled, with only user-facing policies (`auth.uid() = user_id` for select/insert). No admin policy, because a `profiles.is_superadmin`-based one (the only precedent in this repo) would fail to apply — see pre-flight finding above. Admin access goes through the service-role key exactly like every other admin route already does.

### `referral_audit_logs` (new table)
`id, entity_type (commission|withdrawal), entity_id, action (generated|requested|approved|rejected|completed|reversed), actor_id, reason, metadata, created_at`.

`admin_audit_logs` (Gen 3) was checked and does not exist live, so it isn't reused — see `CONSOLIDATION_PLAN.md` §10.2. RLS enabled with **no** policies at all (service-role only), since this is a system/admin-only audit trail with no legitimate direct end-user access pattern.

## Rollback

Run `air_0221_referral_stage1_foundation_rollback.sql`. It drops, in dependency order: `referral_audit_logs` table → `referral_withdrawals` table + its trigger/function → the three new `referral_commissions` columns + their index/constraint/trigger/function. `referral_commissions` itself, and every column that existed before this migration, is never touched.

Safe as long as Stage 2/3 hasn't started writing real data into the new objects yet (true today — nothing in this repo writes to them). The rollback file's header includes three pre-flight `SELECT count(*)` queries to run first if there's any doubt.

## Existing-data impact

None. Zero rows existed anywhere in the affected tables before this migration (see pre-flight table above), and this migration doesn't `UPDATE`, `DELETE`, or backfill anything — it only adds nullable/defaulted columns and new empty tables.

## Dry-run / pre-check performed

1. Row-count pre-flight against production for every table this migration touches or is designed around (table above).
2. Full SQL syntax validation of both the forward and rollback files using `pglast` (Python bindings over the real PostgreSQL grammar, `libpg_query`) — both parsed cleanly (33 and 12 statements respectively). This is a genuine parse against Postgres's own grammar, not a heuristic linter.
3. Cross-checked every referenced existing column/table (`profiles.id`, `referral_commissions`'s existing columns, `gen_random_uuid()` availability) against the live schema via PostgREST introspection, not just against `auth-web/supabase_schema.sql` (which has already been shown in this project to drift from what's actually deployed).

**Not performed**: an actual `BEGIN; ... ROLLBACK;` dry-run inside a real Postgres session, since this environment has no `psql`/Postgres client and no staging database — only production, which this migration has not yet been applied to. Recommend running the migration inside an explicit transaction the first time it's actually applied (`BEGIN;` ... verify ... `COMMIT;`), even though every statement here is individually idempotent.

## What Stage 2 needs to do next (dual-write plan)

Per `CONSOLIDATION_PLAN.md` §5 Stage 2, now unblocked by this foundation:

1. **Backfill `commission_level`** on any future `referral_commissions` rows generated by the settlement worker (`auth-web/lib/settlement.ts`) — update it to write both `commission_type` (unchanged, for backward compat with any reader still on it) and `commission_level` (1 or 2) going forward. No historical backfill needed today (0 rows).
2. **Backfill `source_job_id`** the same way — the settlement worker already knows the source recharge/job reference; start populating it going forward.
3. **Start writing `referral_audit_logs`** rows from the withdrawal admin routes (`auth-web/app/api/admin/withdrawals/route.ts`, and once it exists, the new referral-withdrawal admin endpoints) on approve/reject/complete, and from the settlement worker on commission generation.
4. **Dual-write `referral_withdrawals`**: when a user requests a referral-earnings withdrawal, write to both the legacy pattern (still live) and the new table for a full bake period, per the standing Stage 2 policy in §5 — this is where the AIR-0221A-hotfixed `settlements/payout` and `withdrawals` routes eventually get a second write target, not a replacement, until Stage 3 cutover.
5. Still **not in scope for Stage 2 either**: touching Gen 2/3, or the $20 instant-reward code path (that removal plan is documented separately, see `worknote/AIR-0221-Stage1.md` §4).
