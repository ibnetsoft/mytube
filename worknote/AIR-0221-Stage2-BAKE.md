# AIR-0221 Stage 2 — Bake Watch

**Bake start date: 2026-07-09** (the day Stage 2 dual-write code — `worknote/AIR-0221-Stage2.md` — was deployed).

**No code, DB, or UI changes in this document or its authoring.** This is an observation log and a set of check procedures, updated over time as the bake period progresses. Stage 3 (Read Cutover) does not start until the entry criteria at the bottom are met.

---

## ⚠ Baseline finding, 2026-07-09 — read this before interpreting anything below

Pulled the full `global_settings` table (read-only) as part of establishing the bake baseline. **There is no `referral_mode` key in `global_settings` at all.** `auth-web/lib/settlement.ts` reads `settings['referral_mode'] || 'OFF'` — with no key present, this always evaluates to `'OFF'`, and the settlement worker's very first check (`if (mode === 'OFF') { ...skip... }`) means **the settlement worker currently never generates any commissions, regardless of the Stage 2 dual-write code being deployed and correct.** There are also no `referral_level1_percent`/`referral_level2_percent` keys configured.

**Consequence for this bake watch: zero settlement cycles can actually occur, and therefore zero real dual-write activity can be observed, until `referral_mode` is turned on (and level percents configured) in `global_settings` — a product/business decision, not a bug, and explicitly not something this ticket authorizes changing (DB 변경 금지).** This is surfaced here so the bake period's clock doesn't start being counted against wall-clock time while the underlying system is inactive — "2 settlement cycles" should be read as "2 cycles of actual referral_mode-on activity," not "2 calendar periods." Recommend flagging to the CTO/product owner separately: the bake period cannot produce a meaningful signal until this is turned on.

Baseline row counts, confirmed via read-only REST query, 2026-07-09:

| Table | Rows |
|---|---|
| `referral_commissions` | 0 |
| `referral_commissions` where `commission_type = 'WITHDRAWAL'` (legacy withdrawal rows) | 0 |
| `referral_withdrawals` | 0 |
| `referral_audit_logs` | 0 |

Every observation item below currently reads "0 / 0 — no activity yet to evaluate" as a direct consequence of the finding above, not because the dual-write code is failing. This will be re-checked at each bake watch pass.

---

## Observation items (1–8) and how each is checked

### 1. `[Stage2 dual-write]` failure log presence

**Limitation, stated plainly**: this environment has read-only access to the production Supabase database (via `SUPABASE_SERVICE_ROLE_KEY` REST calls) but **no access to the running application server's stdout/log output** (the desktop app and/or the Next.js deployment). Every `[Stage2 dual-write] ...failed...`/`...error...` line the Stage 2 code prints (in `app/routers/referral.py`, `app/routers/admin_referrals.py`) goes somewhere this session cannot read.

Two ways to actually check this:
- **Direct (preferred)**: whoever operates the server(s) greps/tails logs for the literal string `[Stage2 dual-write]` over the bake window. Any hit is a failure event — note its frequency and whether it's a transient blip or a systematic pattern (e.g., every single request failing the same way, vs. one-off network hiccups).
- **Indirect proxy, checkable from here**: item 5's matching query below. A logged dual-write failure and a legacy/new-table row-count or content mismatch are two views of the same underlying fact — if item 5's parity check is clean, that's strong (though not conclusive, since a failure that self-corrects on retry wouldn't necessarily leave a mismatch) indirect evidence that dual-writes are succeeding.

### 2. `referral_commissions` row count

```sql
SELECT count(*) FROM public.referral_commissions;
SELECT count(*) FROM public.referral_commissions WHERE commission_level IS NOT NULL;
SELECT count(*) FROM public.referral_commissions WHERE source_job_id IS NOT NULL;
```
The second and third queries should always equal the first, for every row generated *after* the Stage 2 deploy (2026-07-09) — any row with a null `commission_level`/`source_job_id` created after that date is a dual-write gap in `settlement.ts` worth investigating. (Rows from before the deploy, if any ever existed, would legitimately have nulls — none do today, per the baseline above.)

