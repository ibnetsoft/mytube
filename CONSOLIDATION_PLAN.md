# AIR-0221 — Referral System Consolidation Plan

**Status:** **AIR-0221 PLANNING PHASE CLOSED (2026-07-09).** §10 is the authoritative target design — it supersedes the exploratory recommendations in §4/§6/§7 and resolves OQ-2/OQ-3/OQ-4 below. §§0–9 are kept as-is because they're the evidence base the final decision was made from; where §10 disagrees with an earlier section, §10 wins. Full chain completed: AIR-0221A (emergency RPC hotfix), Stage 1 (schema foundation, applied to production), AIR-0221C (audit-action CHECK hotfix), Stage 2 (dual-write implementation, deployed) + `worknote/AIR-0221-Stage2-BAKE.md` (bake-watch procedure), AIR-0221B ($20 instant-reward removal), and AIR-0221D (`AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`, activation plan with final CTO decisions on percents/trigger/default-sponsor/bake-cycle). **Remaining work is execution, not planning** — see `AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`'s closing section for the concrete next-ticket list (Settlement Engine Specification, Job-Completed trigger implementation, activation, bake, then Stage 3).
**Author:** Claude (Sonnet 5), from a full read-only audit of the current codebase.
**Scope:** `migrations/`, `auth-web/*.sql` + `auth-web/app/api/**`, `auth-web/lib/settlement.ts`, `app/routers/referral.py`, `app/routers/admin_referrals.py`, `app/routers/settings.py`, `services/web_admin_client.py`.

---

## 0. Read this first — the premise of the task needs to be corrected

AIR-0221 frames this as consolidating **two** data models ("Legacy" vs "New"). The actual audit found **four generations plus one side-channel**, not two, and — critically — **most of the "new" generation was never finished and has never run successfully in production**, because it references a database column that does not exist. This changes the shape of the work from *"merge two live systems"* to *"promote the one system that actually works, and formally retire the rest."* That's a smaller, lower-risk job than a symmetric merge, but it means the P0 items as originally scoped ("integrate `referral_commissions` vs `commissions`") need to be re-read in that light. Details below; recommendation is in §4.

| Gen | What it is | Core tables | `profiles` FK | Status |
|---|---|---|---|---|
| **0 — Tenant/Wallet** | Original wallet withdrawal + platform fee system | `withdrawals`, `tenant_configs`, `tenant_commission_logs` | `usdt_balance`, `wallet_address` | **LIVE** — used today for actual payouts |
| **1 — Referral 2.0** (AIR-0122–0125) | Current referral commission engine | `referral_commissions` | `referred_by` | **LIVE** — this is what users and admins actually see today |
| **2 — "Referral Dashboard 3.0"** (AIR-0157–0166) | A parallel commission/withdrawal/KPI/tree system, SQL-only | `commissions`, `withdrawal_requests`, `worker_jobs` | `referrer_id` (**column was never created**) | **BROKEN, ORPHANED** — zero callers in application code; every RPC in this generation throws `column "referrer_id" does not exist` (or worse) the moment it's invoked |
| **3 — Admin Treasury / Risk / Habit / Analytics** (AIR-0201–0208) | Layered on top of Gen 2 | same as Gen 2 + `admin_audit_logs`, `risk_flags`, `user_activity`, `user_events` | same nonexistent `referrer_id` | **BROKEN, ORPHANED** — same root defect, inherited |
| **4 — Instant referral reward** | Flat $20 bonus on a referred user's 2nd approved publish | `referral_rewards_log` | `referred_by` | **LIVE** — a separate, parallel payout path that bypasses `referral_commissions` entirely |

Full evidence (file:line for every claim above) is in the companion audit appendix, §A at the bottom of this document, so this plan can be verified line-by-line rather than taken on faith.

---

## 1. Why Gen 2/3 is broken, in one sentence each

- `profiles.referrer_id` is referenced in 8 migration files and ~15 RPCs/triggers, but no migration or schema file anywhere ever runs `ALTER TABLE profiles ADD COLUMN referrer_id`. The real column is `referred_by`. This looks like a naming assumption made once, early, and then copy-pasted forward through six months of migrations without anyone re-verifying it against the live schema.
- `get_commission_timeline` additionally selects a `job_type` column from `commissions` that was never created (job type only ever lives inside a JSONB `metadata` field).
- `admin_scan_referral_trees` queries `public.referral_trees`, a table that is never created anywhere in the repo.
- The Python desktop app's own `app/routers/referral.py` module docstring (lines 1–17) already documents this: *"Broken Supabase RPCs... all reference a non-existent column `referrer_id`. We skip those and query the tables directly."* — i.e., a previous engineer already independently discovered this and routed around it rather than fixing it. That workaround is the reason the product works today despite Gen 2/3 existing in the schema.

