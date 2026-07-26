# AIR-0221D — Referral Activation Plan

**Status: DESIGN ONLY. No code, DB, or UI changed by this document or its authoring.** This plan proposes how to turn the 2-level referral system on in production; it does not turn it on. Every action item below requires separate, explicit authorization before being executed — several of them (marked clearly) also require a small code change that is **not** part of this ticket's scope.

**Prerequisite context**: `worknote/AIR-0221-Stage2-BAKE.md`'s baseline finding (2026-07-09) — `global_settings` has no `referral_mode`, `referral_level1_percent`, or `referral_level2_percent` rows at all, so `settlement.ts` always resolves `mode = 'OFF'` and the settlement worker has never run in production. This plan is the answer to "how do we deliberately end that state."

**CTO Final Decision incorporated (2026-07-09).** The first version of this plan surfaced several open questions (enum values, what "TEST" means, what commission calculations are based on). The CTO has now resolved all of them; §§1–5 below have been rewritten in place to reflect the final decision rather than kept as a separate addendum, since a stale "originally proposed X, but actually Y" reading would be more confusing than useful here. The decisions themselves:

1. **`referral_mode` enum stays `OFF` / `NORMAL` / `PROMOTION`** — `TEST` and `ON` are **not** added. No enum code change needed after all (this resolves what the first draft flagged as a compatibility gap).
2. **"Active" is defined as `referral_mode = 'NORMAL'`.** `PROMOTION` is reserved for future marketing events, not used as an activation step.
3. **Settlement trigger is finalized as Job Completed.** Recharge-based triggering is confirmed to be fully retired, not run in parallel.
4. **Commission calculation basis is Net Settlement Amount**, not Gross — the actual settled amount after refunds/discounts/fees/promotions, not the job's face-value amount. This resolves the first draft's biggest open question (what figure `referral_level1_percent`/`referral_level2_percent` apply to).
5. **Bake period starts when real Job-Completed-triggered commissions actually begin flowing under `referral_mode = 'NORMAL'`** — not the Stage 2 code-deploy date, and not any settings change alone with zero real activity behind it.

Still **no code, DB, or UI change** — this is a documentation update only, and Stage 3 remains explicitly not started.

**CTO Final Decision, round 2 (2026-07-09, same day).** Five more points finalized — §§1, 2, 3, 4, 5 updated in place again below:

