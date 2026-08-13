# Next Tasks

## Security Sprint Status (2026-07-13, read first)
- AIR-0227F-0: `/api/verify` P0 hotfix (platform system keys removed, PIN 1234
  fallback removed) — DONE, merged and deployed.
- AIR-0227F-0B: personal/BYOK API key protection + session-token wiring —
  DONE.
- AIR-0227F-0C: v2.3.7 release-integrity fix — DONE.
- AIR-0227F-0D: v2.3.7 build 243 rebuilt from source, GitHub prerelease
  assets replaced in place (`gh release upload --clobber`, no new Release,
  tag/prerelease status unchanged) — DONE. Final asset: ZIP 456,147,733
  bytes, SHA256 `ff73df7a751578ee8c0a05c0aa6b4a89cddde00d8717755f6b643e0289dddc4a`.
  Earlier AIR-0227F-0C build (456,147,806 bytes /
  `4c6666877258f66d0fe3460b1d47e42e1015af1fc43a35028fd103fd4affdfc0`) is
  superseded — see `docs/AIR_0227F_0B_VERIFY_FIELD_AUDIT.md` for the full
  build-evidence record.
- v2.3.7: REBUILT / TEST RELEASE / PRERELEASE. 자동업데이트: DISABLED.
  일반 사용자 배포: NOT APPROVED.
- 실계정 E2E QA: PENDING — not performed by explicit scope
  (no test-account creation, no real-account login).
- Production `global_settings` (`LATEST_APP_VERSION`/`LATEST_APP_URL`):
  NOT modified. AIR Worker PRs #70/#71/#72 remain unmerged (Draft) as
  required.
- Stage 9 (system key removal): NOT STARTED.
- `SUPABASE_SERVICE_ROLE_KEY` rotation: PENDING — see
  `docs/AIR_0225B_R0_SERVICE_ROLE_ROTATION_AUDIT.md`
  (`UNABLE_TO_VERIFY` / `BLOCKED — SUPABASE OWNER ACTION REQUIRED`, no
  Supabase dashboard/API access). Higher priority than provider-key
  rotation; needs team/CTO confirmation.

## Completed This Sprint
- AIR-0213: Scene pipeline E2E tests + Unmatched asset board — DONE
- AIR-0214: Windows installer + atomic-swap updater — DONE (PR #67, merged 2026-07-08)
- AIR-0215: Windows updater hardening — DONE (PR #67, merged 2026-07-08)
- AIR-0216: Release pipeline automation — DONE (PR #68, merged 2026-07-08)
- AIR-0218: GitHub Actions release automation — DONE (PR #68, merged 2026-07-08)
- **AIR Build 216**: First real installer generated — DONE (2026-07-08)
  - `AIRStudioSetup-2.0.0.exe` (344 MB) SHA256: ae90a183601518321643b41d01f79a188c7a3c5cb9f58a79800914ce229c97f3
  - `AIRStudio-2.0.0-win-x64.zip` (448 MB) SHA256: 8e73e310a7c907afa2c3467a6643baa14f53583c61c840dd7eeaefd3ffa85d12

## Current State (as of 2026-07-08)

### Main HEAD
`651b811b` — docs: update project status for build 216 artifacts (merged with local AIR-0122–0125 referral work)

### Recently Merged PRs
| PR | Title | Merged |
|----|-------|--------|
| #68 | AIR-0216/0218 Windows release pipeline automation | 2026-07-08 |
| #67 | AIR-0214/0215 Windows installer + hardened auto-update system | 2026-07-08 |
| #65 | AIR-0209 Planning Scene Contract Refactor | 2026-07-07 |
| #64 | AIR-0208 Scene Source of Truth Refactor | ~2026-07-06 |
| #63 | AIR-0207 Asset Upload and Scene Matching | ~2026-07-05 |
| #60 | AIR-0206 Production Planner | ~2026-07-04 |
| #27 | AIR-0123 add referral settlement pending worker | 2026-07-03 |
| #26 | AIR-0122 implement referral default sponsor foundation | 2026-07-03 |
| #25 | AIR-0121 refine image workflow guide final UI | 2026-07-03 |
| #17 | Fix auth-web lint execution and warnings | 2026-07-02 |
| #16 | Add per-feature AI model settings | 2026-07-02 |
| #15 | Enable Claude Sonnet 5 for script planning and generation | 2026-07-02 |
| #14 | feat: topic UI and admin ElevenLabs voice management | 2026-07-02 |
| #12 | AIR-0115 document mytube remote cleanup | 2026-07-01 |
| #11 | AIR-0112 enforce Longform Scene asset readiness | 2026-07-01 |
| #10 | AIR-0111 Longform MVP end-to-end validation | 2026-07-01 |
| #9  | AIR-0110A clean Longform integration | 2026-07-01 |

## Pending: Referral Payout
- AIR-0124/0125 (local, not yet in a PR): manual referral payout processor + migration runbook — needs a branch/PR.

## Pending: GitHub Release Upload
- Artifacts in `release/` are ready; publish with: `.\tools\release_github.ps1 -Version 2.0.0 -Build 216`

## Next Sprint Candidates

1. **Canonical export contract** (KI-001) — AIR-0219
   Define and enforce a single export delivery path.
   Multiple paths (render/export/download) are uncoordinated.

2. **Authenticated browser E2E fixture** (KI-003)
   Full Longform worker journey with test credentials.
   Login → Claim → Script → Prompts → Upload → TTS → Render check.
   Requires Playwright setup + Supabase test account.

## Task Pointer
Next task ID: `AIR-0219`. Local referral work (AIR-0124/0125) still needs a PR opened against current main. (Note: `AIR-0126` is already taken upstream by the project-status-sync task, so settlement automation/refund rollback design should use the next free ID after `AIR-0219`.)

## Reference
- `KNOWN_ISSUES.md` — issue list with priorities
