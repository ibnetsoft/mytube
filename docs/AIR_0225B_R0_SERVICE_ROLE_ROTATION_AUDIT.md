# AIR-0225B-R0 — SUPABASE_SERVICE_ROLE_KEY Rotation Audit

Date: 2026-07-12
Status: **BLOCKED — SUPABASE OWNER ACTION REQUIRED**

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

**UNABLE_TO_VERIFY.**

This session has no Supabase dashboard access, no Supabase Management API
token, and no Supabase CLI session. A Vercel CLI session authenticated as
the project owner (`abakorea-9330`) was found to be linked to the `mytube`
production project, which could in principle list *env var names* — this
was **not exercised**: the sandbox's own safety layer blocked the
`vercel env ls production` call as a live production-environment read
outside the scope explicitly authorized ("조사" via source code, not a live
query against production), and this session did not attempt to route
around that block. Confirming actual rotation would additionally require
comparing the current key against the original exposed value, and the
original exposed value is not recoverable (the leaking release assets were
already deleted per §2) — so even with dashboard access, a direct
value-equality check is not possible; only "was the key regenerated after
[date]" is answerable from Supabase's own key-management UI (which shows
key creation/rotation timestamps without exposing the value), and that UI
is only visible to a Supabase project owner/admin.

**Recommended dashboard procedure for the Supabase project owner:**
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
