# AIR-0221 Stage 1: Referral Finalization — Additive Schema Foundation

## Goal
Additive-only schema foundation to promote the live Gen-1 `referral_commissions` engine toward the CTO-approved final model (`CONSOLIDATION_PLAN.md` §10): auto-paid commissions (no pending/approval state), admin approval only at withdrawal time, Commission Trace, audit trail. No existing data touched, no API/UI cutover, no Gen 2/3 changes.

## Actions taken

### 1. `referral_commissions` additive columns
Added `updated_at` (trigger-maintained), `commission_level` (nullable `SMALLINT`, `CHECK IN (1,2)` added `NOT VALID` + validated separately for safety), `source_job_id` (`TEXT`). `commission_type`/`base_tokens`/`rate_percent`/`commission_tokens`/`status`/`metadata`/`created_at`/`paid_at` all untouched. Documented the intended Commission Trace `metadata` JSON convention via `COMMENT ON COLUMN` (not enforced — documentation only).

### 2. `referral_withdrawals` new table
`REQUESTED → APPROVED → SENDING → COMPLETED / REJECTED`, plus `wallet_address`, `amount`, `tx_hash`, `admin_id`, `reason`, `metadata`, full timestamp set (added `sent_at` beyond the literal ticket field list — flagged, easy to drop). Created empty, RLS enabled with user-facing policies only (see finding below on why no admin RLS policy was added). Not wired to any API yet.

### 3. Audit foundation
Checked whether `admin_audit_logs` (Gen 3, `air_0201a_admin_treasury.sql`) could be reused — **confirmed it does not exist in production** (absent from live schema introspection). Created `referral_audit_logs` as a new additive table instead: `entity_type` (commission|withdrawal), `entity_id`, `action` (generated|requested|approved|rejected|completed|reversed), `actor_id`, `reason`, `metadata`, `created_at`. RLS enabled with no policies (service-role only — this is a system/audit table, no legitimate end-user access pattern). Not written to by any application code yet.

### 4. $20 Instant Reward — removal plan (not deleted, per instruction)
**Identified, not touched:**
- `referral_rewards_log` table — confirmed 0 rows in production (no historical data to preserve/archive).
- `auth-web/app/api/admin/publishing/route.ts:206-252` — the trigger logic ("2nd approved publish → flat $20 via `increment_usdt_balance`"), including the actual reward-crediting call at line 239.
- **Already-known bonus finding (from AIR-0221A)**: this code path is currently silently broken anyway — `increment_usdt_balance` references a nonexistent `profiles.updated_at` column (`42703`, confirmed live), so the $20 has not actually been crediting any balance, while `referral_rewards_log` still gets an insert as if it had (that insert isn't gated on the RPC call's success). Consistent with 0 rows in `referral_rewards_log` — if it were working, and any 2nd-publish events had occurred, there would be rows.

