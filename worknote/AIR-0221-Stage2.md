# AIR-0221 Stage 2: Dual Write Implementation

## Goal
Implement dual-write per `AIR-0221_Stage2_DUAL_WRITE_PLAN.md`: keep the legacy referral system fully authoritative and unchanged in behavior, while additionally recording into the Stage-1 schema foundation (`referral_commissions.commission_level`/`source_job_id`, `referral_withdrawals`, `referral_audit_logs`) so a bake period of real parity data can accumulate before any Stage 3 cutover.

## Scope decision, stated explicitly

The ticket's items 1–3 name exactly three write points: the settlement worker, the **referral-earnings** withdrawal request, and **admin withdrawal status changes**. It does not name the Gen-0 general-wallet `withdrawals` table or `auth-web/app/api/admin/withdrawals/route.ts` (the AIR-0221A-hotfixed admin route for that table). The Dual-Write Plan's §2/§3 discuss both entry points as an eventual target, but this implementation is scoped to only what this ticket explicitly lists — the referral-specific path (`app/routers/referral.py`, `app/routers/admin_referrals.py`). The Gen-0 wallet withdrawal route is **not touched** by this ticket. If dual-writing that path too is wanted, treat it as a separate, explicitly-scoped follow-up, not something inferred from the Dual-Write Plan doc alone.

## Changes

### 1. `auth-web/lib/settlement.ts`
Both the L1 and L2 commission `inserts.push({...})` objects now additionally set `commission_level: 1` / `commission_level: 2` and `source_job_id: sourceTxId` (the same recharge transaction id already used for `metadata.source_tx_id`/idempotency). `commission_type`, `status: 'pending'`, and every other existing field are unchanged — this is a pure field addition to the same insert statement, not a new write path.

### 2. `app/routers/referral.py` — `POST /user/referrals/withdraw`
After the existing negative-`referral_commissions`-row insert succeeds (unchanged), the endpoint now:
1. Captures the newly-inserted row's `id` (required `return_representation=True` on that specific `supabase_post` call — see `services/web_admin_client.py` change below).
2. Inserts a `referral_withdrawals` row: `status='REQUESTED'`, `amount`, `wallet_address` = `req.dest_address`, `metadata = {legacy_source: "referral_negative_commission", legacy_commission_id: <captured id>}`.
3. Wrapped in `try/except`; any failure is logged (`print`) and swallowed. The function's return value and status codes are byte-for-byte unchanged from before this ticket — the legacy insert alone still determines success/failure to the caller.

### 3. `app/routers/admin_referrals.py` — `approve_withdrawal` / `reject_withdrawal`
Added `_stage2_dual_write_withdrawal_transition(legacy_commission_id, transitions, admin_email, reason)`, called after the existing legacy `_supabase_patch('referral_commissions', ...)` call in both endpoints (unchanged):
- **`approve_withdrawal`** (the legacy single-click action that sets the commission row straight to `COMPLETED`) mirrors through `[APPROVED → SENDING → COMPLETED]`, one `referral_withdrawals` status update and one `referral_audit_logs` row per state (3 audit rows total), matching the Dual-Write Plan §4's finding that Stage 2 has no independent admin UI to trigger these as separate deliberate actions yet — they're recorded as distinct audit events at the same near-simultaneous point in time regardless.
- **`reject_withdrawal`** mirrors `[REJECTED]` — one status update, one audit row.
- The helper looks up the matching `referral_withdrawals` row via `metadata->>legacy_commission_id = eq.<legacy id>` (verified working against production — see Verification). If no mirror row is found (e.g., a withdrawal requested before this deploy, so it was never dual-written at request time), the `referral_withdrawals` patch is skipped but the `referral_audit_logs` entries are still written, using the legacy commission id as `entity_id` and `metadata.mirror_found: false` — so the audit trail doesn't silently go missing for pre-Stage-2 rows, it just can't update a mirror that was never created.
- Entirely best-effort: wrapped in `try/except`, every failure path only `print`s, nothing raises back into the endpoint. The existing `_supabase_patch`/legacy update, and the pre-existing in-`metadata` `audit_trail` array both endpoints already maintained, are completely unchanged.

### 4. `services/web_admin_client.py` — `supabase_post`
Added an optional `return_representation: bool = False` keyword argument (sets `Prefer: return=representation` when true). Default is `False`, so every other existing caller of `supabase_post` (there are ~10+ across the codebase) is unaffected — this was needed only so `referral.py` could read back the id of the row it just inserted, to link the dual-written `referral_withdrawals` row to it.

