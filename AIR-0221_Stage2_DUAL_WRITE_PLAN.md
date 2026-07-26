# AIR-0221 Stage 2 — Dual-Write Plan

**Status: DESIGN ONLY. No code changed, no DB changed by this document or its authoring.** This is the artifact to be reviewed and approved before any Stage 2 implementation work starts, per CTO instruction ("실제 구현은 CTO가 DUAL_WRITE_PLAN.md 승인한 뒤 시작").

**Prerequisite (done):** AIR-0221 Stage 1 (`migrations/air_0221_referral_stage1_foundation.sql`) applied to production 2026-07-09 and independently re-verified. `referral_commissions.updated_at/commission_level/source_job_id`, `referral_withdrawals`, `referral_audit_logs` all exist, all empty, all unwired to any application code.

**Outstanding from Stage 1, still unresolved — carried forward, not addressed by this plan:** Supabase backup/PITR coverage for the project (`giorysjpgxzdypbmxwmx`) has **not been confirmed**. This was flagged in the Stage 1 checklist (§3) and never independently verified — it requires dashboard/billing access this environment doesn't have. Recorded here per instruction so it isn't lost. Should be confirmed before Stage 2 *implementation* begins, since Stage 2 is the first stage where dual-written rows in the new tables become real data worth protecting.

---

## 1. `referral_commissions` — how `commission_level` / `source_job_id` get populated at generation time

**Where generation actually happens today:** `auth-web/lib/settlement.ts` (the AIR-0123 settlement worker). It runs on admin-triggered recharge events, reads `global_settings.referral_level1_percent`/`referral_level2_percent`, walks `profiles.referred_by` to resolve the L1 and (if present) L2 sponsor, and inserts one `referral_commissions` row per level, deduplicated via `metadata->>'source_tx_id'`.

**Proposed population, per row the worker inserts:**
- `commission_level`: `1` for the direct sponsor's row, `2` for the second-level sponsor's row. Deterministic from which loop iteration produced the row — no new logic needed, just an extra field on the same insert.
- `source_job_id`: populate with the same value already computed for `metadata->>'source_tx_id'` (the recharge transaction id). This promotes an existing value from buried JSONB into a first-class, indexed column — no new identifier needs to be invented.
- `commission_type` (existing free-text column): **left as-is, unchanged**, still written with its current value (`'direct'`/`'level2'`/etc.) — both columns coexist through the bake period, per the standing Stage 2 policy in `CONSOLIDATION_PLAN.md` §5.

**Open design question this plan surfaces but does not resolve — flagging for CTO decision before implementation:** the CTO's canonical flow (`CONSOLIDATION_PLAN.md` §10.1) describes the trigger as *"job completed → Level 1 commission generated"*. The actual live settlement worker's trigger is **admin recharge events**, not individual job/render completions. This plan's proposal (populate `source_job_id` from the recharge `source_tx_id`) matches what the *current* generator actually does. If the intended end-state is genuinely per-job commission generation (e.g., one commission per video render, not per recharge), that is a materially different trigger/business-logic change beyond what dual-write can paper over, and should be confirmed explicitly before Stage 2 implementation — not assumed by this document either way.

**Status semantics:** per §10.1/§10.2, commissions are meant to be generated already-`paid`, with no pending/approval sub-state. Since `referral_commissions.status` today defaults to `'pending'` and only becomes `'paid'` via the (AIR-0221A-hotfixed) manual payout button, Stage 2 implementation would need to change `settlement.ts` to insert rows with `status='paid'` directly (and skip/retire the manual-payout step for newly generated rows) to match the approved final flow. This is a **behavior change**, not purely additive dual-write — called out explicitly so it isn't silently bundled into "just add two columns." Recommend implementing this as part of Stage 2 (there's no real data yet, so no migration/backfill burden), but it should be an explicit, named line item in the Stage 2 implementation ticket, reviewed on its own, not inferred from this plan.

---

## 2. `referral_withdrawals` — dual-write mechanics

