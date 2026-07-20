# Schema Impact Note — AIR-0228 Stage 1

Migration: `air_0228_chatgpt_plus_verification_stage1.sql`
Rollback: `air_0228_chatgpt_plus_verification_stage1_rollback.sql`
Design doc: `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md`

## Scope

This migration creates **only new, empty objects** — 3 tables + 1 storage bucket.
**Zero existing tables/columns are altered, zero existing rows are touched.** Unlike
`air_0221` Stage 1 (which ALTERed the live `referral_commissions` table), there is no
existing-table-mutation risk class here at all — the "does this affect current data"
question has a trivial answer: no, by construction, because nothing existing is
referenced except as an FK target (`public.profiles(id)`, read-only reference, no
column on `profiles` itself is touched).

## Files changed

| File | Type |
|---|---|
| `migrations/air_0228_chatgpt_plus_verification_stage1.sql` | new — forward migration |
| `migrations/air_0228_chatgpt_plus_verification_stage1_APPLY.sql` | new — single-paste apply wrapper with built-in verification |
| `migrations/air_0228_chatgpt_plus_verification_stage1_rollback.sql` | new — rollback |
| `migrations/air_0228_chatgpt_plus_verification_stage1_CHECKLIST.md` | new — apply checklist |
| `migrations/air_0228_chatgpt_plus_verification_stage1_IMPACT.md` | new — this note |

No application code (`auth-web/app/**`, `app/routers/**`, `services/**`) is touched by
this migration. No web admin UI is touched. Per `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md`
§9, this is deliberately the case — Stage 1 is schema/storage only.

## Tables added

### `subscription_verifications` (new table)
Full column list per SPEC §3.1: submission/status/storage fields, Gemini-extracted
fields (masked email + hash only, never raw email), AI analysis fields, review fields,
expiry fields. RLS enabled with 1 policy (user can `SELECT` own rows). A new row is
created on every submission (never overwritten) so history/audit is preserved.

### `user_badges` (new table)
Generic badge table per SPEC §3.2 — deliberately not `subscription_verification`-specific
so future badge types (e.g. event badges) can reuse it without a new table. A partial
unique index (`uq_user_badges_active_per_code`) guarantees at most one `ACTIVE` badge per
`(user_id, badge_code)` pair at the database level. RLS enabled with 1 policy (user can
`SELECT` own rows).

### `subscription_verification_audit_logs` (new table)
Audit trail per SPEC §3.3. The existing `referral_audit_logs` table was considered and
rejected for reuse — its `entity_type` CHECK is hard-constrained to
`('commission','withdrawal')`, and changing that constraint to accommodate this feature
would be an unrelated-domain schema change with its own regression risk, so a dedicated
table was created instead (same reasoning already documented in the SPEC). RLS enabled,
**zero** policies (service-role only), same pattern as `referral_audit_logs`.

## Storage bucket added

`subscription-verifications`, created **private** (`public = false`) — the opposite of
the existing `videos` bucket, which is public. No `storage.objects` RLS policies added
(SPEC §4): the design has no client ever touching Storage directly for this feature, so
policy absence is the correct default (service-role only), not an oversight.

## Rollback

Run `air_0228_chatgpt_plus_verification_stage1_rollback.sql`. Drops, in dependency
order: the storage bucket row → `subscription_verification_audit_logs` (has an FK into
`subscription_verifications`, drop first) → `user_badges` → `subscription_verifications`.
Nothing pre-existing is ever touched.

Safe as long as Stage 2+ hasn't started writing real data or uploading real files yet
(true today — nothing in this repo references these objects). The rollback file's header
includes pre-flight `SELECT count(*)` queries (and a `storage.objects` count for the
bucket) to run first if there's any doubt.

## Existing-data impact

None, by construction. This migration `INSERT`s exactly one row (the storage bucket
registration, `ON CONFLICT DO NOTHING`) and creates new empty tables — it never
`UPDATE`s, `DELETE`s, or reads any pre-existing row anywhere.

## Dry-run / pre-check performed

1. Full SQL syntax validation of all three SQL files (forward, rollback, and the
   `_APPLY.sql` wrapper) using `pglast` (Python bindings over the real PostgreSQL
   grammar, `libpg_query`) — all three parsed cleanly (33, 8, and 36 statements
   respectively). A genuine parse against Postgres's own grammar, not a heuristic linter.
2. Schema/style cross-checked against the two most recent Stage-1-style migrations in
   this repo (`air_0221_referral_stage1_foundation.sql`, `air_0221c_referral_audit_action_sending.sql`)
   for naming conventions, RLS/policy conventions, and the `_APPLY.sql`/`_CHECKLIST.md`/
   `_IMPACT.md`/`_rollback.sql` companion-file convention.
3. Migration number `air_0228` confirmed unused anywhere in the repo (committed history
   and current working tree) before naming these files.

**Not performed**: a live pre-flight row-count check against production, unlike
`air_0221`'s IMPACT note — not applicable here, since this migration creates only new
empty objects and touches zero existing tables, so there is no "does this table already
have data that could conflict" question to answer. **Not performed**: an actual
`BEGIN; ... ROLLBACK;` dry-run inside a real Postgres session (no `psql`/staging database
available in this environment, only production). The `_APPLY.sql` wrapper's own built-in
`BEGIN`/verify/`COMMIT` structure is the mitigation for this, exactly as it was for
`air_0221` Stage 1.

## What Stage 2 needs to do next

Per `docs/CHATGPT_PLUS_VERIFICATION_SPEC.md` §9, now unblocked by this foundation:

1. Resolve the open architecture BLOCKER in `docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md`
   §1 (approval/scoring logic location — auth-web vs desktop) if not already decided.
2. Build the auth-web user-facing API (§5.1): submit (multipart upload + SHA-256/MIME
   validation + Gemini structured-output analysis + rule scoring), list/detail, resubmit,
   `/api/badges/me`.
3. Nothing in Stage 1 needs to change for Stage 2 to start — every table/column/bucket
   this stage introduces was designed directly from the SPEC's Stage 2+ requirements, not
   guessed at.
