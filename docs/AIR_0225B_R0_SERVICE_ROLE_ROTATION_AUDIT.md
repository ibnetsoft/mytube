# AIR-0225B-R0 — SUPABASE_SERVICE_ROLE_KEY Rotation Audit

Date: 2026-07-12 (updated 2026-07-13)
Status: **BLOCKED — SUPABASE OWNER ACTION REQUIRED** (legacy key revocation
still pending; see §4 for the split status)

This document records variable names, usage locations, and existence/absence
states only. **No key value, partial value, or fingerprint of any key is
recorded anywhere in this document or in this session's outputs.**

## 1. Exposure incident scope (reference)

`SUPABASE_SERVICE_ROLE_KEY` was bundled in plaintext (`app/.env`) into the
desktop build and shipped in 19 public GitHub releases (v2.0.8–v2.3.5) until
2026-07-11. Full original investigation: `worknote/AIR-0225B-stage0-service-role-removal-investigation.md`
and `worknote/AIR-0225B-affected-release-inventory.md` (prior session,
2026-07-11).

## 2. Already-completed remediation (confirmed this session)

- GitHub Actions Secret `SUPABASE_SERVICE_ROLE_KEY` no longer exists on
  either `ibnetsoft/mytube` or `ibnetsoft/AIR-releases` (`gh secret list`,
  this session).
- `.github/workflows/windows-release.yml`, `tools/build_windows.ps1`, and
  `packaging/windows/AIRStudio.spec` only contain **comments** warning this
  key must never be written into a desktop build — no live reference that
  would inject it, confirmed by direct file inspection.
- `tools/scan_release_secrets.ps1` exists as a standing safeguard: it fails
  a release build if a `service_role`-shaped JWT or the literal string
  `SUPABASE_SERVICE_ROLE_KEY=` is found anywhere in the staged build output.
- The affected release **assets** (not the key itself) were already deleted
  per the prior investigation's inventory.
- **What remains unconfirmed by any of the above**: whether the actual key
  *value* in Supabase was ever rotated. None of the above remediations
  touch the Supabase project itself.

## 3. service_role dependency inventory (names/paths only, no values)

### Category A — production runtime required

| Location | Usage |
|---|---|
| `auth-web/lib/supabaseAdmin.ts` | Central privileged Supabase client for auth-web (Vercel production). `requireEnv('SUPABASE_SERVICE_ROLE_KEY')` — fails fast at cold start if unset. Imported by many `admin/*` routes. |
| ~35 files under `auth-web/app/api/admin/**/route.ts`, plus `auth-web/app/api/referrals/route.ts`, `auth-web/app/api/publishing/presigned-url/route.ts`, `auth-web/app/api/desktop-login/route.ts`, `auth-web/app/api/desktop-change-password/route.ts` | Each reads `process.env.SUPABASE_SERVICE_ROLE_KEY!` directly to build its own Supabase client (does not go through `supabaseAdmin.ts`). Covers withdrawals, settlements/payout, user management/ban/role, render-queue, referrals, categories, learning, style-presets, tenants, voices, topics-queue, publishing, and more. |
| `services/render_queue_worker.py`, `services/remote_drive_render_service.py`, `remote_drive_worker.py` | Legacy/current remote render-worker components. Read `SUPABASE_SERVICE_ROLE_KEY` from local environment; **raise `RuntimeError` if absent** (hard dependency, not a silent no-op). Deployment location (which operator machine(s) run these) is outside this session's visibility. |

**Rotation impact**: any rotation requires updating the Vercel Production
env var for `auth-web` **and** the environment of wherever the render-worker
process(es) above actually run, then redeploying/restarting both.

### Category E — unclear / separately flagged (higher severity than a simple usage note)

| Location | Usage |
|---|---|
| `services/web_admin_client.py` (`supabase_key` property, line 88) | Reads `SUPABASE_SERVICE_ROLE_KEY` from the **desktop app's own local environment** and, if present, calls Supabase's REST API directly with service_role privileges from the end-user's machine. Gated by `has_supabase()` — silently no-ops only when the var is absent. |
| `app/routers/auth.py` (`_supabase_headers()`, line 78-87) | Same pattern: reads the var locally on desktop, builds service_role headers for direct Supabase calls. |
| `app/routers/user_topics.py:43`, `app/routers/settings.py:553`, `services/dispatcher_service.py:86` | Same `os.getenv("SUPABASE_SERVICE_ROLE_KEY")` pattern, same desktop-side code. |