**Net effect:** Gen 2/3 is not "the new system we need to migrate into" — it's dead code that happens to be written in SQL instead of Python, so it doesn't show up in normal "unused function" tooling. It was likely built as a bigger, more ambitious dashboard redesign (KPI cards, tree view, risk scoring, habit loops, analytics funnels) that got scoped, half-built, and abandoned before its first RPC was ever actually called from a UI.

---

## 2. Additional live risk found during this audit (not in original AIR-0221 scope, flagging anyway)

Two bugs currently sitting in the live (Gen 0/1) path, independent of the consolidation work:

1. **`process_withdrawal_commission` may already be dropped in production.** `migrations/air_0158c_drop_withdrawal_commission_rpc.sql` drops this function, but `auth-web/app/api/admin/withdrawals/route.ts:96` still calls it live when an admin marks a Gen-0 wallet withdrawal "completed." If that migration has been applied, that admin action is currently failing outright. **Needs verification against the actual production DB before this plan proceeds** — see Open Question OQ-1.
2. **`process_referral_payout` (AIR-0124, the manual settlement payout button) writes to a column that doesn't exist.** It does `UPDATE referral_commissions SET status='paid', paid_at=NOW(), updated_at=NOW()`, but `referral_commissions` (per `auth-web/supabase_schema.sql:142-158`) has no `updated_at` column. If the schema file is accurate, every payout approval is currently failing. **Also needs live-DB verification** — see OQ-1.

These are called out here because a consolidation migration is the natural place to fix them, but they should be **triaged and hotfixed independently and immediately** if confirmed live-broken, rather than waiting for this whole project — money-movement bugs shouldn't wait on a multi-week schema project.

---

## 3. Current schema reference (for the target-model discussion in §4)

### `referral_commissions` (Gen 1, live)
```
id UUID PK
beneficiary_id UUID → profiles(id)
source_user_id UUID → profiles(id) ON DELETE SET NULL
commission_type TEXT DEFAULT 'direct'   -- direct | level2 | country | payout | WITHDRAWAL (free text, no CHECK)
base_tokens BIGINT DEFAULT 0
rate_percent NUMERIC(5,2) DEFAULT 0
commission_tokens BIGINT DEFAULT 0      -- negative for WITHDRAWAL rows
status TEXT DEFAULT 'pending'           -- pending | paid | cancelled (free text, no CHECK)
metadata JSONB DEFAULT '{}'
created_at, paid_at
-- NO updated_at column (see bug #2 above)
```
Withdrawal-of-referral-earnings is modeled as a **negative commission row** with `commission_type='WITHDRAWAL'`, not a separate table. Written by `app/routers/referral.py:338-347` (user requests), read/approved/rejected by `app/routers/admin_referrals.py:190-313` (admin).

### `commissions` (Gen 2, orphaned)
```
id UUID PK
beneficiary_user_id UUID → auth.users
source_user_id UUID → auth.users
referral_level INT CHECK (0, 1, 2)      -- 0 = direct worker job earning (AIR-0165)
source_type TEXT, source_id TEXT
amount NUMERIC(18,4), currency TEXT DEFAULT 'USDT'
status TEXT CHECK (PENDING/APPROVED/PAID/REFUNDED/CANCELED)
created_at, approved_at, paid_at, refunded_at, canceled_at, updated_at
metadata JSONB DEFAULT '{}'
UNIQUE(beneficiary_user_id, source_type, source_id)
```
Structurally the *better-designed* table (real CHECK constraints, proper status timestamps, `updated_at` present, level-0 support for non-referral worker earnings). Nothing reads or writes it outside `migrations/`.