1. **Referral percents finalized**: Level 1 = **5%**, Level 2 = **2%** (replacing the earlier proposed 10%/5% placeholder values).
2. **Default Sponsor: confirmed in use**, with an explicit signup policy (valid code → connect to that referrer; no code → connect to Default Sponsor; invalid code → **registration rejected**). Researched while updating this document: **this exact policy is already fully implemented and merged** (`app/routers/auth.py`, AIR-0122) — see §1.
3. **Settlement trigger refined**: "Job Status = COMPLETED", must execute **exactly once per job** and must be **idempotent** — explicit non-negotiable requirements added to §3's implementation shape.
4. **Bake cycle redefined**: **not** a calendar window (this document's prior recommendation of "1 cycle = 1 week" is now superseded) — a cycle means one real Settlement Batch execution; the bake requirement is **2 real settlement batches observed**, not 2 weeks.
5. **Net Settlement Amount: still not finalized.** Its final definition is deferred to a dedicated future document — a **Settlement Engine Specification** — which must exist and be finalized before Stage 3 starts. This plan does not attempt to define it further.

**This ticket also formally closes the AIR-0221 Planning Phase** — see the closing banner at the bottom of this document.

---

## 1. New `global_settings` keys — proposed defaults

These key names are not new inventions — they already match exactly what two independent, already-existing (but currently unused, since no rows exist) pieces of code expect: `auth-web/lib/settlement.ts` reads them directly, and `auth-web/app/api/admin/settings/referral/route.ts` + `.../page.tsx` (AIR-0122, "Referral Default Sponsor Foundation") already has a full settings UI built for them. No naming decision is actually open here — it's already been made by prior work; this section just proposes the *values*.

| Key | Proposed default | Basis |
|---|---|---|
| `referral_mode` | `'OFF'` | Matches `settlement.ts`'s own fallback (`settings['referral_mode'] \|\| 'OFF'`) and the current de-facto state. Activation is the act of changing this to `'NORMAL'` (CTO decision — see §2). `auth-web/app/api/admin/settings/referral/route.ts:75`'s existing `['OFF', 'NORMAL', 'PROMOTION']` validation already accepts this; **no code change needed for the enum**, resolving what this plan originally flagged as a compatibility gap. |
| `referral_level1_percent` | `'5'` (5%) | **CTO-finalized value** (round 2 decision), replacing the earlier proposed 10% placeholder inherited from the dormant settings page's in-memory form default. |
| `referral_level2_percent` | `'2'` (2%) | **CTO-finalized value** (round 2 decision), replacing the earlier proposed 5% placeholder. |

**Reference only — not to be executed as part of this ticket** (DB change forbidden here):
```sql
INSERT INTO public.global_settings (key, value) VALUES
  ('referral_mode', 'OFF'),
  ('referral_level1_percent', '5'),
  ('referral_level2_percent', '2')
ON CONFLICT (key) DO NOTHING;
```

**CTO decision on the enum (resolved, no longer open)**: keep the existing `OFF` / `NORMAL` / `PROMOTION` values as-is. `TEST` and `ON` are not added. "Active" is defined as `referral_mode = 'NORMAL'`; `PROMOTION` is reserved for future marketing events and is not part of the activation sequence in §2.

### Default Sponsor — confirmed in use, policy already implemented

**CTO decision**: Default Sponsor is used, with this signup-time policy:
- Referral code entered, valid → new user connects to that referrer.
- No referral code entered → new user connects to the configured **Default Sponsor** (`referral_default_sponsor_uuid`).
- Referral code entered, invalid → **registration is rejected outright.**

**Researched while updating this document — this is not new policy to build, it's already fully implemented and merged**: `app/routers/auth.py:327-338` (AIR-0122, per `worknote/AIR-0122.md`, "E2E flow verified"):
```python
if referral_code_input:
    if not web_admin_client.validate_referral_code(referral_code_input):
        return {"success": False, "error": "유효하지 않은 추천코드입니다."}
    referred_by_code = referral_code_input
else:
    default_sponsor_uuid = web_admin_client.fetch_global_setting("referral_default_sponsor_uuid")
    if default_sponsor_uuid:
        referred_by_id = default_sponsor_uuid
```
This maps exactly onto the CTO's three-way policy: invalid code → immediate rejection with an error response (no registration proceeds); no code → falls back to `referral_default_sponsor_uuid`; valid code → connects to that referrer. **No code change is needed for this policy** — it already matches the decision precisely.

**What's still actually open here isn't the policy, it's the data**: `referral_default_sponsor_uuid` itself has **no value set** in `global_settings` today (confirmed empty during Stage 2 bake-watch baseline research — no `referral`-prefixed keys exist at all yet). Until a real UUID is set, the "no code → Default Sponsor" branch silently does nothing (`if default_sponsor_uuid:` is falsy, `referred_by_id` stays empty) — organic signups get no referrer at all, not an error, just silently unattributed. This needs a real Default Sponsor account chosen and its UUID set before activation, or the "no code entered" path produces an unintended (if not necessarily harmful) gap.

---

## 2. Activation sequence: `OFF → NORMAL`

**CTO decision**: no separate stored `TEST` state. The enum stays `OFF` / `NORMAL` / `PROMOTION` (§1), and "active" means `referral_mode = 'NORMAL'`. This section's original draft proposed a `TEST` value specifically to control blast radius before full activation — that goal doesn't go away just because the value doesn't exist in the schema, so the same validation discipline is kept below as a **process step performed while still `OFF`**, not as a second stored mode. Practically: nothing is generated for real until `referral_mode` is actually set to `'NORMAL'`, so there is no in-between DB state to worry about leaving misconfigured — the validation below happens on paper/in a lower environment if one exists, and the switch to `NORMAL` is the actual go-live moment.

**Important implementation-shape reminder, unchanged from the original research**: `settlement.ts`'s current gate is `if (mode === 'OFF') { skip }` — anything else runs the full real settlement logic. Once the Job-Completed trigger (§3) replaces the recharge trigger, whatever new gate code is written for that trigger needs the same `OFF`-check semantics preserved (`NORMAL` and `PROMOTION` both count as "run for real"; only `OFF` skips) — not a new assumption to introduce during implementation, just continuity to hold onto.

### Pre-activation validation (while `referral_mode` is still `OFF`)

**Purpose**: catch configuration and pipeline problems before the first real, live commission is ever generated — since there is no `TEST` mode to safely absorb mistakes in production once `NORMAL` is set.

1. Confirm `referral_level1_percent`/`referral_level2_percent` values are set and reviewed (§1) — these must be the real, final production rates from the start, since there's no separate test-rate phase to later reset out of.
2. Confirm `referral_default_sponsor_uuid` is deliberately set (the signup-time Default Sponsor policy is already fully implemented in `app/routers/auth.py` — see §1 — but the UUID value itself is still unset today, so this step is about the data, not the code).
3. Confirm the Job-Completed trigger (§3) and Net Settlement Amount calculation (§3) are actually implemented and correct — this needs to be true *before* `NORMAL` is set, given there's no dry-run mode to catch a wrong implementation after the fact. If a staging/lower environment exists, exercise the full trace there first: job completes → commission generated with the correct `commission_level`/`source_job_id`/net-settlement-based amount → user requests withdrawal → admin approves → `referral_withdrawals`/`referral_audit_logs` dual-writes correct (per `worknote/AIR-0221-Stage2-BAKE.md`'s check queries, items 2–6).
4. If no staging environment exists to exercise step 3 against, the first real trace happens live immediately after activation — budget for hands-on monitoring of the very first few real events after the switch, rather than treating activation as fire-and-forget.