This is **not** currently exploitable in newly-built clients, because (per
§2) the build pipeline no longer injects this variable into desktop builds
— `has_supabase()` returns false and these paths no-op. But the code itself
is still live: it is exactly the mechanism that turned the original
`app/.env` leak into a working RLS-bypass credential rather than an inert
string. This is a design issue independent of rotation and is called out
under §9 (recommended next steps), not resolved here.

### Category B — deploy/migration only

| Location | Usage |
|---|---|
| `auth-web/run_migration.js` | One-off migration runner, operator-invoked locally against Supabase directly. |
| `scripts/backfill_topic_translations.py` | One-off backfill script, operator-invoked. |
| `migrations/air_0164a_worker_jobs.sql` | Comment only — documents that Postgres RLS is bypassed by `service_role` by design; not a code usage. |

### Category C — local admin tools / dev scripts only

`scratch/apply_supabase_schema.py`, `scratch/check_all_logs.py`,
`scratch/check_global_settings.py`, `scratch/check_logs.py`,
`scratch/check_remote_tables.py`, `scratch/insert_script_styles.py`,
`scratch/test_supabase.py`, `_dev/find_user.py` — ad hoc local
debug/dev-only scripts, not part of any deployed service.

`.env` on this session's local development machine currently has
`SUPABASE_SERVICE_ROLE_KEY` **set** (existence confirmed, value not read or
recorded) — local dev use only, not connected to production distribution.

### Category D — dead references (comments/docs only, no live code)

`.github/workflows/windows-release.yml`, `tools/build_windows.ps1`,
`packaging/windows/AIRStudio.spec` (comments only, see §2);
`worknote/AIR-0225-*`, `worknote/AIR-0225B-*`, `docs/AIR_WORKER_SECURITY.md`,
`docs/HERMES_TOPIC_INTELLIGENCE_*`, `docs/CHATGPT_PLUS_VERIFICATION_*`,
`docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md`, `project_status/*` — documentation
only, no executable reference.

`.env.remote-worker.example` and root `.env.example` — templates only
(`.env.remote-worker.example` documents the variable the render-worker
requires per Category A above; root `.env.example` does not list this
variable at all).

The AIR Worker (new central-server architecture, PR #70/#71/#72, still
Draft/unmerged) was checked on its source branch
(`origin/feat/air-0227c-worker-secure-remote-integration`) — it does **not**
reference `SUPABASE_SERVICE_ROLE_KEY` anywhere; it authenticates against
auth-web's Worker API using its own worker-token mechanism instead. Not a
dependency.

No Supabase Edge Functions directory exists in this repository.

## 4. Actual rotation status

**Split status, confirmed 2026-07-13 by the Supabase project owner directly
viewing the dashboard (status only relayed to this session — no key value,
partial value, or screenshot content was shared or recorded):**

| Item | Status |
|---|---|
| JWT Signing Key (new asymmetric ECC P-256 system) rotation | **ROTATED_CONFIRMED** — current key is ECC(P-256), previous ECC key shown as "rotated a day ago" in Supabase Dashboard → Project Settings → API → JWT Signing Keys |
| Legacy `service_role` API key (Settings → API Keys → Legacy anon, service_role API keys) | **NOT CONFIRMED / STILL ENABLED** — the legacy key toggle remains ON; the "Disable JWT-based API keys" action exists but has **not** been taken |
| Production modification performed this round | **NONE** |

**This does not mean the original leaked key is now invalid — treat it as
still live until the legacy toggle is disabled.** Supabase's legacy
anon/service_role keys are HS256 JWTs signed by a separate legacy JWT
secret, independent of the new asymmetric JWT Signing Keys system. Rotating
the new ECC signing key does **not** invalidate the legacy secret or any
key derived from it — that only happens when "Disable JWT-based API keys"
is explicitly clicked. Until that action is taken, the `service_role` key
that was exposed in 19 public releases (§1) must be assumed to still be a
valid, usable credential. This session did **not** click that button, per
explicit instruction, and does not recommend clicking it yet — see §9 for
why (broad production dependency on the legacy key format, not yet
migrated to the new `sb_secret_*`/`sb_publishable_*` formats).

Before this update, this session had no Supabase dashboard access, no
Supabase Management API token, and no Supabase CLI session. A Vercel CLI
session authenticated as the project owner (`abakorea-9330`) was found to
be linked to the `mytube` production project, which could in principle
list *env var names* — this was **not exercised**: the sandbox's own
safety layer blocked the `vercel env ls production` call as a live
production-environment read outside the scope explicitly authorized
("조사" via source code, not a live query against production), and this
session did not attempt to route around that block.

