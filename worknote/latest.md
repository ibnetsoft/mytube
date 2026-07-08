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