**Principle: dual-write is additive and best-effort. The legacy path stays authoritative through the whole of Stage 2 — nothing reads from `referral_withdrawals` yet.** A failure writing to `referral_withdrawals` must never block, delay, or roll back the legacy write it's shadowing. Concretely: wrap the new-table write in its own try/catch (or equivalent), log failures, and continue — the user-facing request must succeed or fail based on the legacy path alone, exactly as it does today.

**Where dual-write hooks in (two separate legacy entry points, both need it — see §3 for why there are two):**
- `app/routers/referral.py:338` (`POST /user/referrals/withdraw`) — after the existing negative-`referral_commissions`-row insert succeeds, additionally insert a `referral_withdrawals` row: `status='REQUESTED'`, `amount` = the requested amount, `wallet_address` = the user's on-file wallet address, `metadata = {"legacy_source": "referral_negative_commission", "legacy_commission_id": <id of the negative row just inserted>}` — the back-reference lets Stage 3 parity-check the two records against each other.
- The Gen-0 general wallet withdrawal request path (wherever a user currently initiates a `withdrawals` row — this plan doesn't re-derive that endpoint's exact location since it's out of this plan's research scope, but it's the counterpart to `auth-web/app/api/admin/withdrawals/route.ts`'s admin side) — same pattern: after the legacy `withdrawals` insert succeeds, additionally insert into `referral_withdrawals` with `metadata = {"legacy_source": "gen0_wallet", "legacy_withdrawal_id": <id>}`.

**Why both need it, not just the referral-specific one:** per the already-confirmed CTO decision (`CONSOLIDATION_PLAN.md` §10.5 item 1), `referral_withdrawals` is intended to eventually replace *both* legacy patterns, not just the referral-specific one — see §3 below for the reasoning.

**Admin-side dual-write:** `auth-web/app/api/admin/withdrawals/route.ts` (Gen-0, AIR-0221A-hotfixed) and the referral-specific admin approve/reject in `auth-web/app/api/admin/admin_referrals.py`-equivalent both get a mirrored write into `referral_withdrawals` on every state change (see §4 for the state-mapping this requires, since the old flows are coarser than the new 5-state model).

---

## 3. Negative-`WITHDRAWAL`-row and `referral_withdrawals` — simultaneous recording strategy

Today there are genuinely **two independent ledgers** for what a user might think of as "withdrawing money," and they don't currently agree on where the money even lives:

- **Legacy referral-earnings withdrawal** (`referral.py:338`): modeled as a negative `referral_commissions` row (`commission_type='WITHDRAWAL'`, negative `commission_tokens`). The user's available referral balance is computed as a `SUM()` over `referral_commissions` rows — this never touches `profiles.usdt_balance` directly.
- **Legacy general wallet withdrawal** (`withdrawals`, Gen 0, AIR-0221A-hotfixed): drains `profiles.usdt_balance` directly, with tenant-fee calculation via `calculate_commission`/`tenant_commission_logs`.

These two don't actually reconcile today: the (AIR-0221A-hotfixed) manual settlement payout (`process_referral_payout`, now direct-UPDATE) *does* credit `profiles.usdt_balance` when a commission is paid — meaning paid referral earnings land in the same balance pool the Gen-0 withdrawal drains from, while the *separate* SUM-based referral ledger in `referral.py` tracks something that, in practice, isn't backed by a real balance field at all. This inconsistency already exists in Gen 1 today, independent of this consolidation effort — flagging it here because it directly explains why the CTO's "merge into one" decision (§10.5) is the right call, not just a naming simplification: once commissions are auto-paid into `usdt_balance` (per §1 above), a referral-earnings cash-out and a general wallet cash-out really are the same money, and pretending otherwise via two ledgers is what caused this drift in the first place.