**Recommended dashboard procedure for the Supabase project owner (superseded by the confirmation above, retained for reference):**
1. Open Supabase Dashboard → Project Settings → API.
2. Under "Project API keys," check the `service_role` key's shown
   creation/last-rotated date.
3. If that date is **before** 2026-07-11 (when this incident's GitHub-side
   remediation happened), the key has almost certainly **not** been
   rotated since the exposure — treat as `NOT_ROTATED_CONFIRMED` and
   proceed per §6 below.
4. If the date is on/after 2026-07-11, treat as `ROTATED_CONFIRMED`, but
   still re-run the Category A dependency list in §3 to confirm every
   production consumer (Vercel `auth-web`, and every render-worker host)
   was updated to the new value at that time — a rotated-but-not-redeployed
   key is a production outage waiting to happen, not a completed rotation.

## 5. global_settings system key presence (separately requested, not deleted this session)

**UNABLE_TO_VERIFY** for all 6 — this session has no Supabase database
access (no service_role key of its own, no dashboard, no MCP database
tool). Values were not guessed.

| Key | Status |
|---|---|
| `sys_api_gemini` | UNABLE_TO_VERIFY |
| `sys_api_youtube` | UNABLE_TO_VERIFY |
| `sys_api_elevenlabs` | UNABLE_TO_VERIFY |
| `sys_api_topview` | UNABLE_TO_VERIFY |
| `sys_api_topview_uid` | UNABLE_TO_VERIFY |
| `sys_api_claude` | UNABLE_TO_VERIFY |

No system key was deleted. Stage 9 execution remains gated on separate CTO
approval per the existing plan in `docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md`.

## 6. If NOT_ROTATED_CONFIRMED — pre-rotation impact plan (prepared, not executed)

Based on the §3 inventory, if the Supabase project owner confirms the key
has never been rotated, rotation will require, in this order:

1. **Confirm no other production consumer exists beyond §3** — the owner
   should grep their own deployment infra (this session cannot see
   anything beyond this git repository) for any additional service using
   this key, e.g. a hosted render-worker fleet not represented in this repo.
2. **Generate the new key in Supabase** (does not itself break anything —
   old key stays valid until the rotate/revoke step is confirmed by
   Supabase's own UI flow).
3. **Update Vercel Production env var** `SUPABASE_SERVICE_ROLE_KEY` for the
   `mytube` project, then trigger a redeploy (env var changes do not apply
   to already-running Vercel functions).
4. **Update every render-worker host's environment** (wherever
   `services/render_queue_worker.py` / `remote_drive_worker.py` /
   `services/remote_drive_render_service.py` actually run — unknown to this
   session, must be identified by the team) and restart those processes.
5. **Only then** revoke/invalidate the old key value in Supabase.
6. Run the smoke tests in §7.

**Expected impact if step 3/4 is missed**: every `auth-web` admin route and
every render-worker process will start failing Supabase auth
(401/expired-key errors) the moment the old key is revoked — i.e., an
outage across admin functions and the render pipeline, not a security
failure. This is why dependency confirmation must happen before revocation,
not after.

**Rollback**: keep the old key active (do not revoke) until steps 3–4 are
confirmed working via the smoke tests in §7; if something fails, no
rollback action is needed beyond leaving the old key valid and retrying the
redeploy.

## 7. Smoke tests

**Not executed — no rotation was performed this session (blocked before
reaching this step).** Listed here as the checklist to run once a rotation
is actually carried out:

- [ ] NOT TESTED — 회원가입 (registration)
- [ ] NOT TESTED — 로그인 (login)
- [ ] NOT TESTED — `/api/verify`
- [ ] NOT TESTED — 데스크톱 세션 생성/재동기화 (desktop-login / desktop-resync)
- [ ] NOT TESTED — 관리자 인증 (admin auth)
- [ ] NOT TESTED — 추천인 대시보드 조회 (referral dashboard)
- [ ] NOT TESTED — 출금 관리자 API 인증 구간 (withdrawal admin API auth)
- [ ] NOT TESTED — 필요한 Supabase 서버 조회/수정
- [ ] NOT TESTED — 일반 사용자 토큰으로 관리자 권한 접근 차단 확인
- [ ] NOT TESTED — 무토큰 요청에서 민감 필드 비노출 확인 (already covered
      structurally by AIR-0227F-0/0B's `/api/verify` fix, but not re-run as
      part of a rotation smoke test this session)

This session has no real or test Supabase account/credentials to exercise
any of the above; explicitly not claimed as passing.

## 8. Next recommended action