## Explicitly not done (per ticket's constraints)

- No Read/GET API changed — every endpoint touched was a POST/PATCH write path (`/referrals/withdraw`, `/withdrawals/{id}/approve`, `/withdrawals/{id}/reject`). `GET /user/commissions/timeline`, `GET /user/referrals/dashboard`, `GET /user/referrals/tree`, `GET /user/referrals/withdrawal-info`, `GET /admin/referrals/*` are all byte-for-byte unchanged.
- No web admin UI file touched.
- No table dropped.
- No Gen 2/3 object touched.
- Commission `status` is still written as `'pending'` by `settlement.ts` (unchanged) — the "auto-paid, no pending state" business-logic change flagged as an open question in `AIR-0221_Stage2_DUAL_WRITE_PLAN.md` §1 was **not** implemented here, since the ticket only asked for `commission_level`/`source_job_id` to be recorded, not for the status semantics to change. That remains a separate decision to make explicitly before anything relies on it.

## Known side effect (not a regression, inherited from Stage 1)

Any endpoint that queries `referral_commissions` with no explicit `select` (i.e., PostgREST's implicit `select=*`) — e.g. `get_admin_commissions` in `admin_referrals.py` — will now also return `commission_level`/`source_job_id` in each row's JSON, in addition to `updated_at` which already started appearing after Stage 1. This is an unavoidable consequence of adding real columns to a live table and is not something this ticket's "기존 Read API 변경 금지" instruction can prevent without actively stripping new fields back out (not requested, not done) — flagged here for visibility, not treated as a violation, consistent with how the same effect was already accepted after Stage 1's apply.

## Verification performed

- **Static**: `python -m py_compile` and `ast.parse` on all three modified Python files — clean. A real `import app.routers.admin_referrals` / `import app.routers.referral` inside this repo's venv — both succeeded with no errors, confirming the new helper function and its dependencies resolve correctly at runtime, not just syntactically.
- **`settlement.ts`**: `npx tsc --noEmit` — no new errors. `eslint` — clean.
- **`services/web_admin_client.py`**: compiles; `return_representation` is purely additive (verified no other call site passes a 6th positional/keyword arg that would conflict).
- **Functional, against production, self-cleaning (no residual data)** — since none of these code paths could be exercised live without a real authenticated user/admin session (not available in this environment), the exact request shapes the new code produces were tested directly via REST, then deleted:
  1. Inserted a `referral_withdrawals` row shaped exactly like the Stage 2 request-time dual-write → `201`.
  2. Looked it up via `metadata->>legacy_commission_id=eq.<id>` — the exact filter syntax used in the admin-side helper's mirror lookup → found it, `200`.
  3. `PATCH`ed it to `APPROVED` with `approved_at`/`admin_id`/`reason` — the exact shape the helper sends → `200`, fields updated correctly, `updated_at` trigger fired.
  4. Inserted a `referral_audit_logs` row with `action='approved'` → `201`. Then separately confirmed `action` values `requested`, `sending`, `completed`, `rejected` (every value the helper can emit) are all accepted → `201` each.
  5. Deleted every test row. Re-confirmed `referral_withdrawals`, `referral_audit_logs`, and (untouched throughout) `referral_commissions` are all back to **0 rows**.
- **Not performed**: an actual end-to-end click-through (a real user requesting a referral withdrawal, a real admin approving/rejecting it) through the running desktop app / auth-web admin UI. Requires an authenticated session this environment doesn't have. Recommend this as the final regression check before/during the bake period — watch server logs for any `[Stage2 dual-write]` failure lines during real usage, since those indicate the additive path is failing (harmlessly, by design) without blocking users, and are exactly the signal to act on before Stage 3.

## Status

- Implementation complete, statically verified, functionally verified against production via self-cleaning synthetic writes (0 residual rows).
- Bake period has not started in the sense of "real data has accumulated" — this deploy is what starts it. Per the Dual-Write Plan §9 (Definition of Done), Stage 2 completion requires observing real dual-written data over a minimum two full settlement cycles, not just confirming the code paths work.
- No code path here changes user-facing behavior, response shapes, or existing table/column semantics — only additive writes alongside what already exists.
