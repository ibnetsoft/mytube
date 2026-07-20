# AIR-0221C — Apply Checklist

Migration: `air_0221c_referral_audit_action_sending.sql`
Rollback: `air_0221c_referral_audit_action_sending_rollback.sql`

Scope: **one CHECK constraint on one column of one table** (`referral_audit_logs.action`). No other table touched, no application code, no Stage 2 dual-write.

## Current CHECK constraint (before this migration)

Set by Stage 1 (`air_0221_referral_stage1_foundation.sql`), applied to production 2026-07-09:

```sql
CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'completed', 'reversed'))
```

## New CHECK constraint (after this migration)

```sql
CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'sending', 'completed', 'reversed'))
```

Only change: `'sending'` added. Every previously-valid value stays valid — this is a pure widening, not a breaking change to the constraint (nothing that satisfied the old constraint could ever fail the new one).

## Pre-flight

`referral_audit_logs` has 0 rows in production as of AIR-0221C authoring (unchanged since Stage 1 apply — Stage 2 dual-write, the only thing that would ever write to this table, has not been implemented). Confirmed via the same read-only PostgREST method used throughout AIR-0221:

```
GET /rest/v1/referral_audit_logs?select=id&limit=1  with Prefer: count=exact
-> Content-Range: */0
```

Because the table is empty, `VALIDATE CONSTRAINT` cannot fail regardless — there are no rows to violate it. The `NOT VALID` + `VALIDATE CONSTRAINT` pattern is still used, matching Stage 1's style, so this migration remains safe to re-apply later if rows exist by then.

## How to apply (Supabase Dashboard SQL Editor)

Single-paste, single-run, self-verifying — same pattern as the Stage 1 `_APPLY.sql`:

```sql
BEGIN;

ALTER TABLE public.referral_audit_logs
    DROP CONSTRAINT IF EXISTS referral_audit_logs_action_check;

ALTER TABLE public.referral_audit_logs
    ADD CONSTRAINT referral_audit_logs_action_check
    CHECK (action IN ('generated', 'requested', 'approved', 'rejected', 'sending', 'completed', 'reversed'))
    NOT VALID;

ALTER TABLE public.referral_audit_logs
    VALIDATE CONSTRAINT referral_audit_logs_action_check;

COMMENT ON COLUMN public.referral_audit_logs.action IS
    'AIR-0221C: allowed values are generated | requested | approved | rejected | sending | completed | reversed. ''sending'' added to match referral_withdrawals.status''s SENDING state (Stage 1) — originally missing from the Stage-1-authored CHECK constraint, found during Stage 2 dual-write planning before any Stage 2 code was written.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.referral_audit_logs'::regclass
          AND conname = 'referral_audit_logs_action_check'
          AND convalidated = true
          AND pg_get_constraintdef(oid) LIKE '%''sending''%'
    ) THEN
        RAISE EXCEPTION 'AIR-0221C check FAILED: referral_audit_logs_action_check missing, not validated, or does not include sending';
    END IF;
    RAISE NOTICE 'AIR-0221C: verification passed — sending is now an allowed action value.';
END $$;

COMMIT;
```

If the `DO` block's assertion fails, it raises an exception, aborting the transaction — the trailing `COMMIT` then becomes a no-op rollback automatically (same mechanism as the Stage 1 apply script). A clean "Success" with the `AIR-0221C: verification passed` notice and no red error means it applied and committed correctly.

## Post-apply verification (read-only, from outside the DB session too)

Since `pg_constraint` isn't reachable via the PostgREST REST API (confirmed during Stage 1), the DO-block assertion above is the primary verification, run inside the same transaction as the change. As external corroboration, a functional check is also possible: attempt an insert with `action = 'sending'` and a bogus non-existent `entity_id`/`entity_type` combination that would be rejected for an unrelated reason (e.g. missing a required FK target) — if the *response* is no longer a CHECK-constraint violation naming `action`, that confirms `'sending'` is accepted. This wasn't necessary to run for this change given the DO-block assertion already validates the exact constraint definition server-side.

## Rollback conditions

Run `air_0221c_referral_audit_action_sending_rollback.sql` if the migration needs to be undone before Stage 2 implementation starts using `'sending'`. **Do not** run it if any `referral_audit_logs` row already has `action = 'sending'` — the rollback's own `VALIDATE CONSTRAINT` step will fail loudly in that case (by design, not a bug) rather than silently orphaning those rows. Check first:

```sql
SELECT count(*) FROM public.referral_audit_logs WHERE action = 'sending';
```