### 3. `referral_withdrawals` row count

```sql
SELECT count(*) FROM public.referral_withdrawals;
SELECT status, count(*) FROM public.referral_withdrawals GROUP BY status;
```

### 4. `referral_audit_logs` row count

```sql
SELECT count(*) FROM public.referral_audit_logs;
SELECT action, count(*) FROM public.referral_audit_logs GROUP BY action ORDER BY action;
```

### 5. Legacy negative `WITHDRAWAL` row ↔ `referral_withdrawals` matching

```sql
-- Every legacy withdrawal request should have exactly one matching
-- referral_withdrawals row via the back-reference.
SELECT
  rc.id AS legacy_commission_id,
  rc.commission_tokens,
  rc.status AS legacy_status,
  rc.created_at AS legacy_created_at,
  rw.id AS mirrored_withdrawal_id,
  rw.status AS mirrored_status,
  rw.amount AS mirrored_amount
FROM public.referral_commissions rc
LEFT JOIN public.referral_withdrawals rw
  ON rw.metadata->>'legacy_commission_id' = rc.id::text
WHERE rc.commission_type = 'WITHDRAWAL'
ORDER BY rc.created_at DESC;
```
Flag any row where `mirrored_withdrawal_id IS NULL` (legacy request never got a mirror — a dual-write insert failure in `referral.py`) or where `mirrored_amount <> abs(rc.commission_tokens)` (amount mismatch between the two records — a data-integrity concern worth investigating regardless of which stage the project is in).

### 6. `referral_audit_logs` row created after every approve/reject