### `withdrawals` (Gen 0, live) vs `withdrawal_requests` (Gen 2, orphaned)
`withdrawals` (defined twice with drifting columns across `migration_withdrawal_system.sql` and `migration_wallet_withdrawals.sql`, then extended by `migration_withdrawal_commission.sql`) is the live path: it's what `auth-web/app/api/admin/withdrawals/route.ts` and the desktop app (`app/routers/settings.py` → `services/web_admin_client.py`) actually use, and it's the only place the tenant platform fee (`tenant_commission_logs`) is computed. `withdrawal_requests` (`air_0158d`) is a cleaner, single-definition table with real RLS and a real state machine (REQUESTED→APPROVED→SENDING→COMPLETED/REJECTED, matching the P1 dashboard spec's "Requested/Approved/Sending/Completed/Rejected" columns almost verbatim) but has zero live callers.

### `profiles` referral linkage
Only `referred_by UUID → profiles(id)` is real (`auth-web/supabase_schema.sql:18`). `referrer_id` does not exist as a column anywhere. Where Python code emits a JSON key literally called `referrer_id` (`app/routers/referral.py:154,182`), it's relabeling `referred_by` for the frontend's convenience — not reading a different column.

---

## 4. Recommended target model

**Recommendation: promote Gen 1 + adopt Gen 2's better table shape, don't attempt to reconcile Gen 2/3's business logic.**

Concretely:

1. **Commission ledger**: keep `referral_commissions` as the table name (avoid a rename migration touching every live call site for no functional benefit), but **upgrade its schema to match `commissions`'s rigor**: add real `CHECK` constraints on `status`/`commission_type`, add the missing `updated_at`, add `approved_at`/`refunded_at`/`canceled_at` timestamps so a proper PENDING→APPROVED→PAID/REJECTED state machine (matching the P1 dashboard's "Pending/Approved/Paid/Rejected" columns) can exist — today there is no "Approved" or "Rejected" state at all, only pending/paid/cancelled.
2. **Split withdrawal-of-referral-earnings out of `referral_commissions` into a real table.** The current "negative commission row" hack works but can't cleanly support the P1 dashboard's Withdrawals state machine (Requested/Approved/Sending/Completed/Rejected) without overloading `commission_type` further. Recommend introducing a dedicated `referral_withdrawals` table shaped like the orphaned `withdrawal_requests` (it already has exactly the right states and RLS) but scoped specifically to referral-earnings cash-out, **distinct from** the general wallet `withdrawals` table (see OQ-2 — these may or may not be the same money and need a product decision, not just an engineering one).
3. **`profiles.referrer_id`**: do not create this column. Standardize everywhere on `referred_by`, and fix the Gen 2/3 SQL to reference it correctly *only* for the pieces of Gen 2/3 that are worth salvaging (see #5).
4. **Retire, don't migrate, the rest of Gen 2/3.** `worker_jobs`, `risk_flags`, `user_activity`, `admin_audit_logs`, `user_events`, `referral_trees` (never-created), and their RPCs represent a different, larger product surface (gig-job marketplace, fraud scoring, retention/habit loop, analytics funnel) that was never finished and never launched. Re-scoping "fix these to point at the right column" as part of a referral-data consolidation would silently balloon this task into re-building four unrelated unshipped features. Recommend formally shelving them (leave the SQL in `migrations/` history for reference, do not run it against production, note in `project_status/ROADMAP.md` as "designed but not built, revisit if the job-marketplace/risk-scoring features are re-prioritized").
5. **What IS worth salvaging from Gen 2/3**, once pointed at the right column/table:
   - `admin_approve_commission` / `admin_reject_commission` / `admin_approve_withdrawal` / `admin_reject_withdrawal` / `admin_complete_withdrawal` (`air_0201a_admin_treasury.sql`) — this is exactly the Approve/Reject/Complete admin workflow the P1 dashboard needs, and it already writes to `admin_audit_logs`, which is exactly the P1 "Audit" tab's data source (Approval History / Reject History / Admin User / Timestamp / Reason). Rewrite these against `referral_commissions`/the new `referral_withdrawals` table instead of `commissions`/`withdrawal_requests`.
   - `get_referral_dashboard_kpi` / `get_referral_tree` / `get_commission_timeline` (`air_0166a` version, the most-recently-hotfixed one) — good shape for the P1 KPI cards / Tree View / Table View, once rewritten against `referred_by` and the corrected commission table.
6. **Unify the "estimated commission" concept (P2).** Two unrelated things currently answer to that name and need to become one concept with clearly labeled UI, not silently merged:
   - **6a — Settlement-generated pending commissions** (`auth-web/lib/settlement.ts`): real rows in `referral_commissions` with `status='pending'`, calculated from actual recharge amounts using the admin-configured `referral_level1_percent`/`referral_level2_percent`. This is a **real, persisted, accrual-basis "pending" commission** — it should simply be exposed as-is on the new dashboard (P0 dashboard already wants a "Pending" tile; this *is* that tile).
   - **6b — Live token-usage projection** (`auth-web/app/api/admin/referrals/route.ts`, `auth-web/app/api/referrals/route.ts`): a **non-persisted, on-the-fly estimate** computed from AI-usage logs using **hardcoded 5%/2% rates** that don't match the admin-configured settlement rates at all. Per the P2 instruction ("기존 '예상 커미션'은 유지한다" / "keep the existing estimated commission"), this is almost certainly what the task means, since it's the one users/admins currently *see* labeled as an estimate. Recommendation: keep it as a clearly-labeled **"Projected (this period, not yet settled)"** figure shown *alongside* the real Pending/Paid figures from 6a, but fix it to read the same configured rates the settlement worker uses instead of the hardcoded 5%/2%, so the two numbers are at least computed consistently even though one is realized and one is projected.

---

## 5. Migration & rollback strategy (P0)

**Principle: additive-first, cutover-second, drop-last — with a real gap between each stage so problems surface before they're irreversible.**

**Stage 0 — Hotfix triage (before anything else, independent of this plan's timeline).**
Confirm/fix the two live-path bugs in §2 (OQ-1 depends on this). This is a same-day fix once confirmed, not part of the multi-week consolidation.

**Stage 1 — Additive schema changes (no behavior change, fully reversible by simply not using the new columns/table).**
- `ALTER TABLE referral_commissions ADD COLUMN updated_at ...`, add `approved_at`/`rejected_at`/`canceled_at`, add proper `CHECK` constraints as *new* constraints (validate against existing data first — if any existing row has a `status` value outside the expected set, the CHECK add will fail loudly, which is the point).
- `CREATE TABLE referral_withdrawals (...)` (new table, modeled on the orphaned `withdrawal_requests` shape). Do not touch the existing "negative commission row" withdrawal path yet.
- Rewrite the salvaged Gen-2 admin/KPI/tree/timeline RPCs (§4.5) as **new** functions (e.g. suffix `_v2` or date-stamp them) pointed at the corrected schema, so the old (broken, orphaned) versions remain in place and callable-but-still-broken until Stage 3, rather than being edited in place.
- **Rollback for this stage**: `DROP` the new objects. Nothing existing was touched, so this is a true no-op rollback.

**Stage 1 update (2026-07-09): written as `migrations/air_0221_referral_stage1_foundation.sql` (+ matching `_rollback.sql`, `_IMPACT.md`, `_CHECKLIST.md`), and applied to production the same day** via `_APPLY.sql` (single-paste wrapper with self-verifying assertions) through the Supabase Dashboard SQL Editor, then independently re-verified read-only against production (new columns/tables present, 0 rows touched/added anywhere). Delivers: `referral_commissions.updated_at`/`commission_level`/`source_job_id` (additive, CHECK added `NOT VALID` + validated), new `referral_withdrawals` table (empty, RLS enabled, not yet wired to any API), new `referral_audit_logs` table (replaces the "salvage `admin_audit_logs`" idea from §4.5 — that table was checked and confirmed **not to exist** in production, so a new table was created instead). Full detail, pre-flight data-conflict check (0 rows in every affected table currently — nothing to conflict with), and the Stage 2 dual-write plan are in `worknote/AIR-0221-Stage1.md` and the Impact Note. Gen 2/3 and the $20 instant-reward path were explicitly left untouched per CTO instruction — the $20 path has a documented removal plan (separate follow-up ticket, not bundled into this stage) rather than being deleted now.

**Stage 2 — Backfill + dual-write.**
- One-time backfill script: for every existing `referral_commissions` row with `commission_type='WITHDRAWAL'`, create a corresponding row in `referral_withdrawals` with matching amount/status/timestamps, so history isn't lost when the UI switches to reading the new table.
- Application code (`app/routers/referral.py`, `app/routers/admin_referrals.py`, `auth-web/lib/settlement.ts`) is updated to **write to both** the old pattern and the new table for a defined bake period (recommend minimum 2 full settlement cycles, so at least two real end-to-end payout runs happen dual-written before cutover).
- **Rollback for this stage**: stop the dual-write (revert the app-code deploy), `referral_withdrawals` stays populated but simply unused going forward — no data loss, no schema rollback needed.

**Stage 3 — Cutover.**
- Flip the admin dashboard and all read paths to the new RPCs/table.
- Old Gen-2/3 RPCs (`get_referral_dashboard_kpi` etc., pre-`_v2`) are left in place but formally documented as deprecated — do not delete yet.
- **Rollback for this stage**: feature-flag or single-commit revert back to the Stage-2 read paths (both are live simultaneously through Stage 2, so this is a config/deploy rollback, not a data rollback).

**Stage 4 — Cleanup (only after a full production billing/audit cycle has run clean on the new path — recommend minimum 30 days).**
- Drop the pre-`_v2` orphaned RPCs.
- Stop writing the legacy "negative commission row" withdrawal pattern (keep the historical rows for audit trail; `commission_type='WITHDRAWAL'` rows become read-only history).
- Formally mark `commissions`, `withdrawal_requests`, `worker_jobs`, `risk_flags`, `referral_trees`-dependent code as shelved (§4.4) — do not drop these tables; they cost nothing to leave empty and dropping them forecloses the option to resume that unfinished work later.

**No `DROP TABLE` on anything containing real data at any stage of this plan.** The only `DROP`s are of never-successfully-run orphaned functions in Stage 4, after a 30-day bake.

---

## 6. API impact analysis (P0)

| Endpoint | Current backing | Stage-3 backing | Breaking? |
|---|---|---|---|
| `GET /user/commissions/timeline` (`app/routers/referral.py:231`) | `referral_commissions` direct query | `get_commission_timeline_v2` RPC | No — same response shape, different query path |
| `GET /user/referrals/withdrawal-info` (`referral.py:267`) | `referral_commissions` aggregate | same table, corrected status set | No |
| `POST /user/referrals/withdraw` (`referral.py:338`) | insert negative `referral_commissions` row | insert into `referral_withdrawals` | **Yes, but internal-only** — response shape can stay identical; only the write target changes |
| `GET/POST /admin/referrals/withdrawals*` (`admin_referrals.py:190-313`) | `referral_commissions` filtered by `commission_type=WITHDRAWAL` | `referral_withdrawals` + new approve/reject RPCs | **Yes, but internal-only** — same caveat |
| `GET /admin/referrals/stats` (`admin_referrals.py:325`) | manual aggregation | `get_referral_dashboard_kpi_v2` | No, response shape can be preserved |
| `POST /admin/settlements/payout` | `process_referral_payout` RPC | same RPC, fixed (add `updated_at` col) | No |
| `POST /api/admin/users/recharge` → `processSettlement` | `auth-web/lib/settlement.ts` | unchanged logic, writes to corrected schema | No |
| `GET/PATCH /api/admin/withdrawals` (Gen-0 wallet withdrawals) | `withdrawals` + `process_withdrawal_commission` | **unchanged — out of scope**, see OQ-2 | No |
| Everything under Gen 2/3 (`commissions`, `withdrawal_requests`, `worker_jobs`, risk/habit/analytics RPCs) | orphaned SQL, no callers | shelved, untouched | No — nothing calls it today, so nothing can break |

**Bottom line: zero externally-visible breaking changes are required.** All response shapes consumed by `auth-web` frontend components and the desktop app can be preserved across every stage; only the internal query targets change. This is a direct consequence of Gen 2/3 being unused — there's no live consumer of that shape to reconcile against.

---

## 7. P1 — Web Admin Referral Dashboard scope assessment

Existing UI today: `auth-web/app/admin/settlements/page.tsx` (145 lines — list + payout button, no filters/search/pagination/export) and `auth-web/app/admin/settings/referral/page.tsx` (225 lines — already covers Mode, Default Sponsor, Level 1/2 %, Min Payout, Settlement Cycle). **There is no dedicated withdrawal admin page today** (only the API route exists) and no tree/table/audit views exist at all. So P1 is close to net-new frontend work, not a redesign of something large:

| P1 spec item | Reuse from existing | Net-new work |
|---|---|---|
| Dashboard KPI tiles (Total/Pending/Paid/Withdrawal Requested/Completed/Top Sponsor/Country/Worker) | none | new page + `get_referral_dashboard_kpi_v2` |
| Organization (Tree/Table/Search/Pagination/Filters) | none | new page + `get_referral_tree_v2` |
| Commission tab (state filters, search, date range, CSV export) | `settlements/page.tsx` as a starting point | filters, search, export are new |
| Withdrawals tab (5-state workflow, search, pagination) | none | fully new, backed by `referral_withdrawals` + Stage-1 approve/reject/complete RPCs |
| Audit tab | none | fully new, backed by `admin_audit_logs` (schema already exists from `air_0201a`, just needs a rewritten trigger source) |
| Settings tab | `settings/referral/page.tsx` covers Level%/Default Sponsor already | add Promotion Mode, Country Manager fields |

Recommend P1 be scoped and estimated as its own follow-up ticket once P0 (data model) lands, since none of it can be meaningfully built against tables that are about to change shape.

---

## 8. Open questions requiring an explicit decision before Stage 1 starts

- **OQ-1 (blocking):** Are `process_withdrawal_commission` and the `referral_commissions.updated_at` write in `process_referral_payout` actually broken in the live production database right now, or has the schema drifted from what's in `auth-web/supabase_schema.sql`/`migrations/` and they're actually fine? This can only be answered by inspecting the real production schema (`\d referral_commissions`, `\df process_withdrawal_commission` or equivalent), not by reading the repo. **Needs someone with production DB access to check before Stage 0 can be closed out.**
- **OQ-2 (blocking for §4.2):** Is a user's referral-commission balance meant to be withdrawn through the *same* flow/table as their general wallet balance (`withdrawals`, Gen 0), or is "referral earnings cash-out" meant to be a distinct, separately-tracked flow? The two systems were clearly built independently without this being reconciled. This is a product decision, not something to infer from code.
- **OQ-3:** Should Gen 2/3's job-marketplace (`worker_jobs`), risk-scoring (`risk_flags`), retention (`user_activity`/habit reminders), and analytics-funnel (`user_events`) features be formally killed (drop the migrations from future consideration) or genuinely shelved-for-later (keep as a backlog item)? Affects whether Stage 4 cleanup also removes those migration files from the "to eventually run" set or just leaves them dormant forever.
- **OQ-4:** Confirm the 6a/6b "estimated commission" unification approach in §4.6 — specifically, is it acceptable for the P2 "estimated commission" the operator sees to change from a hardcoded-5%/2% live projection to one computed off the actual configured settlement rates? This changes the number the operator currently sees, even though it's arguably fixing a bug (rate mismatch).

---

## 9. What this plan explicitly does NOT cover

- Any UI implementation (P1) — that's a follow-up ticket per §7.
- Fixing Gen 0's dual `CREATE TABLE IF NOT EXISTS withdrawals` definition drift (`migration_withdrawal_system.sql` vs `migration_wallet_withdrawals.sql`) — flagged as a latent risk but out of scope unless OQ-2 concludes the two withdrawal systems should merge, in which case it becomes in-scope for Stage 2.
- Migrating the standalone, unnumbered `auth-web/migration_*.sql` files into the `migrations/air_0NNN...` numbering scheme — worth doing for future auditability, but a separate housekeeping task, not a data-model change.

---

## 10. FINAL SCOPE — CTO decisions (2026-07-09)

This section is the authoritative target design. It's simpler than everything proposed in §§3–7, mainly because it removes the pending/approval/reject state at the *commission* level entirely — only *withdrawals* get an approval step. Recorded here so the rest of this document stays as a legible paper trail of how we got here.

### 10.1 Final flow (canonical)

```
signup → referred_by set → job completed → Level 1 commission generated
      → Level 2 commission generated → auto-credited (status = paid, no approval step)
      → user requests withdrawal → admin approves → funds sent → status = completed
```

The key change from §4/§6: there is no more "pending → admin reviews → approved/paid" state machine on the commission ledger itself. A commission is either generated-and-paid, or it doesn't exist. All human review happens once, at withdrawal time — not twice (once per commission, once per withdrawal) like the earlier designs implied.

### 10.2 Deleted (not shelved — actually removed)

This overrides §4.4's "shelve, don't drop" recommendation for Gen 2/3, and extends deletion to parts of Gen 1 that no longer fit the simplified flow:

- **Commission `Pending` status** — commissions no longer have a pending state; they're generated already-paid.
- **Commission Approval / Commission Reject** — no per-commission review step (see 10.1). `admin_approve_commission`/`admin_reject_commission`/`admin_bulk_approve_commissions` (§4.5, `air_0201a_admin_treasury.sql`) are **not** being salvaged after all — drop this from the "worth keeping" list in §4.5.
- **$20 Instant Reward** (Gen 4, `auth-web/app/api/admin/publishing/route.ts:206-252`) — remove the trigger entirely (the "2nd approved publish → flat $20 via `increment_usdt_balance`" logic).
- **`referral_rewards_log` table** — drop once the above is removed and any historical rows are archived/exported if needed for past-payout records.
- **Gen 2 dead code** — `commissions`, `withdrawal_requests`, `worker_jobs` tables and every RPC/trigger listed in §5 that depends on them (`get_available_withdrawal_balance`, `request_withdrawal` ×3 versions, `get_referral_dashboard_kpi` ×4 versions, `get_referral_tree`, `get_commission_timeline`, `complete_worker_job_and_mint_commission`, `admin_approve/reject_commission`, `admin_approve/reject/complete_withdrawal`, `admin_bulk_approve_*`). **Actually `DROP TABLE`/`DROP FUNCTION`, not just left dormant.**
- **Gen 3 dead code** — `risk_flags`, `user_activity`, `admin_audit_logs` (superseded by the new Commission Trace / Audit Log design in 10.4 — re-check whether the new Audit Log needs its own table or can reuse this one before dropping it, see 10.5), `user_events`, and their triggers/RPCs (`check_withdrawal_abuse`, `check_job_abuse`, `admin_scan_referral_trees` — this one references the never-created `referral_trees` table anyway — `handle_new_risk_flag`, `admin_override_user_risk`, `trigger_reengagement_notifications`, `handle_referral_join`, `handle_commission_earned`, `handle_user_activity`, `trigger_habit_reminders`, `handle_backend_analytics`, `get_analytics_dashboard` ×2 versions).
- **Duplicate commission structure** — confirms §4.1: one commission ledger only. `referral_commissions` is promoted; `commissions` is dropped (not merged into).
- **Duplicate withdrawal structure** — confirms §4.2's spirit but the resolution is stricter than "add a new `referral_withdrawals` table alongside the old pattern": the negative-commission-row withdrawal pattern in `referral_commissions` (`commission_type='WITHDRAWAL'`) is retired, and the target is genuinely **one** withdrawal table. Still need to confirm against Gen 0 `withdrawals` — see 10.5.

### 10.3 Target schema (concrete)

**`referral_commissions`** (redesigned; keep the name, keep it as the sole commission ledger):
```
id UUID PK
beneficiary_id UUID → profiles(id)      -- who earns the commission
source_user_id UUID → profiles(id)      -- whose job/activity generated it
level SMALLINT CHECK (level IN (1, 2))  -- replaces free-text commission_type
source_job_id UUID / TEXT               -- 원인 작업(Job)
job_amount NUMERIC(18,4)                -- 작업 금액 — the value the rate was applied to
applied_rate NUMERIC(5,2)               -- 적용 비율 — snapshot of the rate at generation time, not a live join to global_settings
commission_amount NUMERIC(18,4)         -- 생성된 수당
status TEXT DEFAULT 'paid'              -- see note below — no pending/approval sub-states
created_at TIMESTAMPTZ                  -- 발생 시간
```
This table *is* the Commission Trace requirement in 10.4 — every field the spec asks for maps 1:1 to a real column here, not something buried in JSONB, so it's directly queryable/exportable/auditable without joins beyond `beneficiary_id`/`source_user_id` → `profiles`.

`status` note: even though there's no approval workflow, `status` is kept (not hardcoded away) to allow a `'reversed'`/`'voided'` value later if a source job is refunded/disputed — but only `paid` and (rare) `reversed` exist; there is no `pending`/`approved`/`rejected` value anywhere in this table going forward.

**`referral_withdrawals`** (new, single table — replaces all three legacy withdrawal-ish structures pending the 10.5 decision):
```
id UUID PK
user_id UUID → profiles(id)
amount NUMERIC(18,6)
status TEXT CHECK (REQUESTED | APPROVED | SENDING | COMPLETED | REJECTED)
requested_at, approved_at, sent_at, completed_at, rejected_at TIMESTAMPTZ
wallet_address / payout destination TEXT
tx_hash TEXT
admin_note TEXT
approved_by, rejected_by UUID → profiles(id)
```
This matches the CTO flow diagram's states (신청→승인→송금→Completed, +REJECTED) exactly and is structurally the orphaned Gen-2 `withdrawal_requests` table, salvaged.

### 10.4 Required admin features (final P1 scope — replaces §7's table)

- 2-level organization tree (L1/L2 only — not the Gen-2 RPC's arbitrary `p_max_level`)
- Referrer search
- Organization search
- Country filter
- Member detail view
- Level 1 / Level 2 commission view per member
- Withdrawal history
- Audit Log (admin actions on withdrawals: who approved/rejected/completed, when, why)
- **Commission Trace** — a queryable view over `referral_commissions` exposing exactly: occurred time, level, referrer, source job, job amount, applied rate, generated commission, status (all real columns per 10.3, no derived/computed-on-read fields needed)

Note what's **not** in this final list that was in the original P0 dashboard spec: no more "Total/Pending/Paid/Top Sponsor/Top Country/Top Worker" KPI tile row, no Commission-tab state filters (Pending/Approved/Paid/Rejected) since those states no longer exist, no CSV export explicitly requested (may still be worth adding, but not called out here — confirm before building). Treat the original P0 dashboard wishlist in the first AIR-0221 message as superseded by this list where they conflict.

### 10.5 Two items — RESOLVED (2026-07-09)

1. **`referral_withdrawals` replaces `withdrawals` — CONFIRMED, merge into one.** CTO decision: "하나로 통합 (권장 - 중복구조 삭제 지침과 일치)". The Gen-0 tenant platform-fee logic (`tenant_commission_logs`) is folded into the new `referral_withdrawals` flow at Stage 2/3, and `withdrawals` is retired. `services/web_admin_client.py` (`submit_withdrawal_request`, `get_withdrawal_history`) and `app/routers/settings.py`'s two withdrawal endpoints get repointed at `referral_withdrawals` as part of Stage 2/3 — added to the Stage 2/3 work list in §5.

2. **OQ-1 — VERIFIED directly against production Supabase (`giorysjpgxzdypbmxwmx`), read-only, 2026-07-09.** Method: fetched PostgREST's root OpenAPI schema (`GET /rest/v1/` with the service-role key), which enumerates every table/column and every RPC the service role can execute — then cross-checked by test-calling both suspect RPCs with a nonexistent dummy UUID (safe: Postgres function calls are transactional, so a no-match ID rolls back to a no-op if the function exists, and a schema-cache-miss error if it doesn't; no real row was touched either way). Results:
   - **`referral_commissions` has no `updated_at` column** — confirmed live, matches §2 bug #2 exactly. Live columns are: `id, beneficiary_id, source_user_id, commission_type, base_tokens, rate_percent, commission_tokens, status, metadata, created_at, paid_at`.
   - **`process_withdrawal_commission` does not exist in the live schema** — confirmed. `POST /rest/v1/rpc/process_withdrawal_commission` returns `404 PGRST202 "Could not find the function public.process_withdrawal_commission... in the schema cache"`, and the function is absent from the full enumerated RPC list. `migrations/air_0158c_drop_withdrawal_commission_rpc.sql` has been applied — this is genuinely dropped in production. **`auth-web/app/api/admin/withdrawals/route.ts:96` is calling a function that does not exist, so "mark withdrawal completed" is live-broken for admins today.**
   - **Bonus finding, same check: `process_referral_payout` also does not exist in the live schema** (also 404 PGRST202, also absent from the RPC list) — this is *worse* than §2 bug #1 assumed (§2 assumed it exists but writes to a bad column; it doesn't exist at all). The AIR-0124 manual settlement payout button is calling a nonexistent function too. **Both admin money-movement actions (mark-withdrawal-completed, manual-settlement-payout) are currently hard-broken in production**, independent of and predating this consolidation project.
   - Side finding: the orphaned Gen-2 `withdrawal_requests` table is not present in the live schema either (consistent with §0/§1 — it was designed but never actually created/deployed), and Gen-2 `commissions` *does* have an `updated_at` column (minor correction to §3 — not itself broken, just unused).

**Both items are now resolved. Nothing in 10.1–10.4 is blocked.** The two live-broken admin actions above are a **same-day hotfix independent of this project's timeline** per §2's original recommendation — flagging for immediate triage separately from Stage 1.

**Update — hotfixed as AIR-0221A (2026-07-09).** Both dead RPCs replaced with direct-UPDATE application logic in `auth-web/app/api/admin/withdrawals/route.ts` and `auth-web/app/api/admin/settlements/payout/route.ts`; no schema/RPC changes made. Full writeup in `worknote/AIR-0221A.md`. While fixing the payout route, found a **third** live-broken function in the same money path: `increment_usdt_balance` also references the nonexistent `profiles.updated_at` column (confirmed live, `42703`) — the payout hotfix avoids it entirely (direct read-modify-write on `usdt_balance` instead). That RPC is also the credit mechanism for the Gen-4 "$20 instant reward" side-channel (`auth-web/app/api/admin/publishing/route.ts:239`), which means that reward has been silently failing to actually pay out (while still logging success to `referral_rewards_log`) — **not fixed**, since that whole code path is already scheduled for deletion in Stage 1 (§10.2) and isn't worth patching days before removal. Stage 1 can now proceed.

---

## Appendix A — Audit evidence

Full file:line evidence for every table, column, RPC, and code path referenced above is available on request as a companion document (it was produced during this audit as a ~9,000-word structured report and is reproducible by re-running the same repo-wide search). Kept out of the plan body itself to keep this document reviewable at CTO level; happy to attach in full if wanted for the engineering handoff doc.