**Stage 2 strategy, given that:**
1. Keep writing to both legacy patterns exactly as they work today — **no change to either legacy write path's own behavior** in Stage 2, only additive dual-writes alongside them.
2. Every dual-written `referral_withdrawals` row carries `metadata.legacy_source` (`"referral_negative_commission"` or `"gen0_wallet"`) and a back-reference id, specifically so Stage 3 can run a reconciliation report: for every legacy row, does a matching `referral_withdrawals` row exist with a consistent amount/status? Any mismatch found during the bake period is a real finding to resolve *before* cutover, not something to paper over.
3. This plan deliberately does **not** propose changing which balance field either legacy path reads/writes in Stage 2 — reconciling the `usdt_balance`-vs-`SUM(referral_commissions)` inconsistency described above is a Stage 3 cutover concern (once `referral_withdrawals` becomes the single source of truth, this bifurcation naturally resolves, because there's only one table left to read from). Attempting to fix it mid-Stage-2 would mean touching legacy business logic, which is explicitly out of scope here.

---

## 4. Withdrawal state transitions — `REQUESTED → APPROVED → SENDING → COMPLETED / REJECTED`

Neither legacy flow has this many states today, so dual-write requires an explicit mapping, and an explicit acknowledgment of where the new model is *finer-grained* than what Stage 2 can actually drive (since no new admin UI exists yet — building one is out of scope for Stage 2, it's Stage 3+/P1 dashboard work).

| Legacy Gen-0 `withdrawals.status` | Legacy referral `referral_commissions.status` (WITHDRAWAL rows) | Mirrored `referral_withdrawals.status` | Timestamp set |
|---|---|---|---|
| `pending` (row created) | `pending` (row created) | `REQUESTED` | `requested_at` |
| *(no distinct state)* | *(no distinct state)* | `APPROVED` | *(see note below)* |
| *(no distinct state)* | *(no distinct state)* | `SENDING` | *(see note below)* |
| `completed` | `paid` | `COMPLETED` | `completed_at` |
| `rejected` | `cancelled` | `REJECTED` | `rejected_at` |

**Note on `APPROVED`/`SENDING`:** both legacy admin actions are single-step ("approve & pay" / "mark completed" happen in one click, per the current UI in `auth-web/app/admin/settlements/page.tsx` and the withdrawals admin route). Since Stage 2 builds no new admin UI, there is no independent trigger for an admin to move a withdrawal through `APPROVED` and `SENDING` as separate, deliberate steps yet. Proposed Stage 2 behavior: when the legacy single-step "complete" action fires, the dual-write sets `APPROVED`, `SENDING`, and `COMPLETED` on the mirrored row **near-simultaneously** (all three timestamps within the same request), rather than leaving `approved_at`/`sent_at` null. This is an honest limitation, not a hidden gap — full independent control over each state is what the new admin UI (P1, `CONSOLIDATION_PLAN.md` §10.4) is for for; Stage 2 only guarantees the mirrored row ends up in the *correct final state* with a defensible timestamp trail, not that intermediate states are meaningfully distinct yet.

---

## 5. `referral_audit_logs` — write points

| Event | `entity_type` | `entity_id` | `action` | `actor_id` | Trigger location |
|---|---|---|---|---|---|
| Commission generated (settlement worker) | `commission` | new `referral_commissions.id` | `generated` | `NULL` (system, no human actor) | `auth-web/lib/settlement.ts`, right after each insert |
| Withdrawal requested (either legacy entry point) | `withdrawal` | new `referral_withdrawals.id` | `requested` | `NULL` (user-initiated, not an admin action) | `app/routers/referral.py:338` and the Gen-0 wallet withdrawal request path, alongside the §2 dual-write |
| Withdrawal approved | `withdrawal` | `referral_withdrawals.id` | `approved` | admin's `profiles.id` | `auth-web/app/api/admin/withdrawals/route.ts` and the referral-specific admin approve endpoint |
| Withdrawal rejected | `withdrawal` | `referral_withdrawals.id` | `rejected` | admin's `profiles.id`, `reason` = admin-supplied note if any | same, on the reject path |
| Withdrawal completed | `withdrawal` | `referral_withdrawals.id` | `completed` | admin's `profiles.id` | same, on the complete path |

**Schema gap surfaced by this plan — RESOLVED (AIR-0221C, applied to production 2026-07-09).** `referral_audit_logs.action`'s CHECK constraint originally had no `'sending'` value; it now does (`generated | requested | approved | rejected | sending | completed | reversed`), via `migrations/air_0221c_referral_audit_action_sending.sql`. This removes the constraint that previously forced folding `SENDING` into the `completed` audit entry — Stage 2 implementation may now log a distinct `sending` audit action if/when it's actually able to drive that state independently. §4's underlying finding still holds, though: no new admin UI exists yet, so Stage 2 still can't *independently trigger* `SENDING` as a deliberate step (the legacy single-click "complete" action still moves through `APPROVED`/`SENDING`/`COMPLETED` near-simultaneously, per §4). What changed is only that the audit log is no longer schema-blocked from recording it as its own event when that becomes possible — Stage 2 can choose to emit a `sending` audit row at the same near-simultaneous point as `approved`/`completed` if that's judged useful, or continue treating it as folded into `completed`; either is now valid, and the actual choice belongs to Stage 2 implementation, not this planning document.

---

## 6. $20 Instant Reward — removal target list (execution deferred, per CTO instruction — not part of Stage 2)

Restated from `worknote/AIR-0221-Stage1.md` §4 for this document's completeness, since Stage 2 planning should account for it even though its removal isn't part of Stage 2 itself:

- **`auth-web/app/api/admin/publishing/route.ts:206-252`** — the full "2nd approved publish → $20 reward" trigger block.
  - Line 239: `await supabase.rpc('increment_usdt_balance', { uid: referrerProfile.id, amount_to_add: 20 })` — the actual credit call (already confirmed silently broken in production — `increment_usdt_balance` references the nonexistent `profiles.updated_at` column).
  - Lines 234–236: the `referral_rewards_log` dedup check (`select id ... eq('referred_user_id', ...)`) gating whether the reward has already been given.
  - Line 243: `await supabase.from('referral_rewards_log').insert(...)` — the log write, which currently happens regardless of whether the (broken) credit above actually succeeded.
- **Table `referral_rewards_log`** — 0 rows in production (confirmed during Stage 1 pre-flight), safe to drop with no archival step needed once the code above is removed.

Recommended as its own follow-up ticket (e.g. AIR-0221B), sequenced after Stage 1/2 have stabilized, not bundled into Stage 2 — restated from the Stage 1 worknote, not changed here.

---

## 7. Gen 2/Gen3 — shelved list (unchanged by Stage 2, restated for this document's completeness)

Stage 2 implementation touches none of the following. Restated from `CONSOLIDATION_PLAN.md` §0/§10.2 and `worknote/AIR-0221-Stage1.md` §5:

- **Gen 2** (`air_0157c`–`air_0166a`): tables `commissions`, `withdrawal_requests`, `worker_jobs`; RPCs `get_available_withdrawal_balance`, `request_withdrawal` (×3 versions), `get_referral_dashboard_kpi` (×4 versions), `get_referral_tree`, `get_commission_timeline`, `complete_worker_job_and_mint_commission`, `admin_approve/reject_commission`, `admin_approve/reject/complete_withdrawal`, `admin_bulk_approve_*`.
- **Gen 3** (`air_0201`–`air_0208`): tables `risk_flags`, `user_activity`, `admin_audit_logs` (confirmed nonexistent live), `user_events`; RPCs/triggers `check_withdrawal_abuse`, `check_job_abuse`, `admin_scan_referral_trees`, `handle_new_risk_flag`, `admin_override_user_risk`, `trigger_reengagement_notifications`, `handle_referral_join`, `handle_commission_earned`, `handle_user_activity`, `trigger_habit_reminders`, `handle_backend_analytics`, `get_analytics_dashboard` (×2 versions).

Actual `DROP` of these is scoped to the Stage-4-equivalent cleanup pass per `CONSOLIDATION_PLAN.md` §10.2/§5, not Stage 2.

---

## 8. Rollback strategy for Stage 2

Stage 2, as designed here, is **application-code-only** — no schema change. This makes rollback simpler than Stage 1's, but with one real caveat: Stage 2 is the first stage where the new tables accumulate genuine data, so "rollback" has two different meanings depending on what's being rolled back.

**A. Rolling back the Stage 2 code deploy (the normal case):** revert/redeploy the previous version of `auth-web/lib/settlement.ts`, `app/routers/referral.py`, the Gen-0 wallet withdrawal request path, and the two admin routes. Since dual-write is additive and best-effort (§2), the legacy paths keep working exactly as before throughout Stage 2 — reverting the dual-write code simply stops new rows from being added to `referral_withdrawals`/`referral_audit_logs`/the new `referral_commissions` columns going forward. **Rows already written by the dual-write logic are left in place, not deleted** — they're harmless (nothing reads them as a source of truth yet) and deleting them destroys the exact parity data Stage 3 needs to evaluate whether cutover is safe. This is the recommended default rollback path.

**B. Clearing Stage-2-written data specifically (only if there's a concrete reason to, e.g. a bug produced bad data that would corrupt the Stage 3 parity analysis):**
```sql
-- NOT part of this plan's approval scope — for reference only, to be reviewed
-- and explicitly authorized separately if actually needed:
DELETE FROM public.referral_audit_logs;
DELETE FROM public.referral_withdrawals;
UPDATE public.referral_commissions SET commission_level = NULL, source_job_id = NULL
  WHERE commission_level IS NOT NULL OR source_job_id IS NOT NULL;
```
This is a **data-clear**, not a schema rollback — the Stage 1 schema (columns/tables) stays in place either way. **Do not use the Stage 1 rollback script (`air_0221_referral_stage1_foundation_rollback.sql`) once Stage 2 has written real data** — that script `DROP`s the tables/columns outright and does not archive anything, exactly as its own header warns. If Stage 2 needs to be fully undone including the schema, back up (`SELECT` export or `pg_dump` of the three affected objects) before running the Stage 1 rollback, not after.

**C. Full stop condition:** if Stage 2 dual-write is found to be interfering with the legacy (still-authoritative) write path in any way — even indirectly, e.g. added latency, connection pool pressure, an exception that wasn't actually caught the way §2 intends — treat that as a **Sev-1 for this project** and revert immediately via path A, regardless of how much parity data has been collected so far. The legacy path must never degrade because of Stage 2 instrumentation; that's the whole premise of "additive, best-effort."

---

## 9. Stage 2 completion criteria (Definition of Done)

Stage 2 is done, and Stage 3 cutover planning can start, when **all** of the following hold:

1. **Coverage**: every commission generated by `settlement.ts` during the bake period has non-null `commission_level` and `source_job_id`, alongside the unchanged `commission_type`. Every withdrawal request through either legacy entry point during the bake period has a matching `referral_withdrawals` row (verified via the `metadata.legacy_*` back-references from §2/§3).
2. **State parity**: for every withdrawal that reached a terminal legacy state (`completed`/`paid` or `rejected`/`cancelled`), the mirrored `referral_withdrawals` row is in the correct corresponding terminal state (`COMPLETED` or `REJECTED`) per the §4 mapping, with no orphaned rows stuck in `REQUESTED`/`APPROVED`/`SENDING` past a reasonable processing window.
3. **Audit completeness**: `referral_audit_logs` has a `generated` entry for every new commission and a `requested`/`approved`/`rejected`/`completed` entry for every withdrawal state change during the bake period — spot-checked against §5's write points, not just row-count matched.
4. **Zero legacy regression**: no increase in error rate, latency, or user-facing failures on the legacy withdrawal/commission paths attributable to the dual-write additions (§8.C's Sev-1 condition never triggered, or if it did, was reverted and the root cause fixed before re-attempting).
5. **Bake period elapsed**: minimum two full settlement cycles with dual-write live and stable, per the standing policy already recorded in `CONSOLIDATION_PLAN.md` §5 Stage 2 — not shortened just because criteria 1–4 look clean early.
6. **Open items from this plan explicitly resolved, not left ambiguous**: the §1 "job-completion vs recharge-event" trigger-model question answered by the CTO; the §5 `'sending'` audit-action gap either accepted as out-of-scope for Stage 2 (as proposed) or explicitly re-scoped; Supabase backup/PITR coverage (carried forward from Stage 1, restated at the top of this document) confirmed.
7. **Sign-off**: CTO/engineering review of the actual bake-period parity data (not just this plan's predictions) before Stage 3 cutover planning begins.

Stage 2 is explicitly **not** done just because the code deploys cleanly and doesn't error — criteria 1–3 require observing real dual-written data over the bake period, not just verifying the write paths exist.