1. Supabase project owner performs the dashboard check in §4.
2. If `NOT_ROTATED_CONFIRMED`: owner (or a session with dashboard access)
   confirms the full consumer list in §3 Category A against real deployment
   infra, then executes §6 in order, then runs §7.
3. Independently of rotation timing: the Category E desktop-side
   direct-service_role code paths (`services/web_admin_client.py`,
   `app/routers/auth.py`, `app/routers/user_topics.py`,
   `app/routers/settings.py`, `services/dispatcher_service.py`) should be
   considered for removal in a follow-up task — they are currently inert
   only because the build pipeline no longer feeds them a value, which is
   an operational safeguard, not a code-level guarantee.
4. `global_settings.sys_api_*` presence (§5) and Stage 9 deletion remain
   separately gated on CTO approval, unchanged from
   `docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md`.
5. See §9 below for the legacy-key-deactivation readiness pre-check
   (code/config audit only, no production changes, no key disabled).

## 9. Legacy anon/service_role deactivation pre-check (2026-07-13, audit only)

Scope: source code and deployment **config files** in this repository only.
No live Vercel/Supabase environment was queried for this section (per the
same scope boundary as §4). No key was disabled. No production setting was
changed.

### 9.1 Which Supabase key types does production auth-web use?

Both legacy key types, exclusively — no trace of the new `sb_publishable_*`
/ `sb_secret_*` format anywhere in this codebase (checked via repo-wide
search; the only incidental match was an unrelated third-party library
docstring example under `venv_old/`, not project code):

- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — legacy anon key
- `SUPABASE_SERVICE_ROLE_KEY` — legacy service_role key

### 9.2 `NEXT_PUBLIC_SUPABASE_ANON_KEY` usage

Used in exactly 3 places, all in `auth-web`, all as a plain opaque string
passed straight into `@supabase/supabase-js`'s `createClient(url, key)` —
no decoding, no JWT-shape parsing, no format-specific assumption anywhere:

- `auth-web/lib/supabaseClient.ts` — general client-side/shared client
- `auth-web/app/api/admin/_auth.ts` — `getRequester()`/`requireAdmin()`/
  `requireSuperAdmin()`: builds a throwaway client with the anon key purely
  to call `auth.getUser(token)` against the caller's own Bearer token (the
  user's session JWT, not the anon key itself, is what's being verified —
  this path is unaffected by the anon/service_role key format and would
  keep working correctly through the JWT Signing Key rotation already
  confirmed in §4)
- `auth-web/app/api/referrals/route.ts` — same anon-key-plus-user-token
  pattern

The Python desktop backend does **not** use the anon key path at all
(confirmed both in this audit and in the prior
`worknote/AIR-0225B-stage0-service-role-removal-investigation.md`
investigation) — it exclusively uses `SUPABASE_SERVICE_ROLE_KEY` (§9.3).

### 9.3 `SUPABASE_SERVICE_ROLE_KEY` usage

Unchanged from the full inventory already recorded in §3 Category A/E of
this document: `auth-web/lib/supabaseAdmin.ts` (central client) plus ~35
individual `auth-web/app/api/**/route.ts` files that read
`process.env.SUPABASE_SERVICE_ROLE_KEY!` directly, plus the legacy remote
render-worker components (`services/render_queue_worker.py`,
`services/remote_drive_render_service.py`, `remote_drive_worker.py`, which
raise `RuntimeError` if the value is absent), plus the Category E
desktop-side paths already flagged for removal in §8 item 3.

### 9.4 Readiness to replace the anon key with a new `sb_publishable_*` key

**Code-ready, deployment not yet done.** Every usage site (§9.2) treats the
anon key as an opaque string handed directly to `createClient()` — Supabase
designed the new `sb_publishable_*` format as a drop-in value replacement
for this exact parameter, so swapping the `NEXT_PUBLIC_SUPABASE_ANON_KEY`
environment variable's **value** (not its name — no code change needed)
should work without touching any of the 3 files above. This has not been
verified against a real `sb_publishable_*` value (none available to this
session), so treat as "expected to work by design," not "tested."

### 9.5 Readiness to replace server admin usage with a new `sb_secret_*` key

**Code-ready in the same sense, but operationally large.** Same conclusion
as §9.4 — every `SUPABASE_SERVICE_ROLE_KEY` usage site is a plain string
passed to `createClient()` or used as a raw `Authorization`/`apikey` header
value, with no HS256/JWT-shape assumption found anywhere (confirmed: no
custom JWT verification code exists in this repository at all — see §9.6).
So no source code change is required to accept a `sb_secret_*` value. What
makes this operationally large is scale, not code compatibility: ~35+
independent literal env var reads in `auth-web` alone, plus however many
separate hosts run the legacy render-worker scripts (§9.3, location unknown
to this session) — every one of those processes needs the new value and a
restart before the legacy key can be safely disabled.

