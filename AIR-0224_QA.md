# AIR-0224 — QA

**Status: static verification only. Nothing in this ticket has been executed against production yet** — see `REFERRAL_E2E_TEST_PLAN.md` §7 for what needs explicit sign-off before running (test-account creation via the Admin API touches `auth.users`, a shared system; Scenario 3 requires a temporary write to a live `global_settings` value affecting real signups). This document will be updated with real PASS/FAIL results once execution is authorized and run.

## 1. Static verification performed

- **SQL syntax**: `REFERRAL_TEST_FIXTURE.sql` and `REFERRAL_VALIDATE.sql` both parsed cleanly with `pglast` (real PostgreSQL grammar, `libpg_query`) — 12 and 1 top-level statements respectively (the commented-out gated blocks, by design, aren't parsed as active statements — they're meant to be uncommented and run as their own separate step).
- **Shell syntax**: `REFERRAL_TEST_ACCOUNTS.sh` passed `bash -n` (syntax-only dry run, no execution).
- **Schema cross-check**: every column referenced in the fixture (`referral_commissions.commission_level`/`source_job_id`, `referral_withdrawals.*`, `referral_audit_logs.*`) was checked against the actual Stage 1 migration and live PostgREST schema introspection performed earlier this project — not assumed from `auth-web/supabase_schema.sql` alone, which has already been shown this session to drift from what's actually deployed.
- **`bigint` finding**: confirmed live via PostgREST (`{"format": "bigint", "type": "integer"}` for both `commission_tokens` and `base_tokens`), not just inferred from the schema file — this directly shaped the fixture's rounding approach (see `REFERRAL_E2E_TEST_PLAN.md` §3) and is a real finding for the future Settlement Engine Specification, not a fixture-only concern.
- **Math cross-check**: every literal value inserted in `REFERRAL_TEST_FIXTURE.sql` Part B was independently re-derived against `REFERRAL_EXPECTED_RESULTS.md`'s worked table by hand (ROUND-half-away-from-zero applied to each job/rate pair) — no discrepancies found.
- **Cascade-delete review**: read the actual FK definitions (not assumed) for all three Stage 1/2 tables — `referral_commissions.beneficiary_id` and `referral_withdrawals.user_id` are `ON DELETE CASCADE` from `profiles`, but `referral_audit_logs.actor_id` is `ON DELETE SET NULL` and `entity_id` has no FK at all. This is why the teardown instructions explicitly delete `referral_audit_logs` rows by metadata tag *before* relying on cascade for the other two tables — an error caught during design, not left as a landmine in the teardown script.

## 2. What is NOT yet verified (honest gap — requires live execution)

- Whether the Supabase Admin API call in `REFERRAL_TEST_ACCOUNTS.sh` actually produces the expected `referred_by` chain via the live `on_auth_user_created` trigger — the trigger's behavior was confirmed by reading its use in AIR-0122 (already-merged, "E2E flow verified" per that ticket's own worknote) but not re-exercised here.
- Whether `REFERRAL_TEST_FIXTURE.sql`'s `DO` block assertions (Parts A/B/C) actually pass against real inserted data — they're written to fail loudly (`RAISE EXCEPTION`) if anything is wrong, but that's only meaningful once actually run.
- Scenario 3 (Default Sponsor) and Scenario 5 (idempotency detection) — both intentionally left as commented-out, separately-gated blocks, not run.
- AIR-0223's dashboard against real (non-empty) data — `AIR-0223_AUTH_QA_CHECKLIST.md`'s results reported "No data found." everywhere, since `referral_mode` was OFF and the DB was empty at that time. This fixture is what would finally let that checklist be re-run meaningfully.

## 3. PASS/FAIL — pending execution

