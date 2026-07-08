# Next Tasks

## Completed This Sprint
- AIR-0213: Scene pipeline E2E tests + Unmatched asset board — DONE
- AIR-0214: Windows installer + atomic-swap updater — DONE (PR #67, merged 2026-07-08)
- AIR-0215: Windows updater hardening — DONE (PR #67, merged 2026-07-08)
- AIR-0216: Release pipeline automation — DONE (PR #68, merged 2026-07-08)
- AIR-0218: GitHub Actions release automation — DONE (PR #68, merged 2026-07-08)
- **AIR Build 216**: First real installer generated — DONE (2026-07-08)
  - `AIRStudioSetup-2.0.0.exe` (344 MB) SHA256: ae90a183601518321643b41d01f79a188c7a3c5cb9f58a79800914ce229c97f3
  - `AIRStudio-2.0.0-win-x64.zip` (448 MB) SHA256: 8e73e310a7c907afa2c3467a6643baa14f53583c61c840dd7eeaefd3ffa85d12
  - `latest.json` (v2.0.0, build 216, channel stable) SHA256: 462867622589c52729ec6abb34e2bb4f52e2752fdaca0221c7d09426ed478430

## Pending: Real-install E2E QA
- AIR-0217: `project_status/QA_AIR_0215_E2E.md` — 8 scenarios, requires test machine

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

## Reference
- `BOOTSTRAP.md` — installer/updater system spec
- `RELEASE_PROCESS.md` — full release workflow (manual + CI)
- `QA_AIR_0215_E2E.md` — 8-scenario real-install E2E QA checklist
- `KNOWN_ISSUES.md` — issue list with priorities
