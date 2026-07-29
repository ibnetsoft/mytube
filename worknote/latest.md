# AIR-0227F-0D — v2.3.7 Rebuild + Asset Finalization (most recent)

**Date**: 2026-07-13
**Status**: DONE

- AIR-0227F-0B: DONE
- AIR-0227F-0C: DONE
- AIR-0227F-0D: DONE — v2.3.7 build 243 rebuilt from source this session
  (fresh PyInstaller build, `dist/AIRStudio/AIRStudio.exe` produced
  2026-07-13 07:43 local), staging (`release/staging/AIRStudio/app`)
  replaced from the new `dist/AIRStudio` output, `version.json`/
  `current.json` rewritten without BOM (`version=2.3.7`, `build=243`),
  rebuilt exe launch-tested (MainWindowTitle "AIR Studio", Responding=True,
  clean exit, no leftover process), portable ZIP rebuilt and its GitHub
  prerelease assets replaced in place via `gh release upload --clobber`
  (no new Release created, tag/prerelease status unchanged).
  - Final asset: `AIRStudio-2.3.7-win-x64.zip`, 456,147,733 bytes, SHA256
    `ff73df7a751578ee8c0a05c0aa6b4a89cddde00d8717755f6b643e0289dddc4a`.
  - 폐기된 이전 값 (AIR-0227F-0C 최초 빌드): 456,147,806 bytes /
    `4c6666877258f66d0fe3460b1d47e42e1015af1fc43a35028fd103fd4affdfc0`.
- 자동업데이트: DISABLED (v2.3.7 / build 243 remains a GitHub prerelease;
  `/releases/latest` reconfirmed as `v2.3.6` after the asset swap)
- 일반 사용자 배포: NOT APPROVED
- 실계정 E2E QA: PENDING (not performed, out of scope this session)
- Stage 8 (platform key rotation): USER KEY ROTATION COMPLETED
  (Gemini/YouTube/ElevenLabs/Claude; TopView excluded — no prior key) /
  RESIDUAL SECRET AUDIT PENDING (production `global_settings.sys_api_*` and
  Vercel env vars unconfirmed — no DB/dashboard access this session)
- Stage 9 (system key removal): NOT STARTED — see
  `docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md` for the per-key table and
  recommended order
- Production `global_settings` (`LATEST_APP_VERSION`/`LATEST_APP_URL`) was
  NOT modified.
- `SUPABASE_SERVICE_ROLE_KEY` rotation: PENDING — see
  `docs/AIR_0225B_R0_SERVICE_ROLE_ROTATION_AUDIT.md`
  (`UNABLE_TO_VERIFY` / BLOCKED, no Supabase dashboard/API access)
- Full detail: `docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md`,
  `docs/AIR_0225B_R0_SERVICE_ROLE_ROTATION_AUDIT.md`,
  `project_status/LATEST.md`

---

# Build 216 — First Real Installer Generated

**Date**: 2026-07-08
**Status**: DONE — artifacts in `release/`

## PRs Merged
- PR #67 (AIR-0214/0215) → main: 2026-07-08T02:21:07Z
- PR #68 (AIR-0216/0218) → main: 2026-07-08T02:21:39Z

## Build Results (Version 2.0.0, Build 216, Channel stable)

| Artifact | Size | SHA256 |
|----------|------|--------|
| AIRStudioSetup-2.0.0.exe | 344.08 MB | ae90a183601518321643b41d01f79a188c7a3c5cb9f58a79800914ce229c97f3 |
| AIRStudio-2.0.0-win-x64.zip | 448.11 MB | 8e73e310a7c907afa2c3467a6643baa14f53583c61c840dd7eeaefd3ffa85d12 |
| latest.json | 481 bytes | 462867622589c52729ec6abb34e2bb4f52e2752fdaca0221c7d09426ed478430 |

All `.sha256` sidecars present and verified. Build counter at 216 (committed to main).

## Merged in Locally From Referral 2.0 Branch (2026-07-03 work, merged 2026-07-08)
- Current understanding: AIR Studio is a local FastAPI application with a substantial worker-facing UI under `templates/`, plus a Next.js admin app under `auth-web`.
- Local main previously pointed at `c73ca016` — AIR-0123 remove fallback referral percentages — before this merge.