| # | Criterion | Status |
|---|---|---|
| 1 | 추천가입 (Scenario 1/3 signup attribution) | PENDING execution |
| 2 | Level 1 | PENDING execution |
| 3 | Level 2 | PENDING execution |
| 4 | Default Sponsor | PENDING execution (Scenario 3, gated separately) |
| 5 | 추천수당 (commission generation, simulated) | Statically verified (math + schema), PENDING live insert confirmation |
| 6 | 출금 (withdrawal request → approval) | Statically verified (logic matches Stage 2's real code paths), PENDING live execution |
| 7 | Audit | Statically verified (expected row counts/shapes derived), PENDING live execution |
| 8 | Dashboard | PENDING — requires fixture data to exist first (AIR-0223's UI already independently smoke-tested clean against empty data, per `AIR-0223_QA.md`) |
| 9 | Idempotency | PENDING execution (Scenario 5, gated separately, self-reverting) |
| 10 | Regression | N/A yet — this ticket adds no application code, only SQL/shell fixture scripts and markdown docs; `git diff --stat` confirms zero existing files modified |

## 4. Regression check (the one thing fully verifiable right now)

`git status`/`git diff --stat` confirm **zero existing files modified** by AIR-0224 — every artifact (`REFERRAL_E2E_TEST_PLAN.md`, `REFERRAL_TEST_FIXTURE.sql`, `REFERRAL_TEST_ACCOUNTS.sh`, `REFERRAL_EXPECTED_RESULTS.md`, `REFERRAL_VALIDATE.sql`, this file) is new. No application code, migration, or previously-delivered AIR-0221/0223 file was touched.

## 5. Phase 1 execution result (2026-07-09) — test account creation

**Approved scope**: `REFERRAL_TEST_ACCOUNTS.sh` only (4 test accounts). Not run: any `global_settings` change, Scenario 3, `referral_mode` change.

### Accounts created

| Account | `auth.users` / `profiles` id | Email | `referral_code` | `country_code` |
|---|---|---|---|---|
| Default Sponsor | `d0ea9b48-da62-42ed-93d8-267e4b1c8706` | `e2e-default-sponsor@airqa.test` | `14A17C05` | KR |
| User A | `5c83dafa-9bd4-4457-a22b-12c271df2f1e` | `e2e-user-a@airqa.test` | `47E948C0` | KR |
| User B | `86ce9fb5-72fe-456a-a4ac-0cb7bb68a31b` | `e2e-user-b@airqa.test` | `2EE04523` | KR |
| User C | `f3a8303c-460a-47b3-a793-49abbd0be686` | `e2e-user-c@airqa.test` | `F4559E90` | KR |

Row count: 4 `auth.users` rows, 4 `profiles` rows (1:1, auto-created by the `on_auth_user_created` trigger). Verified read-only via `GET /rest/v1/profiles?email=in.(...)`.

### ⚠ Two problems found — fixture is NOT in the expected state

**1. `referred_by` is `NULL` on all 4 profiles — the referral chain was never established.**
Verified: `user_metadata.referred_by_id` was correctly sent and correctly stored on `auth.users` (confirmed via `GET /auth/v1/admin/users/{id}`, e.g. User A's `user_metadata` shows `"referred_by_id":"d0ea9b48-da62-42ed-93d8-267e4b1c8706"` — the real Default Sponsor id, correct). But `public.handle_new_user()` (the `AFTER INSERT ON auth.users` trigger that's supposed to read that field and set `profiles.referred_by`) did not do so. The version of this function in `auth-web/supabase_schema.sql` (read before writing the fixture) correctly parses `raw_user_meta_data->>'referred_by_id'` and sets `referred_by` — but this project has repeatedly shown that file drifts from what's actually deployed (e.g. `profiles.is_superadmin` documented but absent live, `migration_withdrawal_commission.sql` apparently never applied). The strong working hypothesis, not yet confirmed (would need SQL Editor / `pg_proc` access this environment doesn't have): **the live `handle_new_user()` trigger is an older version that doesn't implement the `referred_by_id` fallback AIR-0122 documented adding.**

**2. Any `UPDATE` to `profiles` fails with `42703 record "new" has no field "referrer_id"`.**
Attempting to set `referral_code`/`country_code` via `PATCH /rest/v1/profiles` (fields unrelated to any "referrer") failed with this error on all 4 rows — meaning some trigger fires on **any** `profiles` UPDATE and unconditionally references a `referrer_id` field that doesn't exist on the `profiles` row type. This matches the exact `referrer_id`-vs-`referred_by` bug pattern documented extensively in `CONSOLIDATION_PLAN.md` §0/§1 for the orphaned Gen 2/3 RPC stack — most likely a leftover Gen 2/3 `BEFORE UPDATE` trigger (e.g. something in the `handle_referral_join`/`handle_commission_earned` family) that was never actually cleaned up and fires unconditionally regardless of `referral_mode` or which columns changed. **This means `UPDATE`s to `profiles` are currently broken in production for any caller, not just this fixture** — a real, live bug, independent of AIR-0224.

**Neither of these was caused by this ticket's scripts** — `REFERRAL_TEST_ACCOUNTS.sh` sent exactly what it should have; the failure is in pre-existing, already-deployed database trigger(s). `REFERRAL_TEST_FIXTURE.sql` Part A's sanity-check `DO` block (designed specifically to catch exactly this class of problem before any commission data gets inserted) would correctly `RAISE EXCEPTION` and refuse to proceed if run against this state right now — the defensive design worked as intended.

### Row count summary
- `auth.users`: 4 created (all `.test` domain, all `email_confirm=true`)
- `profiles`: 4 auto-created (1:1)
- `referred_by` populated: **0 of 4** (expected 3 — A→DS, B→A, C→B)
- `referral_commissions`/`referral_withdrawals`/`referral_audit_logs`: 0 (Part B/C not run — blocked on the above)

### Cleanup procedure (if teardown is wanted now, before further work)
```bash
SUPABASE_URL=...; SUPABASE_KEY=...  # from .env, as in REFERRAL_TEST_ACCOUNTS.sh
for ID in d0ea9b48-da62-42ed-93d8-267e4b1c8706 5c83dafa-9bd4-4457-a22b-12c271df2f1e \
          86ce9fb5-72fe-456a-a4ac-0cb7bb68a31b f3a8303c-460a-47b3-a793-49abbd0be686; do
  curl -s -X DELETE "${SUPABASE_URL}/auth/v1/admin/users/$ID" \
    -H "apikey: ${SUPABASE_KEY}" -H "Authorization: Bearer ${SUPABASE_KEY}"
done
```
`profiles` cascade-deletes automatically (`ON DELETE CASCADE`). No `referral_commissions`/`referral_withdrawals`/`referral_audit_logs` rows exist yet, so there's nothing else to clean up. **Recommend NOT tearing down yet** — these 4 accounts are otherwise valid and reusable once the trigger issue is triaged; deleting and recreating them gains nothing if the same trigger bug is still live.

### Recommendation before proceeding to Scenario 1/2/4/5
This needs a decision, not just a retry: (a) triage/fix the two trigger issues via SQL Editor (separate ticket — this is a DB/code change outside AIR-0224's scope), then re-run cleanly, or (b) work around them within AIR-0224's scope — e.g. skip relying on `handle_new_user()`/any `profiles` UPDATE entirely and set `referred_by`/`referral_code`/`country_code` via a **single `auth.users` metadata-driven path only if a working one can be found**, or accept `referred_by=NULL` isn't fixable without a DB write this ticket doesn't cover. Given the trigger bugs are real production defects (not fixture-specific), I'd recommend (a) — flagging to CTO as its own priority rather than working around it silently inside a test-fixture ticket.

## Next step

Paused pending direction on the above. Not proceeding to Scenario 1/2/4/5 (per the approval's own sequencing) since the fixture's foundational referral chain isn't actually in place yet.