### 9.6 Edge Functions / custom JWT verification depending on legacy HS256

**None found.** This repository has no `supabase/functions/` directory and
no Supabase Edge Functions of any kind. No custom JWT decode/verify code
(no `jwt.verify`, `jsonwebtoken`, `jose`, `HS256`, or hand-rolled JWT
parsing) exists anywhere in the codebase — all Supabase Auth token
verification goes through the official `@supabase/supabase-js` /
`supabase-py` client libraries (`auth.getUser(token)`,
`auth.admin.getUserById()`), which already use whatever signing key
Supabase's own backend considers current. This means the JWT Signing Key
rotation confirmed in §4 has no code-level compatibility risk — but it also
means, as stated in §4, that this rotation is orthogonal to the legacy
anon/service_role key toggle and did not affect it.

### 9.7 What breaks if the legacy keys are disabled right now (before migration)

Effectively all of `auth-web`'s server-side functionality, plus the legacy
render-worker pipeline:

- Every `admin/*` route (`supabaseAdmin.ts` fails fast at cold start per
  its own `requireEnv()` guard — see §3), including user management, bans,
  settlements/payout, withdrawals, render-queue, referrals administration,
  categories, learning, style-presets, tenants, voices, topics-queue,
  publishing
- `desktop-login` / `desktop-change-password` (both use
  `SUPABASE_SERVICE_ROLE_KEY` directly)
- The anon-key-based admin auth check itself (`_auth.ts`) would keep
  working for *identity verification*, but every route it protects still
  needs the service_role client afterward, so the net effect is the same
  outage
- `services/render_queue_worker.py`, `services/remote_drive_render_service.py`,
  `remote_drive_worker.py` — hard `RuntimeError` on next poll cycle if these
  processes are still running against the old legacy key
- Any operator running `auth-web/run_migration.js` or
  `scripts/backfill_topic_translations.py` against production

In short: disabling the legacy toggle without first rolling out new
`sb_publishable_*`/`sb_secret_*` values everywhere above would be a
full outage of the admin backend and the render pipeline, not a
security-only action. This is exactly why §9.8's order matters.

### 9.8 Replacement order / rollback / smoke test plan (prepared, not executed)

**Order:**
1. Supabase owner generates the new `sb_publishable_*` (replaces anon) and
   `sb_secret_*` (replaces service_role) keys from the dashboard. This does
   not disable anything yet — legacy keys keep working in parallel.
2. Update the Vercel Production environment variables for `auth-web`
   (`NEXT_PUBLIC_SUPABASE_ANON_KEY` → new `sb_publishable_*` value,
   `SUPABASE_SERVICE_ROLE_KEY` → new `sb_secret_*` value; variable **names**
   stay the same, only values change, per §9.4/§9.5) and redeploy.
3. Update every legacy render-worker host's environment (§9.3 — hosts
   unknown to this session, must be identified by the team) and restart
   those processes.
4. Run the full smoke-test list below against production with the new
   values in place, while the legacy keys are still technically enabled
   (so there is a safety net if something fails).
5. Only after all smoke tests pass: Supabase owner clicks "Disable
   JWT-based API keys."
6. Re-run the smoke-test list once more immediately after disabling, to
   catch anything that silently still depended on the legacy key format
   despite step 4 passing (e.g., a cached client, a process that wasn't
   actually restarted in step 3).

**Rollback:** do not disable the legacy keys until step 4 passes. If step 2
or 3 fails, no rollback action is needed — the legacy keys remain valid and
production keeps running on them; simply fix and retry. If step 5 has
already happened and step 6 uncovers a failure, the legacy toggle cannot be
un-disabled by this team (Supabase-side deprecation flow) — this is exactly
why step 4 (parallel-operation smoke test before disabling) is the actual
safety gate, not step 6.

**Smoke tests (same checklist as §7, re-listed for this specific
migration):** registration, login, `/api/verify`, desktop session
creation/resync, admin auth, referral dashboard, withdrawal admin API auth,
general Supabase server read/write, non-admin token blocked from admin
routes, token-less request doesn't leak sensitive fields — plus,
specific to this migration: confirm anon-key-based public reads succeed
with the new `sb_publishable_*` value, and confirm service_role-based
admin writes succeed with the new `sb_secret_*` value.

**Not executed this round** — this is a prepared plan only, pending CTO
approval to actually provision and roll out the new keys.