### PR #29 / AIR-0125 — Document Referral Migration Runbook (MERGED 2026-07-03)
- Created `REFERRAL_MIGRATION_RUNBOOK.md` to safely apply AIR-0122 ~ AIR-0124 DB changes to production.
- Documented execution steps, prerequisites, verification SQLs, and rollback strategies.

### PR #28 / AIR-0124 — Settlement Payout Processor (MERGED 2026-07-03)
- Implemented a DB RPC (`process_referral_payout`) for atomic manual payout processing.
- Ensured transaction safety: updates `pending` commission to `paid`, logs `paid_at`, and increments `usdt_balance` idempotently.
- Added `/api/admin/settlements/payout` superadmin API and "Approve & Pay" UI with confirmation logic.

### PR #27 / AIR-0123 — Referral Settlement Worker (Pending) (MERGED 2026-07-03)
- Implemented a background worker for generating referral commissions upon Admin Recharge.
- Generates `pending` status commissions up to Level 2 based on non-hardcoded global percentages.
- Enforces strict rounding logic (2 decimal places) and loop/self-referral prevention.
- Added `source_tx_id` + `commission_type` UNIQUE INDEX for database-level idempotency.
- Created `/admin/settlements` read-only dashboard.

### PR #26 / AIR-0122 — Referral Default Sponsor Foundation (MERGED 2026-07-03)
- Implemented foundation for Referral 2.0.
- Replaced optional referral code logic with strict validation and UUID-based Default Sponsor fallback.
- Added Next.js Admin UI for Referral Settings (`/admin/settings/referral`).
- Added DB migrations to seamlessly connect existing `referred_by IS NULL` users to the designated Default Sponsor.
- Added strict server-side API enum validation for `referral_mode` and `settlement_cycle`.

### AIR-0124/0125 — Referral Payout Processor + Migration Runbook (local, not yet in a PR)
- Manual referral payout processor translating `pending` commissions to `paid` and depositing into beneficiaries' `usdt_balance`.
- Migration runbook documented.
- Needs a PR opened against current main and re-verification against the Scene/Production Planner refactors that landed since.

### PR #25 / AIR-0121 — Image Workflow Guide (MERGED 2026-07-03)
- Added an explicit, 7-step Image Production Workflow UI in `image_gen.html` for better user onboarding.
- LocalStorage state persistence with hooks into API responses for auto-completion.
- 4 languages i18n support.

### AIR-0117 — Project status document sync (2026-07-02)
- Confirmed PR #11 (AIR-0112) MERGED into main on 2026-07-01.
- Discovered PRs #14–#17 merged without corresponding WORK_INDEX / LATEST entries.
- Updated WORK_INDEX, LATEST, NEXT_TASK, and worknote/latest to reflect actual GitHub state.
- Cleaned NEXT_TASK of completed items (PR #11 re-review, AIR-0117 browser verification).

## Build Environment Notes
- Inno Setup 6.7.3 installed to `C:\Projects\InnoSetup6\ISCC.exe` (not in Program Files — installed without admin)
- PyInstaller 6.21.0 installed in venv
- To rebuild: add `C:\Projects\InnoSetup6` to PATH, then run `.\tools\build_windows.ps1 -Version X.Y.Z -Channel stable`

## Next
- Publish to GitHub Releases: `.\tools\release_github.ps1 -Version 2.0.0 -Build 216`
- AIR-0217: Real-install E2E QA (manual, 8 scenarios from QA_AIR_0215_E2E.md)
- AIR-0219: Canonical export contract (KI-001)

---

# AIR-0210 Legacy Code Removal

**Date**: 2026-07-07
**Status**: DONE (merged)

## Objectives
- Confirm zero active references to script_analyzer and director_ai across the entire codebase.
- Delete both deprecated service files and all associated dead code.

## Changes Made
- Deleted app/services/script_analyzer.py
- Deleted app/services/director_ai.py
- Deleted templates/pages/script_analyzer_preview.html
- Deleted templates/pages/director_ai_preview.html
- Deleted scratch/test_script_analyzer.py
- Deleted scratch/test_director_ai.py
- Removed GET /admin/script-analyzer and GET /admin/director-ai from app/routers/pages.py

## Next Sprint
- scene_id 기반 E2E 테스트
- Asset Pipeline 통합 검증