### OFF → NORMAL (activation)

1. Explicit sign-off that step 3 above (trigger + calculation correctness) has been verified, in staging if available.
2. Set `referral_mode` to `'NORMAL'`.
3. Monitor the first real Job-Completed-triggered commission(s) closely (per step 4 above if no staging validation was possible).
4. The bake-watch clock (§4) starts specifically once real commissions are actually observed flowing under `NORMAL` — not at the moment the setting is flipped, in case there's a gap before the first real job completes.

### Rollback within this sequence

At any point, reverting is trivial: set `referral_mode` back to `'OFF'` (or delete the row) — this is a single-row `global_settings` change, not a schema or code rollback, and takes effect on the next settlement-triggering event (no redeploy needed, since `settlement.ts` reads the setting fresh from the DB each time it's invoked). Rows already generated while `NORMAL` was active are real Stage-1/Stage-2 schema data and should be handled the same way any other bake-period data is — left in place (harmless, informative) unless a concrete reason to delete them exists.

---

## 3. Settlement trigger — target: Job Completed (not recharge)

### Current actual trigger (as implemented today)

`processSettlement()` has exactly **one** call site in the entire codebase: `auth-web/app/api/admin/users/recharge/route.ts:104`, fired synchronously (fire-and-forget, errors caught and logged, not surfaced) whenever an **admin manually recharges a user's token balance**. There is no cron job, no batch process, and no other trigger anywhere. The `referral_cycle` setting (`REALTIME | DAILY | WEEKLY | MONTHLY | MANUAL`, already present in the dormant settings UI) is **not read by `settlement.ts` at all** — it has zero effect on when settlement actually runs today, despite existing as a configurable option.

### Target trigger per CTO decision: Job Status = COMPLETED

Final: the trigger basis is **Job Status = COMPLETED**, and recharge-based triggering is **fully retired**, not run in parallel. **Two non-negotiable requirements added in the round-2 decision**:
- **Executes exactly once per job.** A job's completion must generate its commission(s) a single time, never on every re-read/re-render of the job's status.
- **Idempotent.** Re-triggering the same job-completed event (retry, duplicate webhook/call, race condition) must not create duplicate commissions.

No literal `status = 'COMPLETED'` string exists anywhere in this codebase today (checked `app/routers/projects.py` and the `publishing_requests` status values) — "Job Status = COMPLETED" is being used at the spec level, and the closest existing real analog remains `auth-web/app/api/admin/publishing/route.ts`'s `PATCH` handler transitioning a `publishing_requests` row to `status = 'approved'` — this is exactly the signal the now-removed AIR-0221B "$20 instant reward" used to hook into (a "user's Nth approved video" event), so the infrastructure to detect "a job finished" already exists and is proven, even though its previous consumer was just deleted. This remains the recommended hook point; it has not been independently reconfirmed by the CTO as *the* specific hook (only the trigger *principle* was decided), so treat the exact hook location as a strong recommendation carried over from the original research, not yet a separately ratified decision.

**Idempotency implementation note, for whoever builds this next**: this codebase already has a proven pattern to reuse, not invent fresh. `settlement.ts`'s current (recharge-based) trigger already dedupes via `metadata->>'source_tx_id'` before inserting. The Job-Completed trigger has an even more natural dedup key already sitting in the schema: **`referral_commissions.source_job_id`** (added in Stage 1 specifically for this purpose). Before generating a commission for a job, check whether a `referral_commissions` row already exists with that `source_job_id` — if so, skip. This satisfies both "exactly once" and "idempotent" with the same check, and requires no new schema.

### Commission calculation basis: Net Settlement Amount — **still not finalized (CTO decision, round 2)**

The direction (net, not gross) was stated in round 1 of this decision, but **round 2 explicitly walks back treating this as resolved**: Net Settlement Amount's exact definition is **not finalized**, and finalizing it is deliberately deferred to a dedicated future document — a **Settlement Engine Specification** — which must exist and be finalized **before Stage 3 starts**. This document does not attempt to define Net Settlement Amount further; doing so here would preempt that dedicated spec.

**What this plan found while researching the surface that spec will need to cover, left here as input for whoever writes it, not as a decision**: a "Net Settlement Amount" concept, as a concrete computed figure attached to a job/publishing event, **does not currently exist anywhere in this codebase**. What exists today is adjacent but not the same thing:
- `transaction_type` on the token/transaction ledger (`auth-web/migration_token_system.sql`) includes `'REFUND'` as one of several transaction types — confirms refunds are tracked as *events*, but there's no single "net amount after all adjustments" field derived from them per job.
- `tenant_commission_logs.net_usd` (from `calculate_commission`, used in the AIR-0221A withdrawal-fee hotfix) computes a "net" figure — but that's *tenant platform fee* net-of, a completely different deduction than refunds/discounts/promotions on the job itself. Reusing it would be reusing the wrong concept just because the word "net" matches.

**Consequence**: neither the Job-Completed trigger nor the commission calculation can be correctly implemented until the Settlement Engine Specification exists and defines this. This section is intentionally left as an open pointer to that future document rather than an attempted definition.

**Implementation shape, for whoever executes this next (not done here)**: hook a new `processSettlement`-equivalent call (or a modified `processSettlement` accepting a job-completion event shape, carrying the job's Net Settlement Amount, instead of a recharge event shape) into `publishing/route.ts`'s `PATCH` handler at the point `status` transitions to `'approved'`, mirroring exactly how the now-removed §AIR-0221B reward logic used to detect that transition (`existing?.status !== 'approved' && status === 'approved'`). The recharge-route call site (`auth-web/app/api/admin/users/recharge/route.ts:104`) must be **removed** at the same time the new one is added, per the CTO's "recharge 기준 사용하지 않는다" — leaving both active would double-generate commissions from two different triggers.

---

## 4. Bake start condition — CTO decision incorporated

**CTO decision**: the bake clock does **not** start at the Stage 2 code-deploy date, and does not start merely at the moment `referral_mode` is set to `'NORMAL'` either — it starts when **real Job-Completed-triggered commissions actually begin flowing** under `referral_mode = 'NORMAL'`. A settings flip with no real activity behind it yet produces nothing to observe; the bake period is about observing real dual-write behavior under real load, so it can only meaningfully start once that real load exists. This refines (and is now the authoritative version of) §2's step 4 above.

**"Minimum two Settlement Cycles" — CTO decision, round 2: explicitly NOT calendar-based.** This document's prior recommendation ("1 cycle = 1 calendar week") is **superseded**. The CTO's definition: 1 cycle = 1 real **Settlement Batch** execution; the bake requirement is **2 real settlement batches observed**, regardless of how much or how little wall-clock time that takes. Since the Job-Completed trigger fires per-job (§3), each individual job-triggered settlement execution counts as one batch under this system's vocabulary — there is no separate cron/scheduled batch process to count instead (confirmed: none exists today, and none is being introduced by this plan). So "2 settlement cycles" concretely means: **observe 2 real, successful, correctly-idempotent Job-Completed-triggered settlement executions**, not a time window of any length. This could be satisfied by 2 jobs completing minutes apart, or take much longer if job completions are infrequent — duration is not the criterion, count is.

Once real `NORMAL`-phase activity begins, the check queries and rollback criteria already defined in `worknote/AIR-0221-Stage2-BAKE.md` apply unchanged — this plan doesn't replace that document's mechanics, only the starting clock, the cycle definition, and the trigger-change context around it.

---

## 5. Stage 3 (Read Cutover) entry conditions — updated

Supersedes `worknote/AIR-0221-Stage2-BAKE.md`'s entry-condition list (that document should be updated to point here once activation actually begins — not done automatically by this plan, since only this single document is this ticket's deliverable). All of the following must hold, not just the ones added here:

1. **Settlement Engine Specification exists and is finalized** (§3) — defines Net Settlement Amount concretely, not just "net, in principle." This is a new prerequisite added by the round-2 CTO decision and did not exist in this plan's first version — Stage 3 cannot start without it, full stop.
2. **Activation complete**: `referral_mode = 'NORMAL'` is live (§2), with the pre-activation validation steps (§2) completed first — no separate `TEST` state exists to have "exited," per the CTO decision, so this criterion is satisfied by the pre-activation checklist being done *before* `NORMAL` was set, not by a distinct stored intermediate state.
3. **Trigger migration complete** (§3): the Job-Completed trigger is implemented per the finalized Settlement Engine Specification (item 1), is verified to execute exactly once per job and idempotently (§3's non-negotiable requirements), and the recharge-based trigger (`auth-web/app/api/admin/users/recharge/route.ts:104`'s `processSettlement` call) has been **removed**, not left running in parallel.
4. **Minimum two real Settlement Batches observed** (§4 — count-based, not calendar-based), counted from when real Job-Completed-triggered commissions first began flowing under `NORMAL`.
5. All of `worknote/AIR-0221-Stage2-BAKE.md`'s original criteria (coverage, audit completeness, zero legacy regression, no unresolved rollback-trigger condition, explicit sign-off) — evaluated against real `NORMAL`-phase data.

---

## Summary — resolved by CTO decision vs. still open

**Resolved (2026-07-09, both decision rounds, no longer open)**:
- `referral_mode` enum stays `OFF`/`NORMAL`/`PROMOTION` — no code change needed for the enum itself.
- "Active" = `referral_mode = 'NORMAL'`; `PROMOTION` reserved for future events, not an activation step.
- `referral_level1_percent` = **5%**, `referral_level2_percent` = **2%** — final values, not placeholders.
- Default Sponsor policy (valid code/no code/invalid code) — confirmed in use, and confirmed **already fully implemented** (`app/routers/auth.py`, AIR-0122).
- Settlement trigger: **Job Status = COMPLETED**, recharge fully retired (not parallel), must execute exactly once per job, must be idempotent (natural dedup key already exists: `referral_commissions.source_job_id`).
- Bake start condition: when real Job-Completed commissions begin flowing under `NORMAL`, not at deploy or at the settings flip alone.
- Bake cycle definition: **count-based** (2 real Settlement Batches), explicitly **not** calendar-based — this document's earlier "1 week per cycle" recommendation is withdrawn.

**Still open (by design — not resolved by this plan, requires further decision or implementation work)**:
- **Net Settlement Amount's concrete definition — explicitly deferred to a future Settlement Engine Specification document**, required to exist and be finalized before Stage 3. This is the single largest remaining blocker.
- Whether `referral_default_sponsor_uuid` has an actual value set (the policy code is ready; the data is not).
- The exact Job-Completed hook location — `publishing/route.ts`'s approval transition remains the strongly recommended candidate but has not been independently ratified as *the* specific hook.

None of the still-open items are gaps in Stage 1/Stage 2 (that work is complete and independently verified) — they are the remaining product/engineering decisions standing between this plan and actually flipping `referral_mode` to `'NORMAL'`, and the Settlement Engine Specification stands between that and Stage 3.

---

## AIR-0221 Planning Phase — Status: **CLOSED** (2026-07-09)

Per CTO instruction, the AIR-0221 Planning Phase is now formally closed. This covers: the original consolidation audit and design (`CONSOLIDATION_PLAN.md`), the emergency hotfix (AIR-0221A), the additive schema foundation and its production apply (Stage 1), the audit-action schema hotfix (AIR-0221C), the dual-write implementation and its production deploy (Stage 2), the bake-watch procedure (`worknote/AIR-0221-Stage2-BAKE.md`), the $20 instant-reward removal (AIR-0221B), and this activation plan (AIR-0221D) — all complete as design/implementation/documentation artifacts.

**What remains is explicitly execution, not planning**, and each item below is its own future ticket, not authorized by this closure:
- Setting real values for `referral_level1_percent`/`referral_level2_percent`/`referral_default_sponsor_uuid` in `global_settings`.
- Writing the Settlement Engine Specification (defines Net Settlement Amount).
- Implementing the Job-Completed trigger (idempotent, exactly-once, per the Specification) and removing the recharge-based trigger.
- Flipping `referral_mode` to `'NORMAL'` and running the bake period (2 real settlement batches).
- Stage 3 (Read Cutover) planning — not started, gated on all of the above.

This document (`AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`) and `worknote/AIR-0221-Stage2-BAKE.md` remain the live reference for that future execution work.
