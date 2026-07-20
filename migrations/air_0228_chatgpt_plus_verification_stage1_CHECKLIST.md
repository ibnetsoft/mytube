# Stage 1 Migration — Final Production-Apply Checklist

Migration: `air_0228_chatgpt_plus_verification_stage1.sql`
Rollback: `air_0228_chatgpt_plus_verification_stage1_rollback.sql`
Impact note: `air_0228_chatgpt_plus_verification_stage1_IMPACT.md`
Design doc: `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md` (§3, §4, §9 Stage 1)

**User approved starting Stage 1 (2026-07-15).** The open architecture BLOCKER
from `docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md` §1 (approval/scoring logic
must run in auth-web, not the desktop app) does not block Stage 1 — Stage 1
is pure schema/storage, no application code is written yet.

---

## 1. Production apply order

1. Confirm preconditions immediately before applying (not just at authoring time):
   - No other migration or manual schema change is queued/in-progress that touches
     `public.profiles` (all three new tables FK into it) at the same time.
   - `gen_random_uuid()` is available (already used by every other Stage-1-style
     migration in this repo, e.g. `air_0221_referral_stage1_foundation.sql` —
     `pgcrypto`/`pgcrypto`-equivalent is already enabled in this project).
2. Open a SQL session against production (Supabase SQL Editor), paste
   `air_0228_chatgpt_plus_verification_stage1_APPLY.sql` **in full, unmodified** —
   it already wraps itself in `BEGIN`/verification/`COMMIT` (see file header).
3. Read the output per the file's own instructions:
   - `NOTICE: AIR-0228 Stage 1: all verification checks passed.` → applied and committed.
   - Any red error (`Stage1 check FAILED: ...`) → nothing was committed, automatically
     rolled back. Copy the exact error text back for diagnosis before retrying.
4. Only after commit + verification: update `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md`
   §9 (mark Stage 1 done) and a new `worknote/AIR-0228-Stage1.md` recording the
   apply date, then move to Stage 2 planning.

This migration creates **only brand-new, empty objects** (3 tables + 1 storage
bucket) and touches **zero existing tables/columns** — unlike `air_0221` Stage 1,
there is no existing-table ALTER here, so the "does this affect live data" risk
class from that precedent does not apply at all.

---

## 2. Transaction application method

Use `air_0228_chatgpt_plus_verification_stage1_APPLY.sql` directly — it already
contains `BEGIN;` ... `COMMIT;` with the verification checks built in as `DO $$ ... $$`
assertions (see that file's own header for exact run instructions). Do not paste the
plain `air_0228_chatgpt_plus_verification_stage1.sql` file by itself unless you intend
to run the checklist §4 queries manually afterward in the same session before deciding
to `COMMIT`/`ROLLBACK` yourself.

- No `CREATE INDEX CONCURRENTLY` needed anywhere — every index in this migration is on
  a brand-new table that is empty at creation time, so a normal `CREATE INDEX` inside
  the transaction is instant and holds no meaningful lock.

---

## 3. Backup / snapshot check before applying

Not required to be a blocking step here: every object this migration creates is new
and empty, and it touches zero existing rows/tables/columns. There is nothing for a
backup to protect against for *this specific migration*. Standard ongoing Supabase
backup coverage for the project is unaffected either way.

---

## 4. Post-apply verification

Already built into `air_0228_chatgpt_plus_verification_stage1_APPLY.sql`'s `DO $$ ... $$`
block (§5a–§5g in that file): table existence, RLS enabled, policy counts (1 on
`subscription_verifications`, 1 on `user_badges`, 0 on
`subscription_verification_audit_logs`), trigger existence, all 9 indexes, storage
bucket exists and is private, and all three new tables are empty. If you ran the plain
migration file instead of `_APPLY.sql`, run these same checks manually (see that file
for the exact queries) before `COMMIT`.

---

## 5. Rollback execution conditions

Run the rollback (`air_0228_chatgpt_plus_verification_stage1_rollback.sql`) if:
- Any verification check fails and the transaction was already committed (if not yet
  committed, a plain `ROLLBACK` is sufficient).
- The CTO changes the Stage 1 design before Stage 2 starts — cleaner to roll back and
  re-author than hand-patch.

Do **NOT** run the rollback if Stage 2+ has started writing real rows to any of the
three tables or uploading real files to the `subscription-verifications` bucket — the
rollback `DROP`s outright, it does not archive anything. Run the pre-flight
`SELECT count(*)` queries printed at the bottom of the rollback file first, every time.

---

## 6. RLS policy presence/absence and reasoning

| Table | RLS enabled | Policies | Reasoning |
|---|---|---|---|
| `subscription_verifications` | Yes | 1: user can `SELECT` own rows | All writes (submit, review, approve/reject) go through auth-web's server-side API using the service-role key (SPEC §5.1/§5.3) — no client ever needs `INSERT`/`UPDATE` RLS. The one `SELECT` policy is defense-in-depth in case future client code ever queries Supabase directly, matching the `referral_withdrawals` precedent. |
| `user_badges` | Yes | 1: user can `SELECT` own rows | Same reasoning — badge grants only ever happen server-side (auth-web admin-approve action), never client-written. |
| `subscription_verification_audit_logs` | Yes | 0 | System/audit-only table, same reasoning as `referral_audit_logs` — RLS enabled with zero policies means only the service role (which bypasses RLS) can touch it, matching every other admin/system table in this codebase. |

No admin-specific policy is added anywhere (matching the `referral_withdrawals`
precedent) — live admin authorization is the hardcoded-email check in
`auth-web/app/api/admin/_auth.ts`, and every admin API route already uses the
service-role key, which bypasses RLS regardless of policies present.

---

## 7. Storage bucket

`subscription-verifications` is created **private** (`public = false`), the opposite
of the existing `videos` bucket. No `storage.objects` RLS policies are added for this
bucket (SPEC §4) — clients never touch Storage directly for this feature; the server
uploads on their behalf after SHA-256/MIME validation and only ever hands out
short-lived (~5 min) signed URLs to admins reviewing evidence.

---

## 8. Code changes needed in later stages (list only — not implemented here)

None of the following exist yet; Stage 1 deliberately leaves all application code untouched. See `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md` §9 for the full staged plan.

1. **Stage 2** — auth-web user-facing API (§5.1: submit/list/resubmit/badges-me) + Gemini structured-output analysis + rule-scoring logic.
2. **Stage 3** — desktop app settings screen upload UI (`templates/pages/settings.html`, `static/js/settings_page.js`) + proxy endpoints in `app/routers/settings.py` (§5.2).
3. **Stage 4** — web admin management screens (`auth-web/app/admin/subscription-verifications/**`, `auth-web/app/api/admin/subscription-verifications/**`, §5.3, §7) + a badge column on `DashboardContent.tsx`'s member list.
4. **Stage 5** — expiry sweep batch (§8 of SPEC: Vercel Cron or GitHub Actions `on: schedule`, not a desktop-resident asyncio loop) + expiring-soon notifications.
5. **Stage 6** — full QA pass, then feature-flag release.

Before Stage 2 starts, the open BLOCKER in `docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md`
§1 (where approval/scoring logic runs) needs an explicit decision if it hasn't already
been made — Stage 1's schema is designed to support either placement without
migration changes, but Stage 2's actual code depends on the answer.
