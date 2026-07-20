# Stage 1 Migration — Final Production-Apply Checklist

Migration: `air_0221_referral_stage1_foundation.sql`
Rollback: `air_0221_referral_stage1_foundation_rollback.sql`
Impact note: `air_0221_referral_stage1_foundation_IMPACT.md`

**Direction approved by CTO (2026-07-09). Production apply is on hold — this document is the checklist to run through when apply is actually authorized, not an instruction to apply now.**

CTO approvals on record for this stage:
- `referral_withdrawals.sent_at` — keep.
- `referral_audit_logs` — new table, approved.
- `admin_audit_logs` — confirmed not reused (doesn't exist in production).
- `profiles.is_superadmin` — confirmed not depended on anywhere in this migration.
- Admin authorization — stays on the current `auth-web/app/api/admin/_auth.ts` hardcoded-email model; nothing in this migration introduces a DB-level admin flag.

---

## 1. Production apply order

1. Confirm preconditions are still true immediately before applying (not just at authoring time):
   - AIR-0221A hotfix (`auth-web/app/api/admin/withdrawals/route.ts`, `auth-web/app/api/admin/settlements/payout/route.ts`) is deployed and live — Stage 1 doesn't depend on it functionally, but both are part of the same money-path effort and should not be mid-flight simultaneously.
   - No other migration or manual schema change is queued/in-progress against `referral_commissions` or `profiles` at the same time (lock contention / ordering risk).
2. Re-run the pre-flight row-count check (§7 below) — do not trust the "0 rows" finding from Stage-1 authoring without re-checking on the day of apply, since time has passed.
3. Take a backup/snapshot per §3 below.
4. Open a SQL session against production (Supabase SQL Editor or `psql`), paste `air_0221_referral_stage1_foundation.sql` **in full, unmodified**, wrapped per §2 below.
5. Run the post-apply verification queries in §4. All must pass before treating the migration as done.
6. `COMMIT` only after §4 passes. If any check fails, `ROLLBACK` the transaction immediately (this discards the whole migration cleanly — no need to run the separate rollback script if you haven't committed yet).
7. Only after commit + verification: update `CONSOLIDATION_PLAN.md` and `worknote/AIR-0221-Stage1.md` to record the apply date, then move to Stage 2 planning.

The migration's own internal order (already fixed in the file, do not reorder): §1 `referral_commissions` ALTERs + constraint + trigger → §2 `referral_withdrawals` CREATE + RLS → §3 `referral_audit_logs` CREATE + RLS. This order matters only in that §1 touches an existing live table first (higher blast radius) — if something is going to fail, it's most likely to fail there, before the two brand-new empty-table creates in §2/§3 even run.

---

## 2. Transaction application method

```sql
BEGIN;

-- paste the full contents of air_0221_referral_stage1_foundation.sql here

-- then run the §4 verification queries inside the SAME session
-- (still uncommitted) before deciding to COMMIT

COMMIT;   -- only if every §4 check passed
-- or:
ROLLBACK; -- if anything looks wrong
```

Notes:
- Postgres DDL is transactional, so wrapping the whole file in `BEGIN`/`COMMIT` is safe and is the intended way to apply it — every statement in the file (including `ALTER TABLE ... VALIDATE CONSTRAINT`) can run inside a transaction block.
- Do **not** use `CREATE INDEX CONCURRENTLY` here (the file doesn't use it) — `CONCURRENTLY` cannot run inside a transaction block at all, and isn't needed anyway since every index in this migration is either on a brand-new empty table or (for the two `referral_commissions` indexes) on columns that are 0-populated today. **If application is delayed long enough that `referral_commissions` has accumulated meaningful row volume by the time this actually runs**, reconsider: run the two `referral_commissions` index creations (`idx_referral_commissions_commission_level`, `idx_referral_commissions_source_job_id`) separately, outside the transaction, using `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, to avoid holding a write lock on a busy live table. Everything else in the file can stay as one transaction regardless.
- Supabase SQL Editor executes the full pasted block as one submission; confirm in the UI that it reports a single successful transaction rather than statement-by-statement (if it doesn't, wrap explicitly as shown above rather than relying on default behavior).

---

## 3. Backup / snapshot check before applying

1. Confirm what backup coverage the Supabase project (`giorysjpgxzdypbmxwmx`) actually has — plan tier determines whether Point-in-Time Recovery is available. This wasn't checked as part of Stage 1 authoring and should be confirmed by whoever has dashboard/billing access before apply.
2. Regardless of PITR availability, trigger (or confirm the existence of) a manual backup/snapshot immediately before applying, specifically covering `public.referral_commissions` (the one existing table this migration alters) and `public.profiles` (referenced by new FKs).
3. Given the pre-flight check found 0 rows in every affected table as of Stage-1 authoring, a backup today would capture almost nothing — but re-run the row-count check (§7) as part of this same pre-apply pass, and if it now shows non-zero rows, treat a real data backup as **mandatory**, not optional, before proceeding.
4. Record the backup/snapshot reference (timestamp, PITR restore point, or dump file location) in `worknote/AIR-0221-Stage1.md` when apply actually happens, so the rollback path in §5/§6 has something concrete to restore to if the SQL rollback alone isn't sufficient.

---

## 4. Post-apply verification SQL

Run all of these in the same session, before `COMMIT`:

```sql
-- 4a. New referral_commissions columns exist with correct types/defaults
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'referral_commissions'
  AND column_name IN ('updated_at', 'commission_level', 'source_job_id')
ORDER BY column_name;
-- Expect: 3 rows. updated_at NOT NULL default now(); commission_level nullable,
-- no default; source_job_id nullable, no default.

-- 4b. CHECK constraint exists and is VALIDATED (not left NOT VALID)
SELECT conname, convalidated
FROM pg_constraint
WHERE conrelid = 'public.referral_commissions'::regclass
  AND conname = 'referral_commissions_commission_level_check';
-- Expect: convalidated = true. If false, VALIDATE CONSTRAINT didn't complete —
-- do not COMMIT.

-- 4c. Trigger on referral_commissions exists
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgrelid = 'public.referral_commissions'::regclass
  AND tgname = 'trg_referral_commissions_updated_at';
-- Expect: 1 row, tgenabled = 'O' (enabled).

-- 4d. No existing referral_commissions data was touched
SELECT count(*) FROM public.referral_commissions;
-- Expect: same count as the pre-apply check in §7. Any change here means
-- something unexpected happened — investigate before COMMIT.

-- 4e. New tables exist with RLS enabled
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN ('referral_withdrawals', 'referral_audit_logs')
  AND relnamespace = 'public'::regnamespace;
-- Expect: 2 rows, both relrowsecurity = true.

-- 4f. Policy count matches design (2 on referral_withdrawals, 0 on referral_audit_logs)
SELECT tablename, policyname, cmd
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('referral_withdrawals', 'referral_audit_logs')
ORDER BY tablename, policyname;
-- Expect: exactly 2 rows for referral_withdrawals ("Users can view own referral
-- withdrawals", "Users can insert own referral withdrawals"), 0 rows for
-- referral_audit_logs.

-- 4g. Triggers on referral_withdrawals exist
SELECT tgname FROM pg_trigger
WHERE tgrelid = 'public.referral_withdrawals'::regclass
  AND tgname = 'trg_referral_withdrawals_updated_at';
-- Expect: 1 row.

-- 4h. Indexes exist
SELECT indexname FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_referral_commissions_commission_level',
    'idx_referral_commissions_source_job_id',
    'idx_referral_withdrawals_user_id',
    'idx_referral_withdrawals_status',
    'idx_referral_withdrawals_created_at',
    'idx_referral_audit_logs_entity',
    'idx_referral_audit_logs_created_at'
  );
-- Expect: all 7 present.

-- 4i. New tables are genuinely empty (nothing pre-populated them unexpectedly)
SELECT
  (SELECT count(*) FROM public.referral_withdrawals) AS withdrawals_rows,
  (SELECT count(*) FROM public.referral_audit_logs) AS audit_rows;
-- Expect: 0, 0.
```

If any query's actual result doesn't match its "Expect" line: **do not `COMMIT`**. `ROLLBACK` and investigate.

---

## 5. Rollback execution conditions

Run the rollback (`air_0221_referral_stage1_foundation_rollback.sql`) if:
- Any §4 verification query fails **and** the transaction was already committed (if not yet committed, a plain `ROLLBACK` of the open transaction is sufficient and the separate rollback script is unnecessary).
- A structural problem is discovered shortly after apply (e.g., an app team member reports the new objects conflict with something not caught here) and the decision is to fully back out rather than patch forward.
- The CTO changes the Stage 1 design (e.g., decides `sent_at` should in fact be dropped, or `referral_audit_logs`'s shape should change) before Stage 2 starts — cleaner to roll back and re-author than to hand-patch a partially-applied foundation.

Do **NOT** run the rollback if:
- Stage 2 work has started and any real row exists in `referral_withdrawals`, `referral_audit_logs`, or in the new `referral_commissions` columns (`commission_level`/`source_job_id` populated). The rollback script `DROP`s these outright — it does not archive anything. Run the three pre-flight `SELECT count(*)` queries printed at the bottom of the rollback file first, every time, before executing it, regardless of how much time has passed since apply.
- Only a single verification check is borderline/ambiguous and the underlying object is otherwise clearly fine (e.g., a policy naming query returns rows in a different order than expected) — investigate first rather than rolling back reflexively.

---

## 6. Rollback SQL execution order

The rollback file already encodes the correct order (reverse of the forward migration, dependency-safe); do not reorder or run its statements individually out of sequence:

1. `DROP TABLE IF EXISTS public.referral_audit_logs;` (no dependents — drop first)
2. `referral_withdrawals`: drop trigger → drop trigger function → `DROP TABLE`.
3. `referral_commissions`: drop trigger → drop trigger function → drop the two new indexes → drop the CHECK constraint → drop `source_job_id` → drop `commission_level` → drop `updated_at`. (Column drops last, and in this specific order, so that the constraint referencing `commission_level` is gone before the column itself is dropped — dropping the column first would auto-drop the constraint anyway via `CASCADE` semantics, but the explicit order avoids relying on that.)

Run the whole rollback file as one transaction (`BEGIN; ... COMMIT;`), same pattern as §2, so a failure partway through doesn't leave the schema half-reverted.

---

## 7. `referral_commissions` — CHECK constraint impact if rows already exist by apply time

**Risk is effectively zero, by construction, regardless of row count at apply time.** Reasoning:

- `commission_level` is a **brand-new column** added with no explicit default, so every pre-existing row automatically receives `NULL` for it the instant the `ADD COLUMN` runs — there is no way for a pre-existing row to already hold an out-of-range value, because the column didn't exist for that row to have a value in.
- The CHECK constraint is `commission_level IS NULL OR commission_level IN (1, 2)`, which explicitly permits `NULL`. So `VALIDATE CONSTRAINT` scanning every existing row will always pass, no matter how many rows exist, because they can only be `NULL` at this point.
- The same logic applies to `updated_at` (has a `DEFAULT now()`, so no row can violate `NOT NULL`) and `source_job_id` (nullable, no constraint on it at all).

**What re-checking §4a/§4b at apply time is actually for**, then, isn't "did the constraint fail" (it structurally cannot, for this specific migration) — it's:
- Confirming the migration ran to completion at all (i.e., nothing failed earlier in the transaction for an unrelated reason, like a lock timeout).
- Sizing/performance awareness: if `referral_commissions` has grown to a large row count by the time this actually applies (e.g., real settlement activity has started), the `VALIDATE CONSTRAINT` statement still has to physically scan every row — it won't fail, but it takes a `SHARE UPDATE EXCLUSIVE` lock and does real I/O proportional to table size. For the expected scale of a referral-commission table this is very unlikely to be noticeable, but if the apply is delayed by months and volume has grown substantially, budget a few extra seconds/minutes for this step rather than assuming it's instant.

**None of this changes the migration itself** — it's already written the safe way (`NOT VALID` then separate `VALIDATE CONSTRAINT`) specifically so this reasoning holds regardless of when it's actually applied.

---

## 8. RLS policy presence/absence and reasoning

| Table | RLS enabled | Policies | Reasoning |
|---|---|---|---|
| `referral_withdrawals` | Yes | 2: user can `SELECT` own rows (`auth.uid() = user_id`), user can `INSERT` own rows with `status = 'REQUESTED'` | End users will eventually read/create their own withdrawal requests directly (once Stage 2/3 wires up the API) — real end-user access pattern, so real user-scoped RLS is appropriate. **No admin policy.** The only precedent in this repo for an admin RLS policy (`air_0158d_withdrawal_ledger.sql`, orphaned Gen 2) gates on `profiles.is_superadmin`, which was confirmed **not to exist** in production during Stage 1 audit — a policy referencing it would fail to even `CREATE`. Live admin authorization is a hardcoded email check in `auth-web/app/api/admin/_auth.ts` (`SUPER_ADMIN_EMAIL`), enforced at the application layer; every existing admin API route uses the Supabase **service-role key**, which bypasses RLS entirely regardless of what policies exist. So admin access to this table works correctly with zero admin-specific RLS policies, consistent with CTO's "관리자 권한은 현행 `_auth.ts` 방식 기준으로 유지" instruction — adding a DB-level admin flag/policy would be introducing a second, redundant admin-authorization mechanism, not "maintaining the current approach."
| `referral_audit_logs` | Yes | 0 | This is a system/audit-only table — there is no legitimate scenario where an end user reads or writes their own audit trail directly (that's exactly the kind of tamper surface an audit log shouldn't have). RLS enabled with zero policies means: only the service role (which bypasses RLS) can touch it at all, and no `anon`/`authenticated` JWT-bearing client can read or write it under any circumstance, even accidentally. This is intentionally stricter than `referral_withdrawals`.

Both tables having RLS **enabled** (even where `referral_audit_logs` has no policies) matters because Postgres RLS defaults to **deny-all** for enabled tables with no matching policy — so `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` with zero policies is the correct way to express "service-role only," not an oversight.

---

## 9. Code changes needed in Stage 2 (list only — not implemented here)

None of the following exist yet; Stage 1 deliberately leaves all application code untouched.

1. **`auth-web/lib/settlement.ts`** (settlement worker, generates `referral_commissions` rows on recharge) — start writing `commission_level` (1 or 2, alongside the existing `commission_type`) and `source_job_id` on every new row it generates. `commission_type` keeps being written too, unchanged, for backward compatibility until cutover.
2. **`auth-web/app/api/admin/withdrawals/route.ts`** (AIR-0221A-hotfixed) — on `completed`/`rejected` PATCH, also insert a `referral_audit_logs` row (`entity_type='withdrawal'`, `action='completed'|'rejected'`, `actor_id` = the admin, `reason`).
3. **`auth-web/app/api/admin/settlements/payout/route.ts`** (AIR-0221A-hotfixed) — on successful payout, insert a `referral_audit_logs` row (`entity_type='commission'`, `action='completed'`... note: per the CTO's final flow (§10.1 of `CONSOLIDATION_PLAN.md`), commissions are meant to be auto-paid with no admin approval step going forward, so whether this route continues to exist in its current form, or is retired in favor of pure auto-generation, is itself a Stage 2/3 design question — not just a "add an audit insert" change.
4. **New referral-withdrawal admin endpoints** (do not exist yet — no admin UI or API currently reads/writes `referral_withdrawals` at all) — approve/reject/mark-sending/complete actions, each writing both the `referral_withdrawals` status transition and a corresponding `referral_audit_logs` row.
5. **User-facing referral-withdrawal request path** — currently `app/routers/referral.py:338` (`POST /user/referrals/withdraw`) writes a negative `referral_commissions` row. Stage 2 dual-writes: keep that write (unchanged, still the system of record until cutover) **and** additionally insert a matching `referral_withdrawals` row (`status='REQUESTED'`), per the standing Stage 2 dual-write policy in `CONSOLIDATION_PLAN.md` §5.
6. **Settlement-generated commission events** — decide whether commission *generation* (not just withdrawal actions) should also produce a `referral_audit_logs` row (`action='generated'`) for full traceability, or whether that's redundant with `referral_commissions` itself already being the record. Worth a explicit decision before Stage 2 implementation, not assumed either way here.

None of items 1–6 are implemented in this checklist document or in Stage 1 — restating them here only to make the Stage 2 scope concrete for planning purposes, per the ticket's request.