```sql
-- For each legacy WITHDRAWAL row no longer in PENDING (i.e., an admin acted
-- on it), confirm at least one referral_audit_logs entry references it,
-- either directly (entity_id = the mirror's id) or via the mirror-not-found
-- fallback (entity_id = the legacy commission id itself).
SELECT
  rc.id AS legacy_commission_id,
  rc.status AS legacy_status,
  rw.id AS mirrored_withdrawal_id,
  (
    SELECT count(*) FROM public.referral_audit_logs ral
    WHERE ral.entity_id = COALESCE(rw.id, rc.id)
      AND ral.entity_type = 'withdrawal'
  ) AS audit_row_count
FROM public.referral_commissions rc
LEFT JOIN public.referral_withdrawals rw
  ON rw.metadata->>'legacy_commission_id' = rc.id::text
WHERE rc.commission_type = 'WITHDRAWAL'
  AND rc.status NOT IN ('PENDING', 'pending')
ORDER BY rc.created_at DESC;
```
`approve_withdrawal` should produce 3 audit rows per acted-on withdrawal (`approved`, `sending`, `completed`); `reject_withdrawal` should produce 1 (`rejected`). `audit_row_count = 0` on any row here is a gap — either the whole dual-write helper silently failed, or (less likely, since it's wrapped defensively) an exception occurred before reaching the audit-insert loop.

### 7. User withdrawal-request response regression

Not directly queryable from the database — this is about the HTTP response shape/behavior of `POST /user/referrals/withdraw` staying identical to pre-Stage-2. Confirmed statically at implementation time (the function's `return` statements are untouched; the dual-write block is `try/except`-wrapped and placed *after* the point where the legacy write already succeeded — see `worknote/AIR-0221-Stage2.md`). For the bake window, this should be confirmed empirically: **any user-reported withdrawal-request failure or unexpected response during the bake period should be cross-checked against server logs for a `[Stage2 dual-write]` line at the same timestamp** — if one is present, the dual-write path is implicated only as a *log entry*, not as the cause (it cannot throw back into the response by design); if the user-facing failure has no such log line, it's unrelated to Stage 2 entirely, and is a legacy-path issue that predates this work.

### 8. Admin approve/reject response regression

Same reasoning and same check method as item 7, applied to `POST /admin/referrals/withdrawals/{id}/approve` and `.../reject`. The dual-write call in `admin_referrals.py` is invoked *after* the legacy `_supabase_patch` already succeeded and returns `{"success": True, ...}` regardless of what the dual-write helper does internally.

---

## Rollback criteria

Stage 2's own rollback is a **code revert** (redeploy the pre-Stage-2 version of `settlement.ts`, `referral.py`, `admin_referrals.py`, `web_admin_client.py`), not a database rollback — no schema changed in Stage 2. Trigger a rollback if, during the bake window, **any** of the following hold:

1. Item 7 or 8 shows a **real** user/admin-facing regression traceable to the Stage 2 code (not just a co-occurring log line — an actual behavior change, e.g. a request that used to succeed now fails, or takes materially longer). This is the only Sev-1-grade condition — per the Dual-Write Plan §8.C, the legacy path degrading because of Stage 2 instrumentation must never happen, and if it does, revert immediately regardless of how much bake data has been collected.
2. A **sustained, systematic** pattern of `[Stage2 dual-write]` failures (item 1) — e.g. every single settlement/withdrawal event fails to dual-write, rather than an occasional transient blip — indicating a real bug (wrong column name, bad filter syntax, permissions issue) rather than infrastructure noise. A systematic failure doesn't itself harm users (the whole point of best-effort dual-write), but it means the bake period is collecting no useful parity data, so there's no reason to keep it running uninvestigated — fix forward (a small, targeted code fix, back within Stage 2's own scope) rather than accumulating more silent failures.
3. Item 5's parity check shows a **data-integrity** problem beyond simple missing-mirror gaps — e.g. amounts that don't match between the legacy and mirrored rows for cases where both exist. This suggests a logic bug in the dual-write payload construction, not just a coverage gap, and should be fixed before more (potentially also-wrong) data accumulates.

**Do not roll back** for: a coverage gap alone where `mirror_found = false` because a withdrawal predates the Stage 2 deploy (expected, not a bug), or isolated/rare `[Stage2 dual-write]` failures with no discernible pattern and no user-facing effect (log and continue watching).

---

## Stage 3 (Read Cutover) entry conditions — do not start Stage 3 until ALL of these hold

Restated and made concrete from `AIR-0221_Stage2_DUAL_WRITE_PLAN.md` §9, for this specific bake watch:

1. **`referral_mode` has been turned on** (see the baseline finding above) long enough for real settlement activity to actually occur — this bake watch is meaningless until then, and the "2 settlement cycle" clock should be understood as starting from whenever that happens, not from the Stage 2 code-deploy date.
2. **Minimum two full settlement cycles** of real (not synthetic/test) dual-write activity, counted from when `referral_mode` went live — cycle length per `global_settings`'s configured settlement cadence (not currently set; confirm the intended cadence when `referral_mode` is enabled).
3. **Coverage**: item 2's `commission_level`/`source_job_id` null-check and item 5's mirror-matching query both come back clean (zero unexpected gaps) across the whole bake window, not just at a single point-in-time check.
4. **Audit completeness**: item 6's query shows the expected audit row count (3 for approved, 1 for rejected) for every admin action taken during the bake window.
5. **Zero legacy regression**: items 7/8 show no real user/admin-facing failures attributable to Stage 2 across the whole window.
6. **No unresolved rollback-trigger condition** from the section above — if one fired, it was root-caused, fixed, and the bake clock effectively restarted from the fix (a partial bake before a fix doesn't count toward the two-cycle minimum).
7. **Explicit CTO/engineering sign-off** on the actual accumulated bake data (this document, kept current) — not on this document's existence alone.

Until 1–7 all hold, Stage 3 planning does not start. This bake watch document should be updated (new dated entries appended below) at each check-in rather than replaced, so the full history of the bake window is visible in one place.

---

## Bake watch log

| Date | Referral mode | `referral_commissions` | `referral_withdrawals` | `referral_audit_logs` | Notes |
|---|---|---|---|---|---|
| 2026-07-09 (bake start) | OFF (no key in `global_settings`) | 0 | 0 | 0 | Baseline. See finding above — bake cannot progress until `referral_mode` is enabled. |