**Removal plan for a future stage:**
1. Remove the trigger call block (lines ~206-252 of `publishing/route.ts`) in a dedicated small PR — this is a pure code deletion, no schema change required.
2. Because `referral_rewards_log` has 0 rows today, there is nothing to archive/export before dropping the table — `DROP TABLE referral_rewards_log` can happen in the same cleanup pass as the code removal, not deferred to a 30-day bake like the Gen 2/3 tables (those are deferred because they're a bigger, more speculative rollback surface; this one is a single dead trigger with zero data).
3. Sequencing: do this once Stage 1/2 schema work has landed and stabilized, so it doesn't get bundled with (and risk being confused for) the referral-commission model change itself. Recommend as its own ticket (e.g. AIR-0221B) rather than folding into Stage 2/3.

### 5. Gen 2/3 — shelved, documented only (not touched)
No SQL in this migration references any of the following. Restating the shelved list from `CONSOLIDATION_PLAN.md` §0/§10.2 here for Stage-1 deliverable completeness:

- **Gen 2** (`air_0157c`–`air_0166a`): tables `commissions`, `withdrawal_requests`, `worker_jobs`; RPCs `get_available_withdrawal_balance`, `request_withdrawal` (×3 versions), `get_referral_dashboard_kpi` (×4 versions), `get_referral_tree`, `get_commission_timeline`, `complete_worker_job_and_mint_commission`, `admin_approve/reject_commission`, `admin_approve/reject/complete_withdrawal`, `admin_bulk_approve_*`.
- **Gen 3** (`air_0201`–`air_0208`): tables `risk_flags`, `user_activity`, `admin_audit_logs` (confirmed nonexistent live, see §3 above), `user_events`; RPCs/triggers `check_withdrawal_abuse`, `check_job_abuse`, `admin_scan_referral_trees`, `handle_new_risk_flag`, `admin_override_user_risk`, `trigger_reengagement_notifications`, `handle_referral_join`, `handle_commission_earned`, `handle_user_activity`, `trigger_habit_reminders`, `handle_backend_analytics`, `get_analytics_dashboard` (×2 versions).

Per `CONSOLIDATION_PLAN.md` §10.2, these are ultimately scheduled for actual `DROP`, not indefinite shelving — but that happens in the Stage-4-equivalent cleanup pass, not Stage 1.

## Pre-flight / verification

- **Data-conflict check**: `referral_commissions`, `withdrawals`, `commissions` (Gen 2), `tenant_commission_logs`, `referral_rewards_log` all confirmed **0 rows** in production via read-only PostgREST queries before writing the migration. No possible CHECK-constraint conflict or data-loss scenario exists today; migration is still written defensively (NOT VALID + VALIDATE CONSTRAINT pattern) for whenever that stops being true.
- **Syntax validation**: both the forward and rollback SQL files parsed cleanly with `pglast` (Python bindings over Postgres's real grammar via `libpg_query`) — 33 and 12 statements respectively, zero syntax errors. No live Postgres client was available in this environment to run an actual `BEGIN/ROLLBACK` dry-run; recommend wrapping the real apply in an explicit transaction as an extra safety margin.
- **Live-schema cross-check**: every existing column/table this migration references (`profiles.id`, `referral_commissions`'s current columns, `gen_random_uuid()`) was verified against the actual live schema (PostgREST introspection), not just against `auth-web/supabase_schema.sql`, which this project has already shown drifts from what's really deployed.
- **New finding**: `profiles.is_superadmin` does not exist in production, even though the orphaned Gen-2 `withdrawal_requests` RLS policies and `migration_withdrawal_commission.sql` both reference it — meaning that migration file was very likely never actually applied either. Real admin auth is a hardcoded email check in `_auth.ts`. This shaped the RLS design for `referral_withdrawals` (see Impact Note) — no admin RLS policy was added, since one referencing that column would fail to apply, and it would be redundant with the real (service-role + app-layer) access path anyway.

Full column/table diff, rollback mechanics, and the Stage 2 dual-write plan are in `migrations/air_0221_referral_stage1_foundation_IMPACT.md`.

## Status
- **Applied to production 2026-07-09**, via `migrations/air_0221_referral_stage1_foundation_APPLY.sql` (a single-paste wrapper around the reviewed migration, with the checklist's §4 checks embedded as self-verifying `RAISE EXCEPTION` assertions) run through the Supabase Dashboard SQL Editor (project `picadiri`, branch `main`/production).
- Apply reported "Success. No rows returned" (no error raised — under this script's design, any failed assertion would have aborted the transaction and produced a visible error instead, so a clean success confirms every §4 check passed).
- **Independently re-verified read-only against production afterward** (not just trusting the SQL Editor screenshot): `referral_commissions?select=updated_at,commission_level,source_job_id` now returns `HTTP 200 []` (previously `400 42703 column does not exist`) — confirms the new columns exist. `referral_commissions` row count still 0 (no existing data touched). `referral_withdrawals` and `referral_audit_logs` both exist and are empty (0 rows each).
- No application code, API, or web admin UI changed in this stage (per instruction).
- No Gen 2/3 object touched.
- Next: Stage 2 (dual-write) planning per the Impact Note's final section, on CTO go-ahead.
